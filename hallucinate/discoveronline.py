"""Discover's online shelves and the wishlist (see core/online_discover.py for what's asked of whom).

Each online part is off until switched on (shell features "discoverNewReleases", "discoverSimilar"), and
nothing is asked while offline mode is on. Lookups run one at a time on a worker of their own, with its own
library connection: new releases for the artists you play at most once a day each, similar artists at most once
a fortnight; what's found is kept, so the shelves show at once. A run shows in the background list with Stop.

Concerts nearby ("discoverConcerts") ask Ticketmaster, with a key of your own, about each artist you play
every few days, near the place you typed in (found on the map once, with OpenStreetMap: see core/concerts.py).

The wishlist ("discoverWishlist", on: it's only shown once something is on it) is kept in the library and never
sent anywhere. After a scan, wishes that are now in your library are ticked off (unless that's switched off).

Previews play through a small player of their own: the music you were playing pauses, and carries on after."""
import datetime
import logging
import os
import queue
import threading
import time

from PySide6.QtCore import Property, QObject, QSettings, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from .core import concerts as gigs
from .core import discover as dcore
from .core import net
from .core import online_discover as core
from .core.db import Database
from .core.i18n import fill, translate

logger = logging.getLogger(__name__)

FOLLOW = {"top50": 50, "top200": 200, "all": 0}
WINDOWS = (30, 90, 180, 365)
SIMILAR_SOURCES = ("listenbrainz", "deezer", "lastfm")
SEEDS = (10, 25, 50)
PREVIEWS = ("deezer", "itunes", "off")
RELEASES_EVERY_S = 20 * 3600
SIMILAR_EVERY_S = 14 * 86400
MBID_AGAIN_S = 30 * 86400  # an artist MusicBrainz didn't know is looked for again after a month
CONCERTS_EVERY_S = 3 * 86400
CONCERT_FOLLOW = {"top50": 50, "top200": 200}
TICKETMASTER_GAP_S = 0.25  # (it takes five requests a second)
FEATURES = ("discoverNewReleases", "discoverSimilar", "discoverConcerts")


