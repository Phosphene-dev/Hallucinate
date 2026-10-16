"""Tag editing and cover art management for QML. All file and network work happens on worker threads."""
import hashlib
import logging
import os
import threading
import time
from urllib.parse import unquote, urlparse

from PySide6.QtCore import Property, QObject, Signal, Slot

from .core import artfetch, health, net, tagedit
from .core.db import Database
from .core.scanner import Scanner
from .core.tags import _image_ext
from .library import _Reader, decorate

logger = logging.getLogger(__name__)


def _local_path(url):
    if url.startswith("file:"):
        return unquote(urlparse(url).path) if os.name != "nt" else unquote(urlparse(url).path).lstrip("/")
    return url


MUSICBRAINZ_INTERVAL = 1.1  # MusicBrainz asks for at most one request per second


class MetadataEditor(QObject):
    busyChanged = Signal()
    coversChanged = Signal()
    _covers_progress = Signal(object)
    changed = Signal()  # tracks or art were modified; reload the library
    saved = Signal(int)
    failed = Signal(str)
    coverResult = Signal(bool, str)
    lookupResults = Signal("QVariantList", str)  # MusicBrainz releases matching an album, or [] and why
    releaseReady = Signal("QVariantMap")  # a chosen release: {fields, tracks, matched, error}
    _mb_done = Signal(object)
    _done = Signal(object)

    def __init__(self, db_path, art_dir, parent=None):
        super().__init__(parent)
        self._reader = _Reader(str(db_path), "metaedit")
        self._art_dir = str(art_dir)
        self._busy = 0
        self._done.connect(self._finish)
        self._db_path = str(db_path)
        self._covers = {"busy": False, "done": 0, "total": 0, "found": 0, "current": ""}
        self._covers_stop = threading.Event()
        self._mb_done.connect(self._on_mb_done)
        self._covers_thread = None
        self._covers_progress.connect(self._apply_covers_progress)

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy > 0

    def _run(self, fn, *args):
        self._busy += 1
        self.busyChanged.emit()

        def work(db):
            try:
                result = fn(db, *args)
            except tagedit.TagWriteError as exc:
                result = {"error": str(exc)}
            except OSError as exc:
                result = {"error": f"{exc.strerror or exc}"}
            except Exception as exc:  # noqa: BLE001
                logger.exception("Metadata operation failed")
                result = {"error": str(exc)}
            self._done.emit(result)

        self._reader.submit(work)

    @Slot(object)
    def _finish(self, result):
        self._busy -= 1
        self.busyChanged.emit()
        kind = result.get("kind")
        if kind == "tags":
            if result.get("errors"):
                self.failed.emit("; ".join(result["errors"][:3]))
            if result.get("saved"):
                self.saved.emit(result["saved"])
                self.changed.emit()
        elif kind == "cover":
            self.coverResult.emit(result["ok"], result["message"])
            if result["ok"]:
                self.changed.emit()
        elif "error" in result:
            self.failed.emit(result["error"])
            self.coverResult.emit(False, result["error"])

    # --- tag editing -----------------------------------------------------------------
    @Slot(str, result="QVariantMap")
    def trackInfo(self, path):
        row = self._reader.submit(lambda db: db.track_by_path(path)).result(timeout=10)
        return decorate([row])[0] if row else {}

    # --- MusicBrainz -------------------------------------------------------------------------------------
    @Slot(str, str)
    def lookupAlbum(self, artist, album):
        """Find releases matching an album on MusicBrainz; lookupResults() reports back."""
        from .core import musicbrainz, net

        if net.is_offline():
            self.lookupResults.emit([], "Offline mode is on, so MusicBrainz can't be searched")
            return
        if not (album or "").strip():
            self.lookupResults.emit([], "The album needs a name to look it up")
            return

        def work():
            try:
                found = musicbrainz.search_releases(artist, album)
                self._mb_done.emit(("results", found, "" if found else "MusicBrainz has no album by that name"))
            except (OSError, ValueError, KeyError) as exc:
                self._mb_done.emit(("results", [], f"Couldn't reach MusicBrainz: {net.describe(exc)}"))

        threading.Thread(target=work, name="musicbrainz", daemon=True).start()

    @Slot(str, str)
    def chooseRelease(self, release_id, album_key):
        """Fetch a release and pair its tracks with the album's songs (by disc and track order, when the
        counts agree); releaseReady() hands over what to fill in."""
        from .core import musicbrainz

        songs = self._reader.submit(lambda db: db.album_tracks(album_key)).result(timeout=10) if album_key else []

        def work():
            try:
                rel = musicbrainz.release(release_id)
            except (OSError, ValueError, KeyError) as exc:
                self._mb_done.emit(("release", {"error": f"Couldn't fetch that release: {net.describe(exc)}"}, ""))
                return
            pairs = musicbrainz.match_tracks([dict(s) for s in songs], rel["tracks"])
            self._mb_done.emit(("release", {
                "fields": {"album": rel["title"], "album_artist": rel["artist"], "year": rel["year"], "genre": rel["genre"]},
                "tracks": [{"path": p, "title": t["title"], "track_no": t["number"],
                            "disc_no": t["disc"] if rel["discs"] > 1 else 0, "artist": t["artist"]} for p, t in pairs],
                "matched": len(pairs), "songs": len(songs), "releaseTracks": len(rel["tracks"]), "error": "",
            }, ""))

        threading.Thread(target=work, name="musicbrainz", daemon=True).start()

    @Slot(object)
    def _on_mb_done(self, result):
        kind, value, message = result
        if kind == "results":
            self.lookupResults.emit(value, message)
        else:
            self.releaseReady.emit(value)

    @Slot("QVariantList")
    def saveTrackTags(self, items):
        """Write each song its own tags: [{path, title, track_no, disc_no, artist}] (from a MusicBrainz match)."""
        items = [dict(i) for i in items]

        def save_each(db, rows):
            total = {"kind": "tags", "saved": 0, "errors": []}
            for row in rows:
                path = row.pop("path")
                fields = {k: str(v) for k, v in row.items() if v not in (None, "", 0)}
                result = self._save_tags(db, [path], fields)
                total["saved"] += result["saved"]
                total["errors"] += result["errors"]
            return total

        self._run(save_each, items)

    @Slot("QVariantList", "QVariantMap")
    def saveTags(self, paths, fields):
        paths, fields = list(paths), dict(fields)
        self._run(self._save_tags, paths, fields)

    def _save_tags(self, db, paths, fields):
        errors, ok = [], []
        for path in paths:
            try:
                tagedit.write_tags(path, fields)
                ok.append(path)
            except tagedit.TagWriteError as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
        if ok:
            Scanner(db, self._art_dir).refresh_files(ok)
        return {"kind": "tags", "saved": len(ok), "errors": errors}

    # --- cover art -----------------------------------------------------------------------
    def _store_cover(self, db, album_key, data, embed):
        if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"):
            raise tagedit.TagWriteError("Not a PNG or JPEG image")
        name = f"{album_key}-{hashlib.sha1(data).hexdigest()[:8]}{_image_ext(data)}"
        path = os.path.join(self._art_dir, name)
        os.makedirs(self._art_dir, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        db.set_album_art(album_key, path)
        db.commit()
        problems = []
        if embed:
            for t in db.album_tracks(album_key):
                try:
                    tagedit.embed_cover(t["path"], data)
                except tagedit.TagWriteError as exc:
                    problems.append(f"{os.path.basename(t['path'])}: {exc}")
            Scanner(db, self._art_dir).refresh_files([t["path"] for t in db.album_tracks(album_key)])
        msg = "Cover updated" + (f" (could not embed in: {'; '.join(problems[:2])})" if problems else "")
        return {"kind": "cover", "ok": True, "message": msg}

    @Slot(str, str, bool)
    def setCoverFromFile(self, album_key, url, embed):
        self._run(lambda db, k, u, e: self._store_cover(db, k, open(_local_path(u), "rb").read(artfetch.MAX_BYTES), e),
                  album_key, url, embed)

    @Slot(str, str, str, bool)
    def fetchCover(self, album_key, artist, album, embed):
        def work(db, key, art, alb, emb):
            try:
                data = artfetch.fetch_cover(art, alb)
            except artfetch.ServiceError as exc:  # their servers, already worded for people
                return {"kind": "cover", "ok": False, "message": str(exc)}
            except OSError as exc:
                return {"kind": "cover", "ok": False, "message": f"Couldn't fetch the cover: {net.describe(exc)}"}
            if not data:
                return {"kind": "cover", "ok": False, "message": "No cover found online"}
            return self._store_cover(db, key, data, emb)

        self._run(work, album_key, artist, album, embed)

    # --- every missing cover at once ---------------------------------------------------
    @Property(bool, notify=coversChanged)
    def coversBusy(self):
        return self._covers["busy"]

    @Property(int, notify=coversChanged)
    def coversDone(self):
        return self._covers["done"]

    @Property(int, notify=coversChanged)
    def coversTotal(self):
        return self._covers["total"]

    @Property(int, notify=coversChanged)
    def coversFound(self):
        return self._covers["found"]

    @Property(str, notify=coversChanged)
    def coversCurrent(self):
        return self._covers["current"]

    @Slot()
    def fetchMissingCovers(self):
        """Look up every album without a cover online, one by one (MusicBrainz allows a request a second)."""
        if self._covers["busy"]:
            return
        self._covers_stop.clear()
        self._covers = {"busy": True, "done": 0, "total": 0, "found": 0, "current": ""}
        self.coversChanged.emit()
        self._covers_thread = threading.Thread(target=self._fetch_covers, name="covers", daemon=True)
        self._covers_thread.start()

    @Slot()
    def cancelCovers(self):
        self._covers_stop.set()

    def _fetch_covers(self, sleep=time.sleep):
        db = Database(self._db_path)
        found = done = 0
        try:
            albums = [a for a in health.missing_covers_all(db)
                      if (a.get("album") or "").strip() and a.get("album") != health.UNKNOWN_ALBUM]
            self._covers_progress.emit({"total": len(albums)})
            last = 0.0
            for album in albums:
                if self._covers_stop.is_set() or net.is_offline():
                    break
                self._covers_progress.emit({"current": album["album"]})
                wait = MUSICBRAINZ_INTERVAL - (time.monotonic() - last)
                if wait > 0:
                    sleep(wait)
                last = time.monotonic()
                try:
                    data = artfetch.fetch_cover(album.get("album_artist") or "", album["album"])
                    if data:
                        self._store_cover(db, album["album_key"], data, False)
                        found += 1
                except (OSError, tagedit.TagWriteError) as exc:
                    logger.info("No cover for %s: %s", album["album"], exc)
                done += 1
                self._covers_progress.emit({"done": done, "found": found, "reload": bool(found) and found % 10 == 0})
        except Exception:  # noqa: BLE001
            logger.exception("Fetching covers failed")
        finally:
            db.close()
            self._covers_progress.emit({"busy": False, "current": "", "reload": found > 0, "finished": True})

    @Slot(object)
    def _apply_covers_progress(self, update):
        reload_ = update.pop("reload", False)
        finished = update.pop("finished", False)
        self._covers.update(update)
        self.coversChanged.emit()
        if reload_:
            self.changed.emit()
        if finished:
            self.coverResult.emit(True, f"Found {self._covers['found']} of {self._covers['done']} covers")

    def shutdown(self):
        self._covers_stop.set()
        if self._covers_thread is not None:
            self._covers_thread.join(timeout=2)
        self._reader.close()
