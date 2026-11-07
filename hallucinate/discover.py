"""The Discover page's data (see core/discover.py for how each shelf is made): read on the library's own reader
thread, and only once the page has been opened (someone who never opens it pays nothing), again when the day
changes or the library has, while the page is in use.

Every shelf can be switched off on its own (Settings → Discover, or the shelf's own menu: shell features
"discover*"); a switched-off shelf isn't even read."""
import datetime
import logging
import time

from PySide6.QtCore import Property, QObject, QSettings, QTimer, QUrl, Signal, Slot

from .core import discover as core
from .core.i18n import fill, translate
from .library import _Reader, decorate
from .models import ALBUM_KEYS, ARTIST_KEYS, TRACK_KEYS, DictModel

logger = logging.getLogger(__name__)

REASON_ALBUM_KEYS = [*ALBUM_KEYS, "reason"]
REASON_TRACK_KEYS = [*TRACK_KEYS, "reason"]
REASON_ARTIST_KEYS = [*ARTIST_KEYS, "reason", "key"]
# what each choice in Settings means
FORGOTTEN_DAYS = (30, 90, 180, 365)
MIX_SIZES = (25, 40, 60, 100)
FRESH = {"none": 0.0, "some": 0.25, "more": 0.5}
SHELVES = ("discoverMixes", "discoverForgotten", "discoverForgottenSongs", "discoverForgottenArtists",
           "discoverDeepCuts", "discoverNeverPlayed", "discoverOnThisDay")


