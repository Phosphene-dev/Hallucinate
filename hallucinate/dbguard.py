"""Keeps the library database (likes, plays, playlists, history: things a rescan can't rebuild) safe.

At start-up the database gets a quick integrity check. A damaged one is moved aside, never deleted, and the newest
daily backup takes its place; with no backup, Hallucinate starts a fresh one and rescans. Once a day a backup is
taken (SQLite's online backup, so it is consistent even while the app writes) and the last few are kept."""
import logging
import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

KEEP = 5
EVERY_S = 24 * 3600


def _healthy(path) -> bool:
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        try:
            return con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            con.close()
    except sqlite3.Error:
        return False


def backups(backup_dir) -> list:
    """Backups, newest first."""
    d = Path(backup_dir)
    return sorted(d.glob("library-*.db"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []


def check(db_path, backup_dir) -> str:
    """Make sure db_path is a healthy database before anything opens it. Returns a message for the user when
    something had to be done, else ""."""
    db = Path(db_path)
    if not db.exists() or _healthy(db):
        return ""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    aside = db.with_name(f"{db.name}.damaged-{stamp}")
    for suffix in ("", "-wal", "-shm"):
        part = Path(str(db) + suffix)
        if part.exists():
            os.replace(part, str(aside) + suffix)
    logger.error("The library database was damaged; moved it to %s", aside)
    for backup in backups(backup_dir):
        if _healthy(backup):
            shutil.copy2(backup, db)
            when = time.strftime("%d %b", time.localtime(backup.stat().st_mtime))
            logger.warning("Restored the library database from %s", backup)
            return (f"Your library database was damaged, so the backup from {when} was restored. "
                    f"The damaged copy was kept as {aside.name}.")
    return (f"Your library database was damaged and there was no backup, so it was started again: choose your "
            f"music folders to rescan. The damaged copy was kept as {aside.name}.")


def backup_now(db_path, backup_dir, keep=KEEP) -> Path:
    d = Path(backup_dir)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"library-{time.strftime('%Y%m%d-%H%M%S')}.db"
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
    for old in backups(d)[keep:]:
        old.unlink(missing_ok=True)
    return dest


def backup_if_due(db_path, backup_dir):
    """Take today's backup in the background if the newest is over a day old."""
    newest = backups(backup_dir)
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
