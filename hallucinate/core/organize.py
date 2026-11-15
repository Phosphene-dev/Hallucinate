"""Organize files from their tags: move songs into folders and names made from a pattern ("Album Artist/Album/01
Title"), each inside the library folder it's already in. Nothing is moved before plan() has been looked at; apply()
never overwrites a file, carries a song's likes, plays, ratings, playlist places and listens to its new path, takes
along its lyrics file and the folder's cover, removes the folders it leaves empty, and keeps a journal so undo()
can put everything back.

CUE sheet albums (one file, many songs) and songs from music servers are left where they are."""
import json
import os
import re
import shutil
import unicodedata

from . import remote, tagedit
from .atomic import write_atomic
from .health import UNKNOWN_ALBUM, UNKNOWN_ARTIST

PRESETS = {
    "artist_album": "{albumartist}/{album}/{disc}{track} {title}",
    "artist_year_album": "{albumartist}/{year} - {album}/{disc}{track} {title}",
    "artist_album_flat": "{albumartist} - {album}/{disc}{track} {title}",
    "artist_album_artist_title": "{albumartist}/{album}/{disc}{track} {artist} - {title}",
}
DEFAULT = "artist_album"
TOKENS = ("albumartist", "artist", "album", "year", "disc", "track", "title", "genre")
SIDECARS = (".lrc",)  # a song's own lyrics file, beside it with the same name
FOLDER_ART = ("cover", "folder", "front", "album", "albumart")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
MAX_PART = 120  # characters in one folder or file name (long names break on some file systems)
_BAD = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class PatternError(ValueError):
    pass


def check_pattern(pattern):
    """The pattern, or PatternError: it needs a {title}, and only known {tokens}."""
    pattern = (pattern or "").strip().strip("/")
    names = re.findall(r"\{([^{}]*)\}", pattern)
    unknown = [n for n in names if n not in TOKENS]
    if unknown:
        raise PatternError("Unknown part: {%s}" % unknown[0])
    if "title" not in names:
        raise PatternError("The pattern needs {title}")
    if ".." in pattern.split("/"):
        raise PatternError("A folder can't be ..")
    return pattern


def clean(part):
    """One folder or file name made safe on every system: no slashes or characters Windows refuses, no names
    it reserves, no dots or spaces at the end, not too long; "" when nothing is left."""
    part = unicodedata.normalize("NFC", str(part or ""))
    part = _BAD.sub("_", part).strip()
    part = " ".join(part.split())
    part = part.rstrip(". ").lstrip(". ") if part not in (".", "..") else ""
    if part.split(".")[0].lower() in _RESERVED:
        part = "_" + part
    return part[:MAX_PART].rstrip(". ")


def render(track, pattern, discs=1):
    """The path (folders and name, no extension) the pattern makes for one song. `discs`: how many discs its
    album has ({disc} is "2-" on a many-disc album, nothing otherwise)."""
    def value(name):
        if name == "albumartist":
            v = track.get("album_artist") or track.get("artist") or ""
            return "" if v == UNKNOWN_ARTIST else v
        if name == "artist":
            v = track.get("artist") or ""
            return "" if v == UNKNOWN_ARTIST else v
        if name == "album":
            v = track.get("album") or ""
            return "" if v == UNKNOWN_ALBUM else v
        if name == "year":
            y = int(track.get("year") or 0)
            return str(y) if y > 0 else ""
        if name == "disc":
            d = int(track.get("disc_no") or 0)
            return f"{d}-" if discs > 1 and d > 0 else ""
        if name == "track":
            n = int(track.get("track_no") or 0)
            return f"{n:02d}" if n > 0 else ""
        if name == "genre":
            return (track.get("genre") or "").split(";")[0].strip()
        return track.get(name) or ""

    parts, raws = [], pattern.split("/")
    for i, raw in enumerate(raws):
        filled = re.sub(r"\{([^{}]*)\}", lambda m: value(m.group(1)).replace("/", "_").replace("\\", "_"), raw)
        filled = re.sub(r"\s*-\s*$|^\s*-\s*", "", filled)  # "2001 - Album" with no year: "Album", not "- Album"
        filled = clean(filled)
        if not filled:
            filled = "Untitled" if i == len(raws) - 1 else "Unknown"
        parts.append(filled)
    return "/".join(parts)


