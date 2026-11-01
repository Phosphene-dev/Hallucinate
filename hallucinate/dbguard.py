"""Keeps the library database (likes, plays, playlists, history: things a rescan can't rebuild) safe.

At start-up the database gets a quick integrity check, unless the last run closed it cleanly and it hasn't changed
since (damage comes from a crash or power loss mid-write, and the check reads the whole file: most of a second
for a quarter of a million songs); it still gets one at least weekly. A damaged one is moved aside, never deleted,
and the newest daily backup takes its place; with no backup, Hallucinate starts a fresh one and rescans. Once a day a backup is
taken (SQLite's online backup, so it is consistent even while the app writes) and the last few are kept."""
import datetime
import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from .core.i18n import fill, format_date, translate

logger = logging.getLogger(__name__)

KEEP = 5
EVERY_S = 24 * 3600
FULL_CHECK_EVERY_S = 7 * 24 * 3600


_last_full_check = {}  # db path -> when its last full integrity check passed (carried in the marker)


def _marker(db) -> Path:
    return Path(str(db) + ".clean")


def _fingerprint(db):
    st = Path(db).stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _closed_cleanly(db) -> bool:
    """Whether the last run closed `db` cleanly, nothing has touched it since, and it was fully checked this
    week. The marker is used up either way, so a crash during this run means a check at the next start."""
    try:
        marker = json.loads(_marker(db).read_text())
        _marker(db).unlink()
    except (OSError, ValueError):
        return False
    _last_full_check[str(db)] = marker.get("checked", 0)
    try:
        same = {k: marker.get(k) for k in ("size", "mtime_ns")} == _fingerprint(db)
    except OSError:
        return False
    return same and time.time() - marker.get("checked", 0) < FULL_CHECK_EVERY_S


DAMAGED = {"SQLITE_CORRUPT", "SQLITE_NOTADB", "SQLITE_CORRUPT_INDEX", "SQLITE_CORRUPT_SEQUENCE",
           "SQLITE_CORRUPT_VTAB"}


def _healthy(path):
    """True when the database checks out, False when it's damaged, None when it couldn't be checked (locked,
    busy, unreadable for now): that isn't damage, and setting it aside would hide recent likes and plays."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        try:
            return con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            con.close()
    except sqlite3.DatabaseError as exc:
        name = getattr(exc, "sqlite_errorname", "")
        if name in DAMAGED or (not name and "malformed" in str(exc).lower() or "not a database" in str(exc)):
            return False
        return None
    except sqlite3.Error:
        return None


def mark_clean(db_path):
    """Call after the last connection closed on a clean exit: the next start may skip the integrity check
    while the file stays exactly as it is now."""
    db = Path(db_path)
    wal = Path(str(db) + "-wal")
    try:
        if not db.exists() or (wal.exists() and wal.stat().st_size):
            return  # writes not merged into the file yet: check it next time
        checked = _last_full_check.get(str(db), 0)
        _marker(db).write_text(json.dumps({**_fingerprint(db), "checked": checked}))
    except OSError:
        pass


def backups(backup_dir, stem="library") -> list:
    """Backups of the database called `stem` (library, streams), newest first."""
    d = Path(backup_dir)
    return sorted(d.glob(f"{stem}-*.db"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []


def check(db_path, backup_dir) -> str:
    """Make sure db_path is a healthy database before anything opens it. Returns a message for the user when
    something had to be done, else ""."""
    db = Path(db_path)
    if not db.exists() or _closed_cleanly(db):
        return ""
    health = _healthy(db)
    if health is None:
        logger.warning("Couldn't check %s this time; leaving it as it is", db.name)
        return ""
    if health:
        _last_full_check[str(db)] = time.time()
        return ""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    aside = db.with_name(f"{db.name}.damaged-{stamp}")
    for suffix in ("", "-wal", "-shm"):
        part = Path(str(db) + suffix)
        if part.exists():
            os.replace(part, str(aside) + suffix)
    logger.error("The database %s was damaged; moved it to %s", db.name, aside)
    library = db.stem == "library"
    for backup in backups(backup_dir, db.stem):
        if _healthy(backup):
            shutil.copy2(backup, db)
            when = format_date(datetime.date.fromtimestamp(backup.stat().st_mtime), translate("DbGuard", "d MMM", "date format (Qt)"))
            logger.warning("Restored the library database from %s", backup)
            return fill(translate("DbGuard", "Your library database was damaged, so the backup from %1 was restored. "
                                  "The damaged copy was kept as %2.") if library
                        else translate("DbGuard", "Your radio and podcasts database was damaged, so the backup from %1 was "
                                       "restored. The damaged copy was kept as %2."), when, aside.name)
    if not library:
        return fill(translate("DbGuard", "Your radio and podcasts database was damaged and there was no backup, so it was "
                              "started again. The damaged copy was kept as %1."), aside.name)
    return fill(translate("DbGuard", "Your library database was damaged and there was no backup, so it was started again: "
                          "choose your music folders to rescan. The damaged copy was kept as %1."), aside.name)


def backup_now(db_path, backup_dir, keep=KEEP) -> Path:
    d = Path(backup_dir)
    d.mkdir(parents=True, exist_ok=True)
    stem = Path(db_path).stem
    dest = d / f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}.db"
    tmp = dest.with_suffix(".part")
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        out = sqlite3.connect(tmp)
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    os.replace(tmp, dest)
    for old in backups(d, stem)[keep:]:
        old.unlink(missing_ok=True)
    return dest


def backup_if_due(db_path, backup_dir):
    """Take today's backup in the background if the newest is over a day old."""
    if not Path(db_path).exists():
        return None
    newest = backups(backup_dir, Path(db_path).stem)
    if newest and time.time() - newest[0].stat().st_mtime < EVERY_S:
        return None

    def run():
        try:
            backup_now(db_path, backup_dir)
        except (OSError, sqlite3.Error) as exc:
            logger.warning("Couldn't back up the library database: %s", exc)

    t = threading.Thread(target=run, name="db-backup", daemon=True)
    t.start()
    return t
