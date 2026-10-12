"""Keeps the on-disk caches (cover thumbnails, waveforms) from growing without end. Entries are keyed by file
date, so edits and re-tags leave stale ones behind; the least recently used go first once a cache is over its
limit. Runs once in the background at start-up."""
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

LIMITS = {"thumbs": 512 * 1024 * 1024, "waveforms": 256 * 1024 * 1024}
TOUCH_AFTER_S = 7 * 24 * 3600


def touch_if_stale(path):
    """Mark a cache file as used (its mtime is the "last used" date), at most about once a week per file."""
    try:
        if time.time() - os.stat(path).st_mtime > TOUCH_AFTER_S:
            os.utime(path)
    except OSError:
        pass


def trim(directory, max_bytes) -> int:
    """Delete the oldest files until `directory` holds at most max_bytes. Returns bytes freed."""
    entries = []
    try:
        with os.scandir(directory) as it:
            for e in it:
                if e.is_file(follow_symlinks=False):
                    st = e.stat(follow_symlinks=False)
                    entries.append((st.st_mtime, st.st_size, e.path))
    except OSError:
        return 0
    total = sum(size for _, size, _ in entries)
    freed = 0
    for _, size, path in sorted(entries):
        if total - freed <= max_bytes:
            break
        try:
            os.unlink(path)
            freed += size
        except OSError:
            pass
    if freed:
        logger.info("Trimmed %s by %.0f MB", directory, freed / 1e6)
    return freed


def trim_in_background(dirs: dict):
    """dirs: {Path: max_bytes}."""
    def run():
        for d, limit in dirs.items():
            trim(Path(d), limit)

    t = threading.Thread(target=run, name="cache-trim", daemon=True)
    t.start()
    return t