def _root_of(path, folders):
    """The library folder `path` is in (the deepest, if they nest), or None."""
    best = None
    for f in folders:
        f = os.path.normpath(f)
        if path == f or path.startswith(f.rstrip(os.sep) + os.sep):
            if best is None or len(f) > len(best):
                best = f
    return best


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def plan(tracks, folders, pattern):
    """What organizing these songs would do: {"moves": [{"src", "dst", "title"}], "same": n already in place,
    "skipped": [{"path", "why"}]}. `tracks`: library rows (path, album_key, tags); `folders`: the library
    folders. A song that would land on an existing file or another song's place gets " (2)"."""
    pattern = check_pattern(pattern)
    discs = {}
    for t in tracks:
        discs.setdefault(t.get("album_key"), set()).add(int(t.get("disc_no") or 0) or 1)
    moves, skipped, same, taken = [], [], 0, {}
    for t in tracks:
        src = t.get("path") or ""
        if remote.is_remote(src):
            skipped.append({"path": src, "why": "server"})
            continue
        if re.search(r"#\d+$", src) or not os.path.isfile(src):
            skipped.append({"path": src, "why": "cue" if re.search(r"#\d+$", src) else "missing"})
            continue
        root = _root_of(os.path.normpath(src), folders)
        if root is None:
            skipped.append({"path": src, "why": "outside"})
            continue
        ext = os.path.splitext(src)[1].lower()
        rel = render(t, pattern, len(discs.get(t.get("album_key"), ())))
        base = os.path.join(root, *rel.split("/"))
        dst, n = base + ext, 1
        while True:
            key = os.path.normcase(dst)
            clash = taken.get(key)
            if os.path.normcase(os.path.normpath(src)) == key or _same_file(src, dst):
                break  # already there (or only its case differs: left as it is)
            if clash is None and not os.path.exists(dst):
                break
            n += 1
            dst = f"{base} ({n}){ext}"
        if os.path.normcase(os.path.normpath(src)) == os.path.normcase(dst) or _same_file(src, dst):
            same += 1
            continue
        taken[os.path.normcase(dst)] = src
        moves.append({"src": src, "dst": dst, "title": t.get("title") or os.path.basename(src)})
    return {"moves": moves, "same": same, "skipped": skipped}