class OnlineDiscover(QObject):
    changed = Signal()  # what the shelves show
    progressChanged = Signal()
    settingsChanged = Signal()
    wishlistChanged = Signal()
    previewChanged = Signal()
    message = Signal(str)
    _found = Signal(object)  # {"releases": [...], "similar": [...]} read on the worker
    _finished = Signal(str)  # a lookup ("releases", "similar") is over
    _wishes = Signal(object)
    _progress = Signal(str, int, int)
    _ticked = Signal(object)
    _preview_ready = Signal(object)
    _placed = Signal(str, object)  # the place typed, and where it is ({"lat", "lon", "name"}, None or an error)

    def __init__(self, db_path, art_dir, player=None, shell=None, sources=None, parent=None, autostart=True):
        super().__init__(parent)
        self._db_path = str(db_path)
        self._art_dir = str(art_dir)
        self._player, self._shell, self._sources = player, shell, sources
        self._settings = QSettings()
        self._releases, self._similar, self._wishlist, self._concerts = [], [], [], []
        self._place_status = ""  # "looking", "missing", or what went wrong finding the place typed in
        self._busy, self._done, self._total = "", 0, 0
        self._stop = threading.Event()
        self._generation = 0  # Stop moves it on: lookups asked for before then are dropped, not run
        self._pending = []  # lookups asked for and not over yet (one of each at a time)
        self._again = set()  # ones asked for afresh while they ran (their settings changed): run again after
        self._closing = False
        self._wanted = False  # the Discover page has been opened: the shelves are kept up to date from then on
        self._jobs = queue.Queue()
        self._found.connect(self._on_found)
        self._finished.connect(self._on_finished)
        self._wishes.connect(self._on_wishes)
        self._progress.connect(self._on_progress)
        self._ticked.connect(self._on_ticked)
        self._preview_ready.connect(self._on_preview)
        self._placed.connect(self._on_placed)
        self._preview = None  # (QMediaPlayer, QAudioOutput), made when first wanted
        self._preview_name, self._preview_title, self._resume = "", "", False
        self._thread = threading.Thread(target=self._work, name="discover-online", daemon=True)
        self._thread.start()
        self._daily = QTimer(self, interval=3 * 3600 * 1000, timeout=self._check)  # (it decides whether it's due)
        if autostart:
            self._daily.start()
            QTimer.singleShot(60_000, self._check)
        if shell is not None:
            shell.featuresChanged.connect(self._features_changed)
        self._had_key = self.ticketmasterReady
        if sources is not None and hasattr(sources, "changed"):
            sources.changed.connect(self._sources_changed)
        self._queue_read()

    # --- settings -------------------------------------------------------------------------------------------
    def _get(self, key, default, kind, choices=None):
        try:
            v = self._settings.value(f"discoverOnline/{key}", default)
            v = (str(v).lower() == "true") if kind is bool and isinstance(v, str) else kind(v)
        except (TypeError, ValueError):
            return default
        return v if choices is None or v in choices else default

    def _prop(key, default, kind, notify, choices=None, reread=False, refetch=""):  # noqa: N805
        def get(self):
            return self._get(key, default, kind, choices)

        def set_(self, value):
            value = kind(value)
            if (choices is None or value in choices) and value != get(self):
                self._settings.setValue(f"discoverOnline/{key}", value)
                self.settingsChanged.emit()
                if refetch:
                    self._check(force=True, only=refetch)  # (only what this setting changes is asked again)
                elif reread:
                    self._queue_read()
        return Property(kind, get, notify=notify), Slot(kind)(set_)

    follow, setFollow = _prop("follow", "top50", str, settingsChanged, tuple(FOLLOW), refetch="releases")
    window, setWindow = _prop("window", 90, int, settingsChanged, WINDOWS, refetch="releases")
    albums, setAlbums = _prop("albums", True, bool, settingsChanged, reread=True)
    eps, setEps = _prop("eps", True, bool, settingsChanged, reread=True)
    singles, setSingles = _prop("singles", False, bool, settingsChanged, reread=True)
    live, setLive = _prop("live", False, bool, settingsChanged, reread=True)
    compilations, setCompilations = _prop("compilations", False, bool, settingsChanged, reread=True)
    notifyNew, setNotifyNew = _prop("notify", False, bool, settingsChanged)
    similarSource, setSimilarSource = _prop("similarSource", "listenbrainz", str, settingsChanged, SIMILAR_SOURCES,
                                            refetch="similar")
    seeds, setSeeds = _prop("seeds", 25, int, settingsChanged, SEEDS, refetch="similar")
    previews, setPreviews = _prop("previews", "deezer", str, settingsChanged, PREVIEWS)
    store, setStore = _prop("store", "bandcamp", str, settingsChanged, tuple(core.STORES))
    tickOff, setTickOff = _prop("tickOff", True, bool, settingsChanged)
    concertRadius, setConcertRadius = _prop("concertRadius", 50, int, settingsChanged, gigs.RADII, refetch="concerts")
    concertFollow, setConcertFollow = _prop("concertFollow", "top50", str, settingsChanged, tuple(CONCERT_FOLLOW),
                                            refetch="concerts")

    # --- concerts: where ------------------------------------------------------------------------------------
    @Property(str, notify=settingsChanged)
    def concertPlace(self):
        """The place as typed in."""
        return str(self._settings.value("discoverOnline/concertPlace", "") or "")

    @Property(str, notify=settingsChanged)
    def concertPlaceName(self):
        """Where that was found on the map ("" until it is)."""
        return str(self._settings.value("discoverOnline/concertPlaceName", "") or "") if self._point() else ""

    @Property(str, notify=settingsChanged)
    def concertPlaceStatus(self):
        return self._place_status

    def _point(self):
        try:
            lat = float(self._settings.value("discoverOnline/concertLat", ""))
            lon = float(self._settings.value("discoverOnline/concertLon", ""))
        except (TypeError, ValueError):
            return None
        return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None

    def _concert_place(self):
        point = self._point()
        return gigs.place_key(point[0], point[1], self.concertRadius) if point else ""

    @Slot(str)
    def setConcertPlace(self, text):
        """Finds the place typed in on the map (once), then looks for concerts near it."""
        text = " ".join(str(text).split())[:120]
        if text == self.concertPlace and (self._point() or self._place_status == "looking"):
            return
        self._settings.setValue("discoverOnline/concertPlace", text)
        for key in ("concertLat", "concertLon", "concertPlaceName"):
            self._settings.remove(f"discoverOnline/{key}")
        if not text:
            self._place_status = ""
        elif net.is_offline():
            self._place_status = translate("DiscoverOnline", "Offline mode is on, so the place can't be found")
        else:
            self._place_status = "looking"

            def find(_db):
                try:
                    self._placed.emit(text, gigs.geocode(text))
                except (OSError, ValueError) as exc:
                    self._placed.emit(text, net.describe(exc))
            self._jobs.put(("quiet", find))
        self.settingsChanged.emit()
        self._queue_read()

    @Slot(str, object)
    def _on_placed(self, text, found):
        if text != self.concertPlace:
            return  # (typed again since)
        if isinstance(found, dict):
            self._settings.setValue("discoverOnline/concertLat", found["lat"])
            self._settings.setValue("discoverOnline/concertLon", found["lon"])
            self._settings.setValue("discoverOnline/concertPlaceName", found["name"])
            self._place_status = ""
            self.settingsChanged.emit()
            self._check(force=True, only="concerts")
        else:
            self._place_status = "missing" if found is None else fill(
                translate("DiscoverOnline", "Couldn't look the place up: %1"), found)
            self.settingsChanged.emit()
        self._queue_read()

    @Slot()
    def _sources_changed(self):
        had, self._had_key = self._had_key, self.ticketmasterReady
        self.settingsChanged.emit()
        if self._had_key and not had:
            self._check(force=True, only="concerts")  # (a key just set up: look now)

    @Property(bool, notify=settingsChanged)
    def ticketmasterReady(self):
        return self._sources is not None and self._sources.ticketmasterConnected

    @Property("QVariantList", notify=changed)
    def concerts(self):
        return self._concerts

    def _on(self, name):
        return self._shell is not None and self._shell.featureOn(name)

    @Property("QVariantList", constant=True)
    def stores(self):
        """[{key, name}] for Settings' choice of where to look for a wish."""
        return [{"key": k, "name": v[0]} for k, v in core.STORES.items()]

    @Property(bool, notify=settingsChanged)
    def lastfmReady(self):
        return bool(self._sources is not None and self._sources.lastfm_key())

    # --- what the page shows --------------------------------------------------------------------------------
    @Property("QVariantList", notify=changed)
    def newReleases(self):
        """[{id, artist, title, kind, extra, date, cover (a file URL or ""), link, wished}], newest first."""
        return self._releases

    @Property("QVariantList", notify=changed)
    def similarArtists(self):
        """[{name, key, because, url, picture, wished}]: artists like yours you don't have."""
        return self._similar

    @Property("QVariantList", notify=wishlistChanged)
    def wishlist(self):
        """[{key, kind, artist, title, note, link, added, got}], still wanted first."""
        return self._wishlist

    @Property(bool, notify=changed)
    def offline(self):
        return net.is_offline()

    @Property(str, notify=progressChanged)
    def busy(self):
        """What's being looked up now (or waiting its turn): "releases", "similar" or ""."""
        return self._busy or (self._pending[0] if self._pending else "")

    @Property(int, notify=progressChanged)
    def done(self):
        return self._done

    @Property(int, notify=progressChanged)
    def total(self):
        return self._total

    # --- looking things up ----------------------------------------------------------------------------------
    @Slot()
    def open(self):
        """The Discover page is showing: read what's kept, and look up what's due."""
        self._wanted = True
        self._queue_read()
        self._check()

    @Slot()
    def refresh(self):
        """"Check now": look everything up again, whenever it was last done."""
        self._check(force=True)

    @Slot()
    def _features_changed(self):
        if not any(self._on(f) for f in FEATURES):
            self.stop()
        if not self._on("discoverSimilar"):
            self.stopPreview()
        self._queue_read()
        self._check()

    def _check(self, force=False, only=""):
        if self._closing or net.is_offline() or not (self._wanted or self._daily.isActive()):
            return
        self._read_opts = self._read_options()
        for feature, job in (("discoverNewReleases", "releases"), ("discoverSimilar", "similar"),
                             ("discoverConcerts", "concerts")):
            if only and job != only:
                continue
            if self._on(feature) and job in self._pending and force:
                self._again.add(job)  # (asked for afresh while one runs: once that's over)
            elif self._on(feature) and job not in self._pending:  # (one at a time: visiting again adds none)
                self._pending.append(job)
                self._jobs.put((job, {"force": bool(force), "generation": self._generation, "read": self._read_opts,
                                      **self._job_options(job)}))
        self.progressChanged.emit()

    @Slot(str)
    def _on_finished(self, job):
        if job in self._pending:
            self._pending.remove(job)
        self.progressChanged.emit()
        if job in self._again:
            self._again.discard(job)
            self._check(force=True, only=job)

    def _job_options(self, job):
        """What a lookup goes by, read here (settings aren't to be read from the worker)."""
        if job == "releases":
            return {"follow": FOLLOW[self.follow], "window": self.window}
        if job == "concerts":
            point = self._point() or (0.0, 0.0)
            key = self._sources.ticketmaster_key(0) if self._sources is not None else ""
            return {"key": key, "lat": point[0], "lon": point[1], "radius": self.concertRadius,
                    "place": self._concert_place(), "artists": CONCERT_FOLLOW[self.concertFollow]}
        key = self._sources.lastfm_key() if self._sources is not None else ""
        return {"source": self.similarSource, "seeds": self.seeds, "lastfm": key}

    @Slot()
    def stop(self):
        """Stop looking things up (what's found so far stays): the lookup going now, and any waiting its turn."""
        self._generation += 1
        self._again.clear()
        if self._busy or self._pending:
            self._stop.set()

    def _read_options(self):
        kinds = [k for k, on in (("Album", self.albums), ("EP", self.eps), ("Single", self.singles)) if on]
        since = (datetime.date.today() - datetime.timedelta(days=self.window)).isoformat()
        return {"kinds": kinds, "since": since, "live": self.live, "compilations": self.compilations,
                "source": self.similarSource, "seeds": self.seeds, "releases": self._on("discoverNewReleases"),
                "similar": self._on("discoverSimilar"), "concerts": self._on("discoverConcerts"),
                "place": self._concert_place()}

    def _work(self):
        db = None
        while True:
            job, options = self._jobs.get()
            if job is None:
                break
            lookup = job in ("releases", "similar", "concerts")
            try:
                if lookup and options["generation"] != self._generation:
                    continue  # (stopped before its turn came)
                if db is None:
                    db = Database(self._db_path)
                if job == "releases":
                    self._look_up_releases(db, options)
                elif job == "similar":
                    self._look_up_similar(db, options)
                elif job == "concerts":
                    self._look_up_concerts(db, options)
                elif job == "tick":
                    self._ticked.emit(core.tick_off(db, time.time()))
                elif job == "quiet":
                    options(db)  # (a preview's lookup: the shelves needn't be read again)
                    continue
                elif callable(job):
                    job(db)
                self._read(db)
            except Exception:  # noqa: BLE001 - one bad answer mustn't stop the worker
                logger.exception("Discover couldn't look that up")
            finally:
                if lookup:
                    self._progress.emit("", 0, 0)
                    self._stop.clear()
                    self._finished.emit(job)
        if db is not None:
            db.close()

    def _read(self, db):
        opts = self._read_opts
        releases = core.recent_releases(db, opts["since"], opts["kinds"], opts["live"], opts["compilations"]) \
            if opts["releases"] else []
        similar = self._suggestions(db, opts) if opts["similar"] else []
        self._wishes.emit(core.wishes(db))  # (first: the shelves mark what's on it)
        shows = gigs.upcoming(db, opts["place"]) if opts["concerts"] and opts["place"] else []
        self._found.emit({"releases": releases, "similar": similar, "concerts": shows})

    _read_opts = {"kinds": [], "since": "9999", "live": False, "compilations": False, "source": "listenbrainz",
                  "seeds": 25, "releases": False, "similar": False, "concerts": False, "place": ""}

    def _queue_read(self):
        self._read_opts = self._read_options()
        self._jobs.put(("read", None))

    def _stopped(self, o):
        return self._stop.is_set() or self._closing or net.is_offline() or o["generation"] != self._generation

    def _look_up_releases(self, db, o):
        artists = core.top_artists(db, o["follow"])
        now = time.time()
        due = [(k, n) for k, n in artists if o["force"] or now - core.releases_checked(db, k) > RELEASES_EVERY_S]
        since = (datetime.date.today() - datetime.timedelta(days=max(WINDOWS))).isoformat()
        for i, (key, name) in enumerate(due):
            if self._stopped(o):
                break
            self._progress.emit("releases", i, len(due))
            first = core.releases_checked(db, key) == 0
            mbid = self._mbid(db, key, name, now)
            if not mbid:
                core.store_releases(db, key, [], now)  # (checked: not asked again until tomorrow)
                continue
            try:
                found = core.releases_since(mbid, since)
            except (OSError, ValueError) as exc:
                logger.info("Couldn't look up %s's releases: %s", name, exc)
                continue
            core.store_releases(db, key, found, now)
            if first:  # (an artist looked at for the first time: their past year isn't news)
                core.mark_seen(db, [r["id"] for r in found])
        # what the shelf shows: news (for the notification) and covers, only for those
        r = o["read"]
        shown = core.recent_releases(db, r["since"], r["kinds"], r["live"], r["compilations"])
        fresh = [x for x in shown if not x["seen"]]
        if fresh:
            self._notify_new(len(fresh))
        db.conn.execute("UPDATE new_releases SET seen = 1")
        db.conn.commit()
        folder = os.path.join(self._art_dir, "online")
        for x in shown:
            if not x["cover"] and not self._stopped(o):
                path = core.fetch_image(core.cover_url(x["id"]), folder)
                if path:
                    core.set_release_cover(db, x["id"], path)

    def _mbid(self, db, key, name, now):
        mbid, looked = core.known_mbid(db, key)
        if mbid is None or (not mbid and now - looked > MBID_AGAIN_S):
            try:
                mbid = core.artist_id(name)
            except (OSError, ValueError) as exc:
                logger.info("Couldn't look up %s on MusicBrainz: %s", name, exc)
                return ""
            core.remember_mbid(db, key, name, mbid, now)
        return mbid

    def _look_up_similar(self, db, o):
        source = o["source"]
        if source == "lastfm" and not o["lastfm"]:
            return
        seeds = core.top_artists(db, o["seeds"])
        now = time.time()
        due = [(k, n) for k, n in seeds if o["force"] or now - core.similar_fetched(db, k, source) > SIMILAR_EVERY_S]
        for i, (key, name) in enumerate(due):
            if self._stopped(o):
                break
            self._progress.emit("similar", i, len(due))
            try:
                if source == "listenbrainz":
                    mbid = self._mbid(db, key, name, now)
                    names = core.similar_listenbrainz(mbid) if mbid else []
                elif source == "deezer":
                    names = core.similar_deezer(name)
                else:
                    names = core.similar_lastfm(name, o["lastfm"])
            except (OSError, ValueError) as exc:
                logger.info("Couldn't look up artists like %s: %s", name, exc)
                continue
            core.store_similar(db, key, source, names, now)
        # pictures only for the artists the shelf shows (each artist's list has dozens)
        folder = os.path.join(self._art_dir, "online")
        for s in core.suggestions(db, core.top_artists(db, o["seeds"]), source):
            if s.get("picture") and not self._stopped(o):
                core.fetch_image(s["picture"], folder)

    def _look_up_concerts(self, db, o):
        if not o["key"] or not o["place"]:
            return
        now = time.time()
        artists = core.top_artists(db, o["artists"])
        due = [(k, n) for k, n in artists if o["force"] or now - gigs.checked(db, k, o["place"]) > CONCERTS_EVERY_S]
        for i, (key, name) in enumerate(due):
            if self._stopped(o):
                break
            self._progress.emit("concerts", i, len(due))
            try:
                found = gigs.shows(name, o["key"], o["lat"], o["lon"], o["radius"])
            except gigs.BadKey:
                self._progress.emit("badkey", 0, 0)
                return
            except (OSError, ValueError) as exc:
                logger.info("Couldn't look up %s's concerts: %s", name, exc)
                continue
            gigs.store(db, key, o["place"], found, now)
            time.sleep(TICKETMASTER_GAP_S)

    def _suggestions(self, db, opts):
        """The shelf's artists, with their pictures as files here (when they've been fetched)."""
        folder = os.path.join(self._art_dir, "online")
        out = core.suggestions(db, core.top_artists(db, opts["seeds"]), opts["source"])
        for s in out:
            s["picture"] = core.cached_image(s.get("picture", ""), folder)
        return out

    def _notify_new(self, count):
        self._progress.emit("notify", count, 0)  # (said on the window's thread, where the setting is read)

    @Slot(str, int, int)
    def _on_progress(self, what, done, total):
        if what == "badkey":
            self.message.emit(translate("DiscoverOnline", "Ticketmaster didn't accept the key: check it in Settings → Discover"))
            return
        if what == "notify":
            if self.notifyNew and self._shell is not None:
                self._shell.notify(translate("DiscoverOnline", "New releases"),
                                   translate("DiscoverOnline", "%n new release(s) by artists you play", None, done))
            return
        if (what, done, total) != (self._busy, self._done, self._total):
            self._busy, self._done, self._total = what, done, total
            self.progressChanged.emit()

    @Slot(object)
    def _on_found(self, data):
        wished = {w["key"] for w in self._wishlist}
        releases = []
        for r in data["releases"]:
            releases.append({"id": r["id"], "artist": r["artist"], "title": r["title"], "kind": r["kind"],
                             "extra": r["extra"], "date": r["date"], "link": core.release_link(r["id"]),
                             "cover": QUrl.fromLocalFile(r["cover"]).toString() if r["cover"] else "",
                             "wished": core.wish_key("album", r["artist"], r["title"]) in wished})
        similar = [{**s, "picture": QUrl.fromLocalFile(s["picture"]).toString() if s.get("picture") else "",
                    "wished": core.wish_key("artist", s["name"]) in wished} for s in data["similar"]]
        self._releases, self._similar = releases, similar
        self._concerts = [dict(c) for c in data.get("concerts", [])]
        self.changed.emit()

    # --- not interested -------------------------------------------------------------------------------------
    @Slot(str, str)
    def notInterestedRelease(self, rid, label):
        self._write(lambda db: dcore.dismiss(db, "release", rid, label))
        self.message.emit(fill(translate("DiscoverOnline", "“%1” won't be shown again"), label))

    @Slot(str, str)
    def notInterestedArtist(self, name, label=""):
        key = core.fold(name).strip()
        self._write(lambda db: dcore.dismiss(db, "artist", key, label or name))
        self.message.emit(fill(translate("DiscoverOnline", "“%1” won't be suggested again"), label or name))

    def _write(self, fn):
        self._read_opts = self._read_options()
        self._jobs.put((fn, None))

    # --- the wishlist ---------------------------------------------------------------------------------------
    @Slot(str, str, str, str, str)
    def addWish(self, kind, artist, title, link="", ref=""):
        self._write(lambda db: core.wish(db, kind, artist, title, link=link, ref=ref, now=time.time()))
        what = fill(translate("DiscoverOnline", "%1 by %2"), title, artist) if kind == "album" and title else artist
        self.message.emit(fill(translate("DiscoverOnline", "“%1” is on your wishlist"), what))

    @Slot(str)
    def removeWish(self, key):
        self._write(lambda db: core.unwish(db, key))

    @Slot(str, str)
    def setWishNote(self, key, note):
        self._write(lambda db: core.set_note(db, key, note))

    @Slot(str, str, str)
    def lookFor(self, artist, title=""):
        """Opens a search for it at the store chosen in Settings."""
        QDesktopServices.openUrl(QUrl(core.store_link(self.store, artist, title)))

    @Slot(str)
    def openLink(self, link):
        if link.startswith("https://"):
            QDesktopServices.openUrl(QUrl(link))

    @Slot(object)
    def _on_wishes(self, rows):
        self._wishlist = rows
        self.wishlistChanged.emit()

    @Slot()
    def libraryChanged(self):
        """After a scan: tick off wishes that are in the library now (if that's on)."""
        if self.tickOff:
            self._read_opts = self._read_options()
            self._jobs.put(("tick", None))

    @Slot(object)
    def _on_ticked(self, got):
        for w in got[:3]:
            what = fill(translate("DiscoverOnline", "%1 by %2"), w["title"], w["artist"]) if w["kind"] == "album" else w["artist"]
            self.message.emit(fill(translate("DiscoverOnline", "“%1” from your wishlist is in your library now"), what))

    @Slot()
    def forget(self):
        """Throws away what was found online (the wishlist stays)."""
        self.stop()
        self._write(lambda db: (core.forget(db), gigs.forget(db)))

    # --- previews -------------------------------------------------------------------------------------------
    @Property(str, notify=previewChanged)
    def previewing(self):
        """The artist whose preview is playing (or being fetched), or ""."""
        return self._preview_name

    @Property(str, notify=previewChanged)
    def previewTitle(self):
        return self._preview_title

    @Slot(str)
    def preview(self, artist):
        """Plays a 30-second preview of the artist's best known song (again: stops it)."""
        if self._preview_name == artist:
            self.stopPreview()
            return
        if self.previews == "off" or net.is_offline():
            return
        self.stopPreview()
        self._preview_name, self._preview_title = artist, ""
        self.previewChanged.emit()
        source = self.previews

        def work(_db):
            try:
                self._preview_ready.emit((artist, core.preview(artist, source)))
            except (OSError, ValueError) as exc:
                logger.info("Couldn't find a preview of %s: %s", artist, exc)
                self._preview_ready.emit((artist, None))
        self._jobs.put(("quiet", work))

    @Slot(object)
    def _on_preview(self, payload):
        artist, found = payload
        if artist != self._preview_name:
            return  # (another was asked for meanwhile)
        if not found:
            self._preview_name = ""
            self.previewChanged.emit()
            self.message.emit(fill(translate("DiscoverOnline", "No preview of %1 found"), artist))
            return
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        if self._preview is None:
            out = QAudioOutput(self)
            p = QMediaPlayer(self)
            p.setAudioOutput(out)
            p.mediaStatusChanged.connect(self._preview_status)
            p.errorOccurred.connect(lambda *_: self.stopPreview())
            self._preview = (p, out)
        p, out = self._preview
        if self._player is not None:
            out.setVolume(max(0.05, min(1.0, float(self._player.volume or 0.8))))  # (as loud as the music was)
            self._resume = bool(self._player.playing)
            if self._resume:
                self._player.pause()
        self._preview_title = found["title"]
        self.previewChanged.emit()
        p.setSource(QUrl(found["url"]))
        p.play()

    def _preview_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.stopPreview()

    @Slot()
    def stopPreview(self):
        if self._preview is not None:
            self._preview[0].stop()
            self._preview[0].setSource(QUrl())
        was = bool(self._preview_name)
        self._preview_name, self._preview_title = "", ""
        if was:
            self.previewChanged.emit()
        if self._resume and self._player is not None:
            self._resume = False
            self._player.play()

    def shutdown(self):
        self._closing = True
        self._stop.set()
        self._daily.stop()
        if self._preview is not None:
            self._preview[0].stop()
        self._jobs.put((None, None))
        self._thread.join(timeout=3)
