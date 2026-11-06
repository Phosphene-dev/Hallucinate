"""Sounds like this: songs that sound like the one you picked, from how they sound (core/soundlike.py).

To find them, Hallucinate first has to listen to your music: a minute or so of each song, in the analysis
helper at low priority, liked and most played songs first. By default that happens only while nothing is
playing and not on battery; it can also run any time, or only when asked (Settings → Discover → Sounds like
this), be paused, and its measurements forgotten. A song picked before it's been measured is measured there
and then. The whole of it can be switched off (shell feature "soundsLike"): then nothing is measured.

Radio mode can pick by sound too, or both ways (Library.radioTracks asks radio_pick here)."""
import datetime
import glob
import logging
import os
import sys

from PySide6.QtCore import Property, QObject, QSettings, QTimer, Signal, Slot

from .analysis import Analyser
from .core import discover as dcore
from .core import soundlike as core
from .core.i18n import fill, translate
from .library import _Reader

logger = logging.getLogger(__name__)

WHEN = ("idle", "always", "ask")  # while nothing is playing / any time / only when asked
ORDERS = ("flow", "alike")
SIZES = (25, 50, 100)
PER_ARTIST = (1, 2, 3, 5, 0)  # (0: no limit)
RADIO = ("together", "sound", "both")
BATCH = 40  # songs asked for at a time
SAVE_EVERY = 20
RESUME_MS = 15_000  # after playback stops, wait this long before measuring again (a pause to skip isn't idle)
ENOUGH = 30  # fewer songs measured than this: picks may not be close, and that's said
BROKEN_AFTER = 12  # this many songs in a row not measured: it's the helper (or a missing drive), not the songs


def on_battery():
    """Whether this computer is running on its battery now (False when there's no telling)."""
    try:
        if sys.platform.startswith("linux"):
            mains = [p for p in glob.glob("/sys/class/power_supply/*") if _read(p, "type") == "Mains"]
            batteries = [p for p in glob.glob("/sys/class/power_supply/*") if _read(p, "type") == "Battery"]
            return bool(batteries) and bool(mains) and not any(_read(p, "online") == "1" for p in mains)
        if os.name == "nt":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("percent", ctypes.c_ubyte),
                            ("saver", ctypes.c_ubyte), ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]

            s = Status()
            return bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s))) and s.ac == 0
    except (OSError, ValueError, AttributeError):
        pass
    return False


