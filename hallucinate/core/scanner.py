"""Incremental folder scanner: only new/changed files are parsed."""
import os
import re
import time
from typing import Callable, Optional

from . import cue, tags
from .db import Database

_CUE_SONG = re.compile(r"^(.*\.[A-Za-z0-9]+)#\d+$")
COMMIT_EVERY_S = 0.2  # changes waiting longer than this are saved before the next file is read


class Scanner:
    def __init__(self, db: Database, art_dir, progress: Optional[Callable[[int], None]] = None,
                 should_stop: Optional[Callable[[], bool]] = None):
        self.db = db
        self.art_dir = str(art_dir)
        self.progress = progress
        self.should_stop = should_stop or (lambda: False)
        self._art = {k: v for k, v in db.album_art_map().items() if v and os.path.exists(v)}
        self._seen = 0
        self._hidden = set()
        self._gone = []  # songs no longer found, removed once every folder is scanned (see _settle_moves)
        self._added = []  # songs new in this scan: a gone one may have just moved here

    def scan(self, folders) -> dict:
        stats = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0, "errors": 0, "moved": 0, "dirs": []}
        self._hidden = self.db.hidden_paths()  # removed from the library on purpose
        self._gone, self._added = [], []
        for folder in folders:
            if self.should_stop():
                break
            self._scan_folder(folder, stats)
        self._settle_moves(stats)
        self.db.finalize()
        return stats

    def refresh_files(self, paths) -> int:
        """Re-read specific files (after a tag edit) and update their rows. Returns how many were updated."""
        n = 0
        for path in paths:
            t = tags.read_track(path, art_known=lambda k: k in self._art)
            if t is None:
                continue
            self._attach_art(t, os.path.dirname(path))
            self.db.upsert_track(t)
            n += 1
        self.db.finalize()
        self.db.commit()
        return n

    def _scan_folder(self, folder: str, stats: dict):
        if not os.path.isdir(folder):
            return  # unmounted/missing: keep existing entries
        existing = self.db.paths_under(folder)
        # songs of CUE sheets embedded in their file, by file, so an unchanged one isn't read again
        embedded = {}
        for p in existing:
            m = _CUE_SONG.match(p)
            if m:
                embedded.setdefault(m.group(1), []).append(p)
        seen = set()
        pending = 0
        last_commit = time.monotonic()
        visited = set()
        # Folders and files that couldn't be read this time (permissions, a flaky network disk): the songs
        # already in the library under them are kept, not taken for gone.
        failed_dirs, failed = [], set()

        def unreadable(err):
            failed_dirs.append(err.filename)

        for root, dirs, files in os.walk(folder, followlinks=True, onerror=unreadable):
            real = os.path.realpath(root)
            if real in visited:  # symlink loop / duplicate view of a directory
                dirs[:] = []
                continue
            visited.add(real)
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            stats["dirs"].append(root)
            sheets = self._cue_sheets(root, files)
            for name in sorted(files):
                if self.should_stop():
                    self.db.commit()
                    return
                if os.path.splitext(name)[1].lower() not in tags.AUDIO_EXTS:
                    continue
                path = os.path.join(root, name)
                if path in self._hidden:
                    continue
                try:
                    st = os.stat(path)
                except OSError:
                    failed.add(path)
                    continue
                self._seen += 1
                if self.progress and self._seen % 25 == 0:
                    self.progress(self._seen)
                if path in sheets:
                    pending += self._scan_cue(path, st, sheets[path], existing, seen, stats, failed)
                    continue
                seen.add(path)
                old = existing.get(path)
                if old and old[0] == st.st_mtime and old[1] == st.st_size:
                    stats["unchanged"] += 1
                    continue
                songs = embedded.get(path, [])
                if not old and songs and all(existing[p] == (st.st_mtime, st.st_size) for p in songs):
                    seen.update(songs)  # a file split by its own CUE sheet, unchanged
                    stats["unchanged"] += len(songs)
                    continue
                if pending and time.monotonic() - last_commit > COMMIT_EVERY_S:
                    # Not while reading a file (a slow or network disk): the library's other writers
                    # (adding a folder, saving a play) would wait on this scan's lock until it's done.
                    self.db.commit()
                    pending, last_commit = 0, time.monotonic()
                t = tags.read_track(path, art_known=lambda k: k in self._art)
                if t is None:
                    stats["errors"] += 1
                    failed.add(path)  # there, but unreadable now: its songs stay as they were
                    continue
                sheet_text = t.pop("_cuesheet", "")
                if sheet_text:
                    rows = self._embedded_cue_rows(t, sheet_text)
                    if rows:
                        seen.discard(path)
                        for row in rows:
                            self._attach_art(row, root)
                            self.db.upsert_track(row)
                            seen.add(row["path"])
                            self._count(row["path"], existing, stats)
                        pending += len(rows)
                        continue
                self._attach_art(t, root)
                self.db.upsert_track(t)
                self._count(path, existing, stats)
                pending += 1
                if pending >= 200:
                    self.db.commit()
                    pending, last_commit = 0, time.monotonic()
        dirs_failed = tuple(d.rstrip(os.sep) + os.sep for d in failed_dirs if d)
        self._gone += [p for p in existing if p not in seen and not self._failed(p, failed, dirs_failed)]
        self.db.commit()

    def _count(self, path, existing, stats):
        if path in existing:
            stats["updated"] += 1
        else:
            stats["added"] += 1
            self._added.append(path)

    def _failed(self, path, failed, dirs_failed) -> bool:
        """Whether `path` (or the file its CUE song lies in) couldn't be read this time."""
        return (path in failed or self.db.file_of(path) in failed or path.startswith(dirs_failed))

    def _settle_moves(self, stats):
        """Remove the songs no longer found, but first give each one that was only moved or renamed (the same
        size, length, title and artist as exactly one song new in this scan) its likes, plays, ratings,
        playlist places and listens, at the new path."""
        if not self._gone:
            return
        gone, added = self.db.move_keys(self._gone), self.db.move_keys(self._added)
        by_key = {}
        for path, key in added.items():
            by_key.setdefault(key, []).append(path)
        olds = {}
        for path, key in gone.items():
            olds.setdefault(key, []).append(path)
        moves = [(old[0], by_key[key][0]) for key, old in olds.items()
                 if len(old) == 1 and len(by_key.get(key, ())) == 1 and key[1] > 0]
        if moves:
            self.db.move_user_data(moves)
        self.db.remove_paths(self._gone)
        stats["removed"] += len(self._gone)
        stats["moved"] += len(moves)
        self.db.commit()
        self._gone, self._added = [], []

    @staticmethod
    def _cue_sheets(directory, files):
        """{audio path: (sheet, file entry, sheet mtime)} for the audio files that CUE sheets here split up."""
        audio = [f for f in files if os.path.splitext(f)[1].lower() in tags.AUDIO_EXTS]
        out = {}
        for name in sorted(files):
            if not name.lower().endswith(".cue") or not audio:
                continue
            path = os.path.join(directory, name)
            try:
                mtime = os.stat(path).st_mtime
            except OSError:
                continue
            for target, (sheet, entry) in cue.split_files(path, audio).items():
                out.setdefault(target, (sheet, entry, mtime))
        return out

    def _scan_cue(self, path, st, found, existing, seen, stats, failed) -> int:
        """Add the songs a CUE sheet makes of one audio file. Returns how many rows were written."""
        sheet, entry, cue_mtime = found
        expected = [cue.virtual_path(path, t["number"]) for t in entry["tracks"]]
        mtime = max(st.st_mtime, cue_mtime)
        # A song with no length (a last track past the end of the file) is never stored, so it can't count
        # against "unchanged": editing the sheet or the file changes mtime for every song that is.
        known = [p for p in expected if p in existing]
        if known and all(existing[p] == (mtime, st.st_size) for p in known):
            seen.update(known)
            stats["unchanged"] += len(known)
            return 0
        whole = tags.read_track(path, art_known=lambda k: False)
        if whole is None:
            stats["errors"] += 1
            failed.add(path)
            return 0
        rows = cue.tracks(whole, sheet, entry, cue_mtime)
        art = whole.get("_art")
        for row in rows:
            if art is not None:
                row["_art"] = art
            self._attach_art(row, os.path.dirname(path))
            self.db.upsert_track(row)
            seen.add(row["path"])
            self._count(row["path"], existing, stats)
        return len(rows)

    @staticmethod
    def _embedded_cue_rows(whole, text):
        """Songs from a CUE sheet stored inside the file (the entry splitting it into the most songs)."""
        sheet = cue.parse(text)
        entries = [f for f in sheet["files"] if len(f["tracks"]) >= 2]
        if not entries:
            return []
        entry = max(entries, key=lambda f: len(f["tracks"]))
        art = whole.get("_art")
        rows = cue.tracks(whole, sheet, entry)
        for row in rows:
            row["_art"] = art
        return rows

    def _attach_art(self, t: dict, directory: str):
        key = t["album_key"]
        raw = t.pop("_art", None)
        if key in self._art:
            t["art"] = self._art[key]
            return
        path = None
        chosen = self.db.chosen_art(key)
        if chosen and os.path.isfile(chosen):
            path = chosen  # you picked this one: the file's own picture doesn't replace it
        elif raw:
            path = os.path.join(self.art_dir, key + tags._image_ext(raw))
            from .atomic import write_atomic

            os.makedirs(self.art_dir, exist_ok=True)  # the cover cache may have been cleared
            write_atomic(path, lambda fh: fh.write(raw))  # never a half-written cover, even if stopped
        else:
            path = tags.find_folder_art(directory)
        if path:
            self._art[key] = path
            t["art"] = path
            self.db.set_album_art(key, path)