def _move(src, dst):
    """Move one file; never over another (FileExistsError)."""
    if os.path.lexists(dst):
        raise FileExistsError(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.rename(src, dst)  # (same disk: instant, and atomic)
    except OSError:
        if os.path.lexists(dst):
            raise
        shutil.move(src, dst)


def _companions(moves):
    """The lyrics files and folder covers that go with these moves: [(src, dst)]. A folder's cover goes along when
    every song of that folder is going to one and the same new folder."""
    out = []
    for m in moves:
        stem_src, stem_dst = os.path.splitext(m["src"])[0], os.path.splitext(m["dst"])[0]
        for ext in SIDECARS:
            if os.path.isfile(stem_src + ext) and not os.path.lexists(stem_dst + ext):
                out.append((stem_src + ext, stem_dst + ext))
    by_dir = {}
    for m in moves:
        by_dir.setdefault(os.path.dirname(m["src"]), set()).add(os.path.dirname(m["dst"]))
    for src_dir, dst_dirs in by_dir.items():
        if len(dst_dirs) != 1:
            continue
        dst_dir = next(iter(dst_dirs))
        try:
            names = os.listdir(src_dir)
        except OSError:
            continue
        audio_left = [n for n in names if os.path.join(src_dir, n) not in {m["src"] for m in moves}
                      and os.path.splitext(n)[1].lower() in _audio_exts()]
        if audio_left:
            continue  # other songs stay: their cover stays with them
        for n in names:
            stem, ext = os.path.splitext(n)
            if stem.lower() in FOLDER_ART and ext.lower() in IMAGE_EXTS and not os.path.lexists(os.path.join(dst_dir, n)):
                out.append((os.path.join(src_dir, n), os.path.join(dst_dir, n)))
    return out


def _audio_exts():
    from .tags import AUDIO_EXTS
    return AUDIO_EXTS


def _prune(dirs, roots):
    """Remove the folders left empty (and their parents, up to the library folder)."""
    roots = {os.path.normpath(r) for r in roots}
    for d in sorted(set(dirs), key=len, reverse=True):
        d = os.path.normpath(d)
        while d not in roots and _root_of(d, roots) is not None:
            try:
                os.rmdir(d)  # only when empty
            except OSError:
                break
            d = os.path.dirname(d)


def _update_library(db, scanner, pairs):
    """The library follows songs moved [(old, new)]: rows read at the new paths, then likes, plays and the rest
    carried over, then the old rows dropped."""
    if not pairs:
        return
    scanner.refresh_files([new for _, new in pairs])
    known = {r[0] for r in db.conn.execute(
        f"SELECT path FROM tracks WHERE path IN ({','.join('?' * len(pairs))})", [new for _, new in pairs])}
    # a file that couldn't be read again where it went keeps its row, moved with it (not dropped from the library)
    for old, new in pairs:
        if new not in known:
            db.conn.execute("UPDATE tracks SET path=? WHERE path=?", (new, old))
    db.move_user_data(pairs)
    db.remove_paths([old for old, new in pairs if new in known])
    db.commit()


def apply(db, scanner, moves, folders, journal, progress=None, stop=None):
    """Move the files of `moves` (from plan()), the library following. Writes `journal` (JSON) as it goes, so
    undo() can put them back. Returns {"moved", "errors": [text]}."""
    done, errors, pairs, record = 0, [], [], []
    left = []
    companions = _companions(moves)
    try:
        for i, m in enumerate(moves):
            if stop and stop():
                break
            src, dst = m["src"], m["dst"]
            tagedit.note_writing(src)
            tagedit.note_writing(dst)
            try:
                _move(src, dst)
            except OSError as exc:
                errors.append(f"{os.path.basename(src)}: {exc.strerror or exc}")
                continue
            record.append([src, dst])
            pairs.append((src, dst))
            left.append(os.path.dirname(src))
            done += 1
            if len(pairs) >= 50:  # the library follows in batches, so a stop leaves it right
                _update_library(db, scanner, pairs)
                pairs = []
                _write_journal(journal, record)
            if progress:
                progress(i + 1)
        _update_library(db, scanner, pairs)
        moved_srcs = {s for s, _ in record}
        for src, dst in companions:
            owner = os.path.splitext(src)[0]
            if src.lower().endswith(SIDECARS) and not any(os.path.splitext(s)[0] == owner for s in moved_srcs):
                continue  # its song didn't move (an error, or stopped)
            try:
                tagedit.note_writing(dst)
                _move(src, dst)
                record.append([src, dst])
                left.append(os.path.dirname(src))
            except OSError:
                pass  # (a cover or lyrics file that won't move stays: the songs did)
    finally:
        _write_journal(journal, record)
        _prune(left, folders)
    return {"moved": done, "errors": errors}


def _write_journal(journal, record):
    if journal:
        text = json.dumps({"moves": record})
        write_atomic(journal, lambda fh: fh.write(text.encode("utf-8")))


def read_journal(journal):
    """The moves of the last organize [[old, new]], or []."""
    try:
        with open(journal, encoding="utf-8") as fh:
            return [m for m in json.load(fh).get("moves", []) if isinstance(m, list) and len(m) == 2]
    except (OSError, ValueError, AttributeError):
        return []


def undo(db, scanner, journal, folders):
    """Put back what the last organize moved (newest first); a file moved again since, or whose old place is
    taken, stays. Returns {"moved", "errors"}; the journal is cleared."""
    record = read_journal(journal)
    pairs, errors, left, done = [], [], [], 0
    audio = _audio_exts()
    for old, new in reversed(record):
        tagedit.note_writing(old)
        tagedit.note_writing(new)
        try:
            _move(new, old)
        except OSError as exc:
            errors.append(f"{os.path.basename(new)}: {exc.strerror or exc}")
            continue
        left.append(os.path.dirname(new))
        if os.path.splitext(old)[1].lower() in audio:
            pairs.append((new, old))
            done += 1
    _update_library(db, scanner, pairs)
    _prune(left, folders)
    try:
        os.remove(journal)
    except OSError:
        pass
    return {"moved": done, "errors": errors}
