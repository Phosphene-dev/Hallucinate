"""Songs from a music server kept on this computer: an album, a playlist or a few songs you chose, downloaded
once so they play without the server, the network or offline mode getting in the way (see remote.local_copy).

Copies are kept in their own folder and only there; removing one deletes only its file. Downloads run one at a
time on a worker. One stopped part-way (the app closed, offline mode, a dropped connection) carries on where it
got to next time, as podcast downloads do; songs still to fetch are remembered until they're done."""
import hashlib
import logging
import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .core import net, remote
from .core.db import Database
from .core.i18n import translate
from .core.tags import AUDIO_EXTS

logger = logging.getLogger(__name__)

SCHEMA = """CREATE TABLE IF NOT EXISTS offline_copies(path TEXT PRIMARY KEY, file TEXT NOT NULL DEFAULT '',
  size INTEGER NOT NULL DEFAULT 0, saved REAL NOT NULL DEFAULT 0, wanted REAL NOT NULL DEFAULT 0)"""


class OfflineCopies(QObject):
    changed = Signal()
    message = Signal(str)
    _done = Signal(str, str, int, str)  # path, file ("" when it failed), size, what went wrong
    _tick = Signal()

    def __init__(self, db_path, folder, parent=None):
        super().__init__(parent)
        self._db = Database(str(db_path))
        self._db.conn.execute(SCHEMA)
        self._db.conn.commit()
        self._folder = Path(folder)
        self._lock = threading.Lock()
        self._queue = []  # paths still to download, in the order asked
        self._names = {}  # path -> the file name its copy gets (worked out here: the worker doesn't use the db)
        self._current, self._fraction = "", 0.0
        self._stop = threading.Event()  # offline mode or closing: the download under way stops (and resumes)
        self._failed = 0
        self._closing = False
        self._done.connect(self._on_done)
        self._tick.connect(self.changed)
        self._worker = None
        self._load()
        self._progress = QTimer(self)
        self._progress.setInterval(500)
        self._progress.timeout.connect(self.changed)

    def _load(self):
        """The copies there are (told to remote, so they play) and the downloads still to do."""
        for path, file in self._db.conn.execute("SELECT path, file FROM offline_copies WHERE file != ''").fetchall():
            if os.path.isfile(file):
                remote.set_copy(path, file)
            else:  # gone from the folder: fetch it again
                self._db.conn.execute("UPDATE offline_copies SET file='', size=0, wanted=? WHERE path=?",
                                      (time.time(), path))
        self._db.conn.commit()
        self._queue = [r[0] for r in self._db.conn.execute(
            "SELECT path FROM offline_copies WHERE file='' ORDER BY wanted, path")]
        self._name(self._queue)

    def _name(self, paths):
        """Each song's copy's file name: its server and song id (hashed, the same every time, so a download
        that stopped finds its .part again) and its format's extension."""
        fmts = {}
        for i in range(0, len(paths), 500):
            chunk = paths[i:i + 500]
            fmts.update(self._db.conn.execute(
                f"SELECT path, fmt FROM tracks WHERE path IN ({','.join('?' * len(chunk))})", chunk).fetchall())
        for p in paths:
            ext = "." + (fmts.get(p) or "").lower()
            ext = ext if ext in AUDIO_EXTS else ".audio"
            parts = remote.parse(p) or ("server", "x", p)
            digest = hashlib.sha1(parts[2].encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
            self._names[p] = f"{parts[0]}-{parts[1]}-{digest}{ext}"

    # --- what QML shows -----------------------------------------------------------------------------------
    @Property(int, notify=changed)
    def count(self):
        """Songs kept on this computer."""
        return self._db.conn.execute("SELECT COUNT(*) FROM offline_copies WHERE file != ''").fetchone()[0]

    @Property(float, notify=changed)
    def bytes(self):
        return float(self._db.conn.execute("SELECT COALESCE(SUM(size), 0) FROM offline_copies").fetchone()[0])

    @Property(int, notify=changed)
    def waiting(self):
        """Songs still to download (the one under way included)."""
        with self._lock:
            return len(self._queue) + (1 if self._current else 0)

    @Property(float, notify=changed)
    def progress(self):
        """How far the download under way has got, 0–1."""
        return self._fraction

    @Property(bool, notify=changed)
    def busy(self):
        return bool(self._current)

    @Slot("QVariantList", result="QVariantMap")
    def status(self, paths):
        """For an album, a playlist or songs: {servers: how many are a server's, kept, waiting}."""
        paths = [p for p in paths if remote.is_remote(p)]
        if not paths:
            return {"servers": 0, "kept": 0, "waiting": 0}
        kept = sum(1 for p in paths if remote.local_copy(p))
        with self._lock:
            pending = set(self._queue) | ({self._current} if self._current else set())
        return {"servers": len(paths), "kept": kept, "waiting": sum(1 for p in paths if p in pending)}

    # --- keep and remove ----------------------------------------------------------------------------------
    @Slot("QVariantList")
    def keep(self, paths):
        """Download these server songs (those not kept already) to keep on this computer."""
        now = time.time()
        new = []
        with self._lock:
            pending = set(self._queue) | {self._current}
        for p in dict.fromkeys(str(p) for p in paths):
            if remote.is_remote(p) and not remote.local_copy(p) and p not in pending:
                new.append(p)
        if not new:
            self.message.emit(translate("Offline", "Those songs are kept on this computer already"))
            return
        self._db.conn.executemany(
            "INSERT INTO offline_copies(path, wanted) VALUES(?, ?) ON CONFLICT(path) DO UPDATE SET wanted=excluded.wanted",
            [(p, now) for p in new])
        self._db.conn.commit()
        self._name(new)
        with self._lock:
            self._queue.extend(new)
        n = len(new)
        if net.is_offline():
            self.message.emit(translate("Offline", "Offline mode is on: %n song(s) will download when it's off", None, n))
        else:
            self.message.emit(translate("Offline", "Keeping %n song(s) on this computer", None, n))
            self._start()
        self.changed.emit()

    @Slot("QVariantList")
    def remove(self, paths):
        """Delete these songs' copies (and stop fetching them): they stream from the server again."""
        gone = 0
        wanted = set(str(p) for p in paths)
        with self._lock:
            self._queue = [p for p in self._queue if p not in wanted]
        for p in wanted:
            row = self._db.conn.execute("SELECT file FROM offline_copies WHERE path=?", (p,)).fetchone()
            if row is None:
                continue
            if row[0] and self._delete(row[0]):
                gone += 1
            remote.set_copy(p, "")
            self._db.conn.execute("DELETE FROM offline_copies WHERE path=?", (p,))
        self._db.conn.commit()
        if gone:
            self.message.emit(translate("Offline", "Removed %n copies from this computer", None, gone))
        self.changed.emit()

    @Slot()
    def removeAll(self):
        self.remove([r[0] for r in self._db.conn.execute("SELECT path FROM offline_copies")])

    @Slot()
    def tidy(self):
        """Forget copies of songs no longer in the library (a server removed, or a song gone from it)."""
        gone = [r[0] for r in self._db.conn.execute(
            "SELECT path FROM offline_copies WHERE path NOT IN (SELECT path FROM tracks)")]
        if gone:
            self.remove(gone)

    def _delete(self, file):
        """Delete a copy, only ever inside the copies' folder. True if it's gone."""
        try:
            if Path(file).resolve().is_relative_to(self._folder.resolve()):
                os.remove(file)
                return True
        except FileNotFoundError:
            return True
        except OSError as exc:
            logger.info("Couldn't remove a copy: %s", exc)
        return False

    # --- downloading --------------------------------------------------------------------------------------
    @Slot()
    def stopNetwork(self):
        """Offline mode came on: stop the download under way (it carries on afterwards)."""
        self._stop.set()

    @Slot()
    def resumeNetwork(self):
        if not net.is_offline():
            self._start()

    def _start(self):
        if self._closing or net.is_offline() or (self._worker is not None and self._worker.is_alive()):
            return
        with self._lock:
            if not self._queue:
                return
        self._stop.clear()
        self._failed = 0
        self._progress.start()
        self._worker = threading.Thread(target=self._work, name="server-copies", daemon=True)
        self._worker.start()

    def _work(self):
        from .core import podcasts as pc

        while not self._stop.is_set():
            with self._lock:
                if not self._queue:
                    self._current = ""
                    break
                path = self._current = self._queue.pop(0)
                self._fraction = 0.0
            self._tick.emit()
            url = remote.stream_url(path)
            if not url or url.startswith("file:"):
                self._done.emit(path, "", 0, "" if url else translate("Offline", "its server can't be reached"))
                continue
            target = self._folder / self._names.get(path, "song.audio")

            def progress(done, total):
                self._fraction = done / total if total else 0.0

            try:
                file = pc.download(url, target, progress, paused=self._stop.is_set)
                self._done.emit(path, file, os.path.getsize(file), "")
            except InterruptedError:  # offline mode or closing: it goes back to the front of the line
                with self._lock:
                    self._queue.insert(0, path)
                break
            except Exception as exc:  # noqa: BLE001 - one song that won't download doesn't stop the rest
                logger.warning("A server song couldn't be kept: %s", type(exc).__name__)
                self._done.emit(path, "", 0, translate("Offline", "it couldn't be downloaded"))
        with self._lock:
            self._current, self._fraction = "", 0.0
        self._tick.emit()

    @Slot(str, str, int, str)
    def _on_done(self, path, file, size, problem):
        if self._closing:
            return
        if file:
            row = self._db.conn.execute("SELECT 1 FROM offline_copies WHERE path=?", (path,)).fetchone()
            if row is None:  # removed while it downloaded
                self._delete(file)
            else:
                self._db.conn.execute("UPDATE offline_copies SET file=?, size=?, saved=? WHERE path=?",
                                      (file, size, time.time(), path))
                remote.set_copy(path, file)
        elif problem:
            self._failed += 1
            self._db.conn.execute("DELETE FROM offline_copies WHERE path=? AND file=''", (path,))
        self._db.conn.commit()
        with self._lock:
            left = len(self._queue) + (1 if self._current and self._current != path else 0)
        if not left:
            self._progress.stop()
            if self._failed:
                self.message.emit(translate("Offline", "%n song(s) couldn't be kept on this computer (is the server there?)",
                                            None, self._failed))
                self._failed = 0
        self.changed.emit()

    def shutdown(self):
        self._closing = True
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=3)
        self._db.close()
