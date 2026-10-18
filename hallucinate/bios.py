"""Artist bios on the artist page: one you write yourself always comes first; otherwise one looked up online
(Wikipedia through MusicBrainz, Last.fm or Discogs), kept in the library so it's fetched once.

Lookups run one at a time on a worker; the results are written on the window's thread."""
import logging
import queue
import threading
import time

from PySide6.QtCore import Property, QLocale, QObject, Signal, Slot

from .core import net
from .core.db import Database, fold
from .onlinesources import BIO_SOURCES

logger = logging.getLogger(__name__)
MAX_LEN = 10_000
RETRY_S = 30 * 86_400  # an artist nobody had a bio for is asked about again after a month
REFRESH_S = 180 * 86_400  # and a bio found is refreshed after half a year
NOT_ARTISTS = {"", "unknown artist", "various artists", "various", "va"}


def lookup(name, album, sources, discogs_token="", lastfm_key="", lang="en"):
    """The first bio found among `sources` (in order): {"text", "url", "source"} or None. Raises OSError when
    no source could be reached at all (so "nothing found" isn't remembered for a network failure)."""
    from .core import discogs, lastfm, wikipedia

    tries = {
        "Wikipedia": lambda: wikipedia.artist_bio(name, album, lang),
        "Last.fm": lambda: lastfm.artist_bio(name, lastfm_key, lang) if lastfm_key else None,
        "Discogs": lambda: discogs.artist_bio(name, discogs_token, album) if discogs_token else None,
    }
    failed, asked = 0, 0
    for source in sources:
        if source not in tries:
            continue
        asked += 1
        try:
            found = tries[source]()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.info("No bio from %s: %s", source, exc)
            failed += 1
            continue
        if found and found.get("text"):
            found["text"] = found["text"][:MAX_LEN]
            return found
    if asked and failed == asked:
        raise OSError("no source could be reached")
    return None


class ArtistBios(QObject):
    changed = Signal(str)  # the folded artist name whose bio changed
    _found = Signal(str, object)  # key, (bio dict or None) — or "error" for a network failure

    def __init__(self, db_path, sources=None, parent=None):
        super().__init__(parent)
        self._db = Database(str(db_path))
        self._sources = sources
        self._jobs = queue.Queue()
        self._busy = set()
        self._tried = {}  # the one source asked, when only one was (remembered with "nothing found")
        self._lang = (QLocale().name() or "en")[:2].lower()
        self._found.connect(self._on_found)
        self._closing = False
        self._thread = threading.Thread(target=self._work, name="artist-bios", daemon=True)
        self._thread.start()

    def _row(self, key):
        return self._db.conn.execute("SELECT * FROM artist_bios WHERE s_aa=?", (key,)).fetchone()

    @Slot(str, result="QVariantMap")
    def bio(self, name):
        """{text, own (it's yours), source, url, picked, busy}."""
        key = fold(name)
        r = self._row(key)
        own = r["own"] if r else ""
        return {"text": own or (r["text"] if r else ""), "own": bool(own), "source": "" if own else (r["source"] if r else ""),
                "url": "" if own else (r["url"] if r else ""), "picked": r["picked"] if r else "",
                "fetchedText": r["text"] if r else "", "busy": key in self._busy}

    def _order(self, picked):
        src = self._sources
        ready = {s["name"] for s in src.bioSources if s["ready"]} if src else {"Wikipedia"}
        if picked:
            return [picked] if picked in ready else []
        first = src.bioSource if src else ""
        if first:  # "Last.fm only": the others aren't asked
            return [first] if first in ready else []
        return [s for s in BIO_SOURCES if s in ready]

    @Slot(str)
    def ensure(self, name):
        """The artist's page opened: look their bio up if it's never been, or not for a long time."""
        if not (name or "").strip() or (self._sources and not self._sources.fetchBios) or net.is_offline():
            return
        key = fold(name)
        if key in NOT_ARTISTS:
            return
        r = self._row(key)
        if r and r["own"]:
            return
        if r and r["fetched"]:
            age = time.time() - r["fetched"]
            wanted = r["picked"] or ""
            if (r["text"] and age < REFRESH_S and (not wanted or r["source"] == wanted)) or \
                    (not r["text"] and age < RETRY_S and r["source"] in ("", wanted)):
                return
        self._ask(name)

    @Slot(str)
    def refresh(self, name):
        """Look it up again now (the source may have more, or you changed where bios come from)."""
        if (name or "").strip() and not net.is_offline():
            self._ask(name)

    def _ask(self, name):
        key = fold(name)
        if key in self._busy:
            return
        r = self._row(key)
        order = self._order(r["picked"] if r else "")
        if not order:
            return
        src = self._sources
        token = src.discogs_token(0) if src and "Discogs" in order else ""
        lastfm_key = src.lastfm_key() if src and "Last.fm" in order else ""
        album = self._db.conn.execute(
            """SELECT MIN(album) FROM tracks WHERE s_aa=? AND album != '' GROUP BY album_key
               ORDER BY COUNT(*) DESC LIMIT 1""", (key,)).fetchone()
        self._busy.add(key)
        self.changed.emit(key)
        self._tried[key] = order[0] if len(order) == 1 else ""
        self._jobs.put((key, name, album[0] if album else "", order, token, lastfm_key))

    def _work(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return
            key, name, album, order, token, lastfm_key = job
            try:
                self._found.emit(key, lookup(name, album, order, token, lastfm_key, self._lang))
            except OSError as exc:
                logger.info("Couldn't look up a bio: %s", exc)
                self._found.emit(key, "error")
            except Exception:  # noqa: BLE001 - one artist's odd answer mustn't stop the worker
                logger.exception("Looking up a bio failed")
                self._found.emit(key, "error")

    @Slot(str, object)
    def _on_found(self, key, found):
        self._busy.discard(key)
        if self._closing:
            return
        if found != "error":
            found = found or {}
            self._db.conn.execute(
                "INSERT INTO artist_bios(s_aa, text, source, url, fetched) VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(s_aa) DO UPDATE SET text=excluded.text, source=excluded.source, url=excluded.url, "
                "fetched=excluded.fetched",
                (key, found.get("text", ""), found.get("source", "") or self._tried.get(key, ""), found.get("url", ""),
                 time.time()))
            self._db.conn.commit()
        self.changed.emit(key)

    @Slot(str, str)
    def setOwn(self, name, text):
        """Your own bio for the artist ("" goes back to the one fetched)."""
        key = fold(name)
        if not key:
            return
        text = (text or "").strip()[:MAX_LEN]
        self._db.conn.execute(
            "INSERT INTO artist_bios(s_aa, own) VALUES(?, ?) ON CONFLICT(s_aa) DO UPDATE SET own=excluded.own",
            (key, text))
        self._db.conn.commit()
        self.changed.emit(key)

    @Slot(str, str)
    def pick(self, name, source):
        """Where this artist's bio comes from ("" for the usual order), then look it up from there."""
        key = fold(name)
        if not key:
            return
        source = source if source in BIO_SOURCES else ""
        self._db.conn.execute(
            "INSERT INTO artist_bios(s_aa, picked) VALUES(?, ?) ON CONFLICT(s_aa) DO UPDATE SET picked=excluded.picked",
            (key, source))
        self._db.conn.commit()
        self.changed.emit(key)
        if not self._sources or self._sources.fetchBios:
            self.refresh(name)

    @Property(str, constant=True)
    def language(self):
        return self._lang

    def shutdown(self):
        self._closing = True
        self._jobs.put(None)
        self._thread.join(timeout=2)
        self._db.close()