class Discover(QObject):
    changed = Signal()
    settingsChanged = Signal()
    dismissedChanged = Signal()
    undoable = Signal(str)
    _done = Signal(object)

    def __init__(self, db_path, player=None, userlib=None, shell=None, parent=None):
        super().__init__(parent)
        self._reader = _Reader(str(db_path), "discover")
        self._player, self._userlib, self._shell = player, userlib, shell
        self._settings = QSettings()
        self._models = {
            "albums": DictModel(REASON_ALBUM_KEYS, self), "songs": DictModel(REASON_TRACK_KEYS, self),
            "artists": DictModel(REASON_ARTIST_KEYS, self), "deepCuts": DictModel(REASON_TRACK_KEYS, self),
            "neverPlayed": DictModel(REASON_ALBUM_KEYS, self),
        }
        self._mixes, self._mix_songs, self._days, self._dismissed = [], [], [], []
        self._wanted = False  # the page has been opened: keep it up to date from now on
        self._loading = False
        self._shelves_pending = []  # (shelves whose new rows are still to show, one a turn)
        self._shelf_timer = QTimer(self, singleShot=True, interval=0)
        self._shelf_timer.timeout.connect(self._next_shelf)
        self._loaded_day = ""
        self._last_undo = None
        self._done.connect(self._apply)
        self._soon = QTimer(self, singleShot=True, interval=2000, timeout=self.refresh)  # (library edits come in bursts)
        self._day = QTimer(self, interval=10 * 60 * 1000, timeout=self._check_day)
        self._day.start()

    def _setting(self, key, default, kind=int):
        try:
            return kind(self._settings.value(f"discover/{key}", default))
        except (TypeError, ValueError):
            return default

    def _on(self, name):
        return self._shell is None or self._shell.featureOn(name)

    # --- what the page shows ------------------------------------------------------------------------------
    def _model(name):  # noqa: N805
        return Property(QObject, lambda self: self._models[name], constant=True)

    forgottenAlbums = _model("albums")
    forgottenSongs = _model("songs")
    forgottenArtists = _model("artists")
    deepCuts = _model("deepCuts")
    neverPlayed = _model("neverPlayed")

    @Property("QVariantList", notify=changed)
    def mixes(self):
        """[{"title", "subtitle", "arts" (cover URLs, up to 4), "count", "minutes"}] (the songs stay here)."""
        return self._mixes

    @Property("QVariantList", notify=changed)
    def onThisDay(self):
        """[{"label", "year", "albums": [...], "songs": [...]}], nearest year first."""
        return self._days

    @Property(bool, notify=changed)
    def loading(self):
        return self._loading

    @Property(bool, notify=changed)
    def empty(self):
        return not (self._mixes or self._days or any(m.count for m in self._models.values()))

    # --- reading ------------------------------------------------------------------------------------------
    @Slot()
    def open(self):
        """The page is showing: read it (the first time, or when the day has changed since)."""
        self._wanted = True
        if self._loaded_day != datetime.date.today().isoformat():
            self.refresh()

    @Slot()
    def refresh(self):
        if not self._wanted:
            return
        self._loading = True
        self.changed.emit()
        wanted = {name: self._on(name) for name in SHELVES}
        days = self._setting("forgottenDays", 90)
        days = days if days in FORGOTTEN_DAYS else 90
        count = max(1, min(8, self._setting("mixCount", 4)))
        size = self._setting("mixSize", 40)
        size = size if size in MIX_SIZES else 40
        fresh = FRESH.get(self._setting("fresh", "some", str), 0.25)

        def work(db):
            try:
                now = time.time()
                f = core.forgotten(db, now, min_days=days) if any(
                    wanted[n] for n in ("discoverForgotten", "discoverForgottenSongs", "discoverForgottenArtists",
                                        "discoverDeepCuts", "discoverNeverPlayed")) else {}
                data = {
                    "day": datetime.date.fromtimestamp(now).isoformat(),
                    "albums": decorate(f.get("albums", [])) if wanted["discoverForgotten"] else [],
                    "songs": decorate(f.get("songs", [])) if wanted["discoverForgottenSongs"] else [],
                    "artists": f.get("artists", []) if wanted["discoverForgottenArtists"] else [],
                    "deepCuts": decorate(f.get("deepCuts", [])) if wanted["discoverDeepCuts"] else [],
                    "neverPlayed": decorate(f.get("neverPlayed", [])) if wanted["discoverNeverPlayed"] else [],
                    "mixes": core.daily_mixes(db, now, count=count, size=size, fresh=fresh)
                    if wanted["discoverMixes"] else [],
                    "days": core.on_this_day(db, now) if wanted["discoverOnThisDay"] else [],
                    "dismissed": core.dismissed(db),
                }
            except Exception:  # noqa: BLE001 - a shelf that couldn't be read is left empty, never the window
                logger.exception("Discover couldn't be read")
                data = None
            self._done.emit(data)

        self._reader.submit(work)

    @Slot(object)
    def _apply(self, data):
        if data is not None and "dismissedOnly" in data:  # (Not interested, or let back in: the list in Settings)
            self._dismissed = data["dismissedOnly"]
            self.dismissedChanged.emit()
            return
        self._loading = False
        if data is None:
            self.changed.emit()
            return
        self._loaded_day = data["day"]
        for a in data["artists"]:
            a["artUrl"] = QUrl.fromLocalFile(a["art"]).toString() if a.get("art") else ""
            a["key"] = core.artist_key({"album_artist": a["name"]})
        # Only the shelves whose songs changed are made again, one per turn of the event loop: all five at once
        # (each one's rows made anew) froze the page for a moment
        self._shelves_pending = [(n, data[n]) for n in ("albums", "songs", "deepCuts", "neverPlayed", "artists")
                                 if self._models[n].items() != data[n]]
        self._next_shelf()
        self._mix_songs = [decorate(m["songs"]) for m in data["mixes"]]
        self._mixes = [{"title": m["title"], "subtitle": m["subtitle"], "count": len(m["songs"]),
                        "minutes": round(sum(s.get("duration") or 0 for s in m["songs"]) / 60),
                        "arts": [QUrl.fromLocalFile(a).toString() for a in m["arts"]]} for m in data["mixes"]]
        for d in data["days"]:
            decorate(d["albums"])
            decorate(d["songs"])
        self._days = data["days"]
        self._dismissed = data["dismissed"]
        self.changed.emit()
        self.dismissedChanged.emit()

    @Slot()
    def _next_shelf(self):
        if self._shelves_pending:
            name, items = self._shelves_pending.pop(0)
            self._models[name].set_items(items)
            if self._shelves_pending:
                self._shelf_timer.start()

    def _check_day(self):
        if self._wanted and self._loaded_day and self._loaded_day != datetime.date.today().isoformat():
            self.refresh()  # (a new day: new mixes)

    @Slot()
    def libraryChanged(self):
        """Songs were added, removed or played: read again shortly, if the page is in use."""
        if self._wanted:
            self._soon.start()

    # --- playing ------------------------------------------------------------------------------------------
    def _mix(self, i):
        return list(self._mix_songs[i]) if 0 <= i < len(self._mix_songs) else []

    @Slot(int, bool)
    def playMix(self, i, shuffle=False):
        songs = self._mix(i)
        if songs and self._player is not None:
            self._player.setShuffle(bool(shuffle))
            self._player.playList(songs, 0)

    @Slot(int)
    def queueMix(self, i):
        songs = self._mix(i)
        if songs and self._player is not None:
            self._player.enqueueAll(songs)

    @Slot(int, result="QVariantList")
    def mixSongs(self, i):
        return self._mix(i)

    @Slot(int, result=int)
    def saveMix(self, i):
        """The mix as a playlist of its own (it stays when the mix changes tomorrow); returns its id, or -1."""
        songs = self._mix(i)
        if not songs or self._userlib is None:
            return -1
        name = fill(translate("Discover", "%1 (%2)"), self._mixes[i]["title"],
                    datetime.date.today().strftime("%Y-%m-%d"))
        pid = self._userlib.createPlaylist(name)
        if pid >= 0:
            self._userlib._write(lambda db, p, ps: db.playlist_add(p, ps), pid, [s["path"] for s in songs],
                                 reload_playlist=True)
        return pid

    @Slot(str, int)
    def playSongs(self, shelf, index):
        """Plays a song shelf (forgotten songs, deep cuts) from the song chosen."""
        model = self._models.get(shelf)
        if model is not None and self._player is not None:
            self._player.playList(model.items(), max(0, index))

    @Slot(int, int)
    def playDay(self, day, index):
        if 0 <= day < len(self._days) and self._player is not None:
            self._player.playList(list(self._days[day]["songs"]), max(0, index))

    # --- "Not interested" ---------------------------------------------------------------------------------
    @Slot(str, str, str)
    def notInterested(self, kind, key, label):
        """Leaves an album, song or artist out of Discover from now on (with Undo; Settings lets it back in)."""
        if kind not in core.KINDS or not key:
            return
        self._last_undo = (kind, key)
        self._write(lambda db: core.dismiss(db, kind, key, label))
        self.undoable.emit(fill(translate("Discover", "“%1” won't be suggested again"), label or key))

    @Slot(str, result=str)
    def artistKey(self, name):
        return core.artist_key({"album_artist": name})

    @Slot()
    def undo(self):
        if self._last_undo:
            kind, key = self._last_undo
            self._last_undo = None
            self.letBackIn(kind, key)

    @Property("QVariantList", notify=dismissedChanged)
    def dismissed(self):
        return self._dismissed

    @Slot(str, str)
    def letBackIn(self, kind, key):
        self._write(lambda db: core.undismiss(db, kind, key))

    @Slot()
    def letAllBackIn(self):
        self._write(core.undismiss_all)

    def _write(self, fn):
        def work(db):
            try:
                fn(db)
                dismissed = core.dismissed(db)
            except Exception:  # noqa: BLE001
                logger.exception("Discover couldn't save that")
                return
            self._done.emit({"dismissedOnly": dismissed})
        self._reader.submit(work)
        self.refresh()  # (after the write: the reader takes them in turn)

    # --- settings -----------------------------------------------------------------------------------------
    def _setting_prop(key, default, kind, choices=None):  # noqa: N805
        # (each setter below is given its name for Qt by hand: a Slot takes its function's name, and these are all set_)
        def get(self):
            v = self._setting(key, default, kind)
            return v if choices is None or v in choices else default

        def set_(self, value):
            value = kind(value)
            if choices is not None and value not in choices:
                return
            if value != get(self):
                self._settings.setValue(f"discover/{key}", value)
                self.settingsChanged.emit()
                self.refresh()
        return get, set_

    _fd = _setting_prop("forgottenDays", 90, int, FORGOTTEN_DAYS)
    forgottenDays = Property(int, _fd[0], notify=settingsChanged)
    setForgottenDays = Slot(int, name="setForgottenDays")(_fd[1])
    _mc = _setting_prop("mixCount", 4, int, range(1, 9))
    mixCount = Property(int, _mc[0], notify=settingsChanged)
    setMixCount = Slot(int, name="setMixCount")(_mc[1])
    _ms = _setting_prop("mixSize", 40, int, MIX_SIZES)
    mixSize = Property(int, _ms[0], notify=settingsChanged)
    setMixSize = Slot(int, name="setMixSize")(_ms[1])
    _fr = _setting_prop("fresh", "some", str, tuple(FRESH))
    fresh = Property(str, _fr[0], notify=settingsChanged)
    setFresh = Slot(str, name="setFresh")(_fr[1])

    @Slot(str, bool)
    def setShelf(self, name, on):
        """A shelf switched on or off (Settings, or its own menu): the page reads again without (or with) it."""
        if self._shell is not None and name in SHELVES:
            self._shell.setFeature(name, on)
            self.refresh()

    def shutdown(self):
        self._day.stop()
        self._soon.stop()
        self._reader.close()