def _read(folder, name):
    try:
        with open(os.path.join(folder, name), encoding="ascii", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


class SoundsLike(QObject):
    changed = Signal()  # how far measuring has got, and whether it's running
    settingsChanged = Signal()
    message = Signal(str)  # something to say in a toast
    _counted = Signal(object)
    _batch = Signal(object)
    _picked = Signal(object)
    _seed = Signal(object)

    def __init__(self, db_path, player=None, userlib=None, shell=None, analyser=None, quick=None, battery=None,
                 autostart=True, parent=None):
        super().__init__(parent)
        self._reader = _Reader(str(db_path), "sounds-like")
        self._player, self._userlib, self._shell = player, userlib, shell
        self._settings = QSettings()
        # Its own helpers: measuring never waits behind (or holds up) a waveform, and one picked song isn't
        # held up by (or cancelled with) the background run.
        self._analyser = analyser or Analyser(self)
        self._quick = quick or Analyser(self)
        self._battery = battery or on_battery
        self.index = core.Index()
        self._measured, self._total = -1, 0
        self._todo, self._results = [], []
        self._failing = []  # songs not measured in a row: kept back until one is (see BROKEN_AFTER)
        self._broken = False  # the helper didn't work: not tried again until the app is started again
        self._current = None
        self._fetching = False
        self._running = False
        self._asked = False  # "Measure now" (when it's set to only when asked): until everything's measured
        self._closing = False
        self._counted.connect(self._on_counted)
        self._batch.connect(self._on_batch)
        self._picked.connect(self._on_picked)
        self._seed.connect(self._on_seed)
        self._soon = QTimer(self, singleShot=True, interval=RESUME_MS, timeout=self._consider)
        self._tick = QTimer(self, interval=60_000, timeout=self._consider)  # (the battery, a quiet library)
        if autostart:
            self._tick.start()
            QTimer.singleShot(20_000, self._recount)  # (not while the app is starting)
        if player is not None:
            player.stateChanged.connect(self._player_changed)
        if shell is not None:
            shell.featuresChanged.connect(self._features_changed)

    # --- settings -----------------------------------------------------------------------------------------
    def _get(self, key, default, kind, choices=None):
        try:
            v = self._settings.value(f"soundsLike/{key}", default)
            v = (str(v).lower() == "true") if kind is bool and isinstance(v, str) else kind(v)
        except (TypeError, ValueError):
            return default
        return v if choices is None or v in choices else default

    def _set(self, key, value):
        self._settings.setValue(f"soundsLike/{key}", value)
        self.settingsChanged.emit()

    def _prop(key, default, kind, notify, choices=None, slot=""):  # noqa: N805
        # (the setter is named for Qt by hand: a Slot takes its function's name, and every one here is set_)
        def get(self):
            return self._get(key, default, kind, choices)

        def set_(self, value):
            value = kind(value)
            if (choices is None or value in choices) and value != get(self):
                self._set(key, value)
                self._consider()
        return Property(kind if kind is not str else str, get, notify=notify), Slot(kind, name=slot or "set" + key[0].upper() + key[1:])(set_)

    when, setWhen = _prop("when", "idle", str, settingsChanged, WHEN)
    notOnBattery, setNotOnBattery = _prop("notOnBattery", True, bool, settingsChanged)
    paused, setPaused = _prop("paused", False, bool, settingsChanged)
    size, setSize = _prop("size", 50, int, settingsChanged, SIZES)
    order, setOrder = _prop("order", "flow", str, settingsChanged, ORDERS)
    tempo, setTempo = _prop("tempo", True, bool, settingsChanged)
    keys, setKeys = _prop("keys", False, bool, settingsChanged)
    sameArtist, setSameArtist = _prop("sameArtist", True, bool, settingsChanged)
    perArtist, setPerArtist = _prop("perArtist", 3, int, settingsChanged, PER_ARTIST)
    radioPicks, setRadioPicks = _prop("radio", "together", str, settingsChanged, RADIO, slot="setRadioPicks")

    @Property(bool, notify=settingsChanged)
    def enabled(self):
        return self._shell is None or self._shell.featureOn("soundsLike")

    # --- how far it's got ----------------------------------------------------------------------------------
    @Property(int, notify=changed)
    def measured(self):
        """Songs measured so far (-1 until counted)."""
        return self._measured

    @Property(int, notify=changed)
    def total(self):
        return self._total

    @Property(bool, notify=changed)
    def running(self):
        return self._running

    @Property(str, notify=changed)
    def waiting(self):
        """Why it isn't measuring now: "" (it is, or it's all done), "off", "paused", "playing", "battery",
        "ask" or "broken" (the helper didn't work this session)."""
        if self._running or (self._total and self._measured >= self._total):
            return ""
        return self._why_not() or ""

    @Slot()
    def _recount(self):
        if self._closing:
            return

        def work(db):
            try:
                core.prune(db)
                self._counted.emit(core.counts(db))
            except Exception:  # noqa: BLE001
                logger.exception("Couldn't count the songs measured")
        self._reader.submit(work)

    @Slot(object)
    def _on_counted(self, got):
        self._measured, self._total = got
        self.changed.emit()
        self._consider()

    # --- measuring in the background ----------------------------------------------------------------------
    def _why_not(self):
        if not self.enabled:
            return "off"
        if self._broken:
            return "broken"
        if self.paused:
            return "paused"
        if self.when == "ask" and not self._asked:
            return "ask"
        if self.when == "idle" and not self._asked and self._player is not None and self._player.playing:
            return "playing"
        if self.notOnBattery and not self._asked and self._battery():
            return "battery"
        return None

    @Slot()
    def _consider(self):
        """Start or stop measuring, as things are now."""
        if self._closing:
            return
        if self._why_not() is not None:
            self._stop()
        elif not self._running and self._measured >= 0 and self._measured < self._total:
            self._running = True
            self.changed.emit()
            self._next()
        self.changed.emit()

    @Slot()
    def _features_changed(self):
        self.settingsChanged.emit()  # (enabled follows the switch)
        self._consider()

    @Slot()
    def _player_changed(self):
        if self.when != "idle" or self._asked:
            return
        if self._player.playing:
            self._soon.stop()
            self._consider()
        else:
            self._soon.start()

    def _stop(self):
        if not self._running:
            return
        self._running = False
        if self._current is not None:
            self._todo.insert(0, self._current)  # (abandoned partway: it's first next time)
            self._current = None
        self._analyser.cancel()
        self._save()
        self.changed.emit()

    @Slot()
    def measureNow(self):
        """Measure everything not measured yet, now (whatever "when" is set to); unpauses."""
        self._asked = True
        if self.paused:
            self._set("paused", False)
        if self._measured < 0:
            self._recount()
        else:
            self._consider()

    @Slot()
    def pause(self):
        """Stop measuring until resumed (the activity list's Stop, Settings' Pause)."""
        self._asked = False
        self.setPaused(True)

    @Slot()
    def resume(self):
        self.setPaused(False)

    def _next(self):
        if not self._running or self._closing:
            return
        if self._why_not() is not None:
            self._stop()
            return
        if not self._todo:
            if not self._fetching:
                self._fetching = True
                skip = {r["path"] for r in self._results + self._failing}

                def work(db):
                    try:
                        self._batch.emit(core.to_measure(db, BATCH, skip))
                    except Exception:  # noqa: BLE001
                        logger.exception("Couldn't find songs to measure")
                        self._batch.emit([])
                self._reader.submit(work)
            return
        row = self._current = self._todo.pop(0)
        self._analyser.submit(row["file"], "features", lambda result, r=row: self._measured_one(r, result),
                              extra={"start": row["offset"] + core.window(row["duration"]), "low": True})

    @Slot(object)
    def _on_batch(self, rows):
        self._fetching = False
        if not rows:  # all done
            self._save()
            self._running = self._asked = False
            self._recount_soon()
            self.changed.emit()
            return
        self._todo = rows
        self._next()

    def _measured_one(self, row, result):
        if self._current is not row:
            return  # (stopped meanwhile: it's measured again later)
        self._current = None
        entry = {"path": row["path"], "mtime": row["mtime"], "result": None}
        if result is None:
            # It couldn't be decoded: a damaged file, or the helper not working at all (or the drive gone). Those
            # aren't saved as "can't be measured" until a song after them is measured, so a broken helper doesn't
            # write the whole library off.
            self._failing.append(entry)
            if len(self._failing) >= BROKEN_AFTER:
                logger.warning("Sounds like this: %d songs in a row couldn't be decoded; stopping", len(self._failing))
                self._failing = []
                self._broken = True
                self._stop()
                self.message.emit(translate("SoundsLike", "Hallucinate couldn't listen to your music just now (song after song failed to decode), so it has stopped for this session. It tries again next time it starts."))
                return
        else:
            entry["result"] = None if result.get("empty") else result
            self._results += self._failing + [entry]
            self._measured = min(self._total, self._measured + 1 + len(self._failing))
            self._failing = []
        if len(self._results) >= SAVE_EVERY:
            self._save()
        self.changed.emit()
        QTimer.singleShot(50, self._next)  # (a breath between songs)

    def _save(self):
        rows, self._results = self._results, []
        if not rows:
            return

        def work(db):
            try:
                core.store(db, rows)
                self.index.stale = True
            except Exception:  # noqa: BLE001
                logger.exception("Couldn't save how songs sound")
        self._reader.submit(work)

    def _recount_soon(self):
        QTimer.singleShot(1000, self._recount)

    @Slot()
    def libraryChanged(self):
        """Songs were added or changed: count again (and measure them, as set)."""
        self.index.stale = True
        if not self._running:
            self._recount()

    @Slot()
    def forget(self):
        """Throw away every measurement (they're measured again, as set)."""
        self._stop()
        self._todo.clear()
        self._reader.submit(lambda db: core.forget(db))
        self.index.stale = True
        self._recount_soon()

    # --- Sounds like this -------------------------------------------------------------------------------
    def options(self, **override):
        return dict({"size": self.size, "order": self.order, "tempo": self.tempo, "keys": self.keys,
                "same_artist": self.sameArtist, "per_artist": self.perArtist}, **override)

    def pick(self, db, seeds, exclude, opts):
        """Paths that sound like `seeds` (on a worker, with its own connection), leaving out what Discover was
        told you're not interested in. `opts` come from options(), read on the window's thread (settings aren't
        to be read from a worker)."""
        self.index.load(db)
        left_out = dcore.dismissed(db)
        songs = {d["key"] for d in left_out if d["kind"] == "song"}
        artists = {d["key"] for d in left_out if d["kind"] == "artist"}
        return self.index.pick(seeds, opts["size"], opts["order"], opts["tempo"], opts["keys"], opts["same_artist"],
                               opts["per_artist"], set(exclude) | songs, artists)

    @Slot(str)
    def playLike(self, path):
        """Plays the song, then songs that sound like it."""
        self._ask("play", path)

    @Slot(str)
    def queueLike(self, path):
        """Adds songs that sound like it to the end of the queue."""
        self._ask("queue", path)

    @Slot(str, str)
    def saveLike(self, path, title):
        """The song and songs that sound like it, as a new playlist."""
        self._ask("save", path, title)

    def _ask(self, action, path, title=""):
        if not self.enabled or not path:
            return
        if "://" in path:
            self.message.emit(translate("SoundsLike", "Only songs on this computer can be matched by how they sound."))
            return
        opts = self.options()
        queued = []
        if action == "queue" and self._player is not None:
            queued = [t.get("path", "") for t in getattr(self._player, "_queue", [])]

        def work(db):
            try:
                self.index.load(db)
                if not self.index.has(path):
                    row = db.conn.execute(
                        "SELECT t.path, t.file, t.cue_start, t.duration, t.mtime, f.path AS done FROM tracks t "
                        "LEFT JOIN sound_features f ON f.path = t.path AND f.mtime = t.mtime AND f.version = ? "
                        "WHERE t.path = ?", (core.VERSION, path)).fetchone()
                    if row is None:
                        self._picked.emit((action, path, title, None, "gone"))
                    elif row["done"]:  # (measured, but there was nothing to tell: silence, or too short)
                        self._picked.emit((action, path, title, None, "unmeasurable"))
                    else:
                        self._seed.emit((action, path, title, {
                            "path": row["path"], "file": row["file"] or row["path"],
                            "offset": float(row["cue_start"] or 0.0), "duration": float(row["duration"] or 0.0),
                            "mtime": row["mtime"]}))
                    return
                self._picked.emit((action, path, title, self.pick(db, [path], queued, opts), ""))
            except Exception:  # noqa: BLE001
                logger.exception("Sounds like this couldn't pick songs")
                self._picked.emit((action, path, title, None, "failed"))
        self._reader.submit(work)

    @Slot(object)
    def _on_seed(self, payload):
        """The song picked hasn't been measured yet: measure it now, then pick."""
        action, path, title, row = payload
        self.message.emit(translate("SoundsLike", "Listening to the song first…"))

        def measured(result):
            got = None if result is None or result.get("empty") else result
            rows = [{"path": row["path"], "mtime": row["mtime"], "result": got}]

            def work(db):
                core.store(db, rows)
                self.index.stale = True
            self._reader.submit(work)
            if got is None:
                self._picked.emit((action, path, title, None, "unmeasurable"))
            else:
                self._ask(action, path, title)
        self._quick.submit(row["file"], "features", measured, first=True,
                           extra={"start": row["offset"] + core.window(row["duration"])})

    @Slot(object)
    def _on_picked(self, payload):
        action, path, title, paths, why = payload
        if paths is None:
            self.message.emit({
                "gone": translate("SoundsLike", "That song isn't in the library any more."),
                "unmeasurable": translate("SoundsLike", "Hallucinate couldn't listen to that song (it may be silent, too short or damaged)."),
            }.get(why, translate("SoundsLike", "Couldn't find songs that sound like that.")))
            return
        if not paths:
            self.message.emit(translate("SoundsLike", "No songs that sound like that yet: Hallucinate hasn't listened to enough of your music.")
                              if len(self.index) < ENOUGH else
                              translate("SoundsLike", "No other songs sound like that with these settings."))
            return
        lib = self._userlib
        if lib is None:
            return
        if action == "play":
            lib.playPaths([path, *paths])
        elif action == "queue":
            lib.enqueuePaths(paths)
            self.message.emit(fill(translate("SoundsLike", "%1 added to the queue"), self._songs(len(paths))))
        elif action == "save":
            name = fill(translate("SoundsLike", "Sounds like %1 (%2)"), title or translate("SoundsLike", "this"),
                        datetime.date.today().strftime("%Y-%m-%d"))
            pid = lib.createPlaylist(name)
            if pid >= 0:
                lib.addPathsToPlaylist(pid, [path, *paths])
                self.message.emit(fill(translate("SoundsLike", "Saved as “%1”"), name))
        if len(self.index) < ENOUGH and self._measured < self._total:
            self.message.emit(fill(translate("SoundsLike", "Picked from the %1 songs listened to so far: they'll get closer as Hallucinate listens to more of your music."),
                                   str(len(self.index))))

    @staticmethod
    def _songs(n):
        return translate("SoundsLike", "%n song(s)", None, n)

    # --- radio ----------------------------------------------------------------------------------------------
    def radio_mode(self):
        """How radio mode picks: "together" (what's played together, tags), "sound" or "both"."""
        return self.radioPicks if self.enabled else "together"

    def radio_options(self, limit):
        """What radio's picks by sound go by (read here, on the window's thread)."""
        return self.options(size=limit, order="alike", per_artist=2)

    def radio_pick(self, db, seeds, exclude, opts):
        """Paths for radio mode that sound like the last few songs (on the library's worker)."""
        try:
            return self.pick(db, seeds, exclude, opts)
        except Exception:  # noqa: BLE001
            logger.exception("Radio couldn't pick by sound")
            return []

    def shutdown(self):
        self._closing = True
        self._tick.stop()
        self._soon.stop()
        self._results_on_close()
        self._analyser.shutdown()
        self._quick.shutdown()
        self._reader.close()

    def _results_on_close(self):
        if self._current is not None:
            self._current = None
        self._save()
