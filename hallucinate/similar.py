"""Similar artists on the artist page, from Last.fm (with the API key set up for scrobbling): those in your
library to go to, the rest to discover, and a mix of the artist with the ones you have.

Off until switched on (Settings → Online & privacy). Lookups run one at a time on a worker and are kept in the
library for a month; the results are written on the window's thread."""
import json
import logging
import queue
import threading
import time

from PySide6.QtCore import QObject, Signal, Slot

from .core import net
from .core.db import Database, fold

logger = logging.getLogger(__name__)
KEEP_S = 30 * 86_400  # asked again after a month
NOT_ARTISTS = {"", "unknown artist", "various artists", "various", "va"}

SCHEMA = """CREATE TABLE IF NOT EXISTS similar_artists(s_aa TEXT PRIMARY KEY, names TEXT NOT NULL DEFAULT '[]',
  fetched REAL NOT NULL DEFAULT 0)"""


class SimilarArtists(QObject):
    changed = Signal(str)  # the folded artist name whose list changed
    _found = Signal(str, object)  # key, [{name, match}] — or None when Last.fm couldn't be reached

    def __init__(self, db_path, sources=None, library=None, parent=None):
        super().__init__(parent)
        self._db = Database(str(db_path))
        self._db.conn.execute(SCHEMA)
        self._db.conn.commit()
        self._sources = sources
        self._library = library  # to tell which of them you have (its artists, by folded name)
        self._jobs = queue.Queue()
        self._busy = set()
        self._closing = False
        self._found.connect(self._on_found)
        self._thread = threading.Thread(target=self._work, name="similar-artists", daemon=True)
        self._thread.start()

    def _enabled(self):
        src = self._sources
        return bool(src and src.fetchSimilar and src.lastfm_key())

    def _row(self, key):
        return self._db.conn.execute("SELECT names, fetched FROM similar_artists WHERE s_aa=?", (key,)).fetchone()

    @Slot(str, result="QVariantMap")
    def similar(self, name):
        """{have: [{name, albums, tracks, artUrl, match}] (in your library), discover: [{name, match, url}]
        (not), busy, asked (looked up at least once), on (switched on and set up)}."""
        key = fold(name)
        r = self._row(key)
        names = []
        if r:
            try:
                names = json.loads(r["names"]) or []
            except ValueError:
                names = []
        have, discover = [], []
        lookup = self._library.artistInfo if self._library is not None else None
        for s in names:
            info = lookup(s["name"]) if lookup else {}
            if info and info.get("tracks"):
                have.append({**info, "match": s.get("match", 0)})
            else:
                discover.append({"name": s["name"], "match": s.get("match", 0),
                                 "url": "https://www.last.fm/music/" + _quote(s["name"])})
        return {"have": have, "discover": discover[:24], "busy": key in self._busy, "asked": bool(r),
                "on": self._enabled()}

    @Slot(str)
    def ensure(self, name):
        """The artist's page opened: look them up if they never have been, or not for a month."""
        key = fold(name)
        if key in NOT_ARTISTS or not self._enabled() or net.is_offline():
            return
        r = self._row(key)
        if r and time.time() - r["fetched"] < KEEP_S:
            return
        self._ask(name)

    @Slot(str)
    def refresh(self, name):
        if fold(name) not in NOT_ARTISTS and self._enabled() and not net.is_offline():
            self._ask(name)

    def _ask(self, name):
        key = fold(name)
        if key in self._busy:
            return
        self._busy.add(key)
        self.changed.emit(key)
        self._jobs.put((key, name, self._sources.lastfm_key()))

    def _work(self):
        from .core import lastfm

        while True:
            job = self._jobs.get()
            if job is None:
                return
            key, name, api_key = job
            try:
                self._found.emit(key, lastfm.similar_artists(name, api_key))
            except (OSError, ValueError) as exc:
                logger.info("Couldn't look up similar artists: %s", exc)
                self._found.emit(key, None)
            except Exception:  # noqa: BLE001 - one artist's odd answer mustn't stop the worker
                logger.exception("Looking up similar artists failed")
                self._found.emit(key, None)

    @Slot(str, object)
    def _on_found(self, key, found):
        self._busy.discard(key)
        if self._closing:
            return
        if found is not None:  # (a network failure isn't remembered as "none")
            self._db.conn.execute(
                "INSERT INTO similar_artists(s_aa, names, fetched) VALUES(?, ?, ?) ON CONFLICT(s_aa) DO UPDATE SET "
                "names=excluded.names, fetched=excluded.fetched", (key, json.dumps(found), time.time()))
            self._db.conn.commit()
        self.changed.emit(key)

    def shutdown(self):
        self._closing = True
        self._jobs.put(None)
        self._thread.join(timeout=2)
        self._db.close()


def _quote(name):
    import urllib.parse

    return urllib.parse.quote(name.replace(" ", "+"), safe="+")
