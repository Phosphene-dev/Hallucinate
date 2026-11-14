"""Suggested fixes for Library health's tag checks: albums without a year, albums without track numbers and songs
without an artist or album. Each looks locally first (folder and file names) and, for years and track numbers,
asks MusicBrainz for the rest. Nothing here writes anything: the suggestions go to a review where you tick the
ones to keep.

Pure functions; the MusicBrainz lookups are passed in (search(artist, album) and release(id), as in
core.musicbrainz) so tests don't touch the network."""
import os
import re

from . import health
from .musicbrainz import _norm, _same

YEAR_IN_NAME = re.compile(r"(?:^|[\s\(\[\{_.-])((?:19|20)\d\d)(?=$|[\s\)\]\}_.-])")
# "01 Title", "01. Title", "01 - Title", "1-03 Title" (disc 1, track 3), "A2 Title" is left alone (vinyl sides)
NUMBERED_NAME = re.compile(r"^\s*(?:(\d{1,2})\s*[-.]\s*)?(\d{1,3})(?:\s*[-._)]\s*|\s+)(?=\S)")
DISC_FOLDER = re.compile(r"^\s*(?:cd|dis[ck]|disque|disco)\s*[-_.]?\s*(\d{1,2})\b.*$", re.IGNORECASE)
ARTIST_DASH = re.compile(r"^(.+?)\s+[-–—]\s+(.+)$")
TRAILING_EXTRA = re.compile(r"\s*[\(\[\{][^\)\]\}]*[\)\]\}]\s*$")
LEADING_YEAR = re.compile(r"^\s*[\(\[]?(?:19|20)\d\d[\)\]]?\s*[-–—.]?\s+")
# folders that say nothing about an artist or album
GENERIC = {"music", "musique", "musik", "música", "musica", "my music", "audio", "mp3", "mp3s", "flac", "songs",
           "downloads", "download", "unsorted", "misc", "various", "new folder", "itunes", "itunes media",
           "media", "library", "albums", "singles", "unknown", "unknown artist", "unknown album", "home"}


def _plausible_year(year, now_year=2100):
    return 1900 <= year <= now_year


def year_from_names(paths):
    """A year every one of an album's folder names agree on ("Album (1997)", "1997 - Album"), or 0. The folder
    is read first; the file names only if it has none, and then all of them must say the same."""
    if not paths:
        return 0
    folders = set()
    for p in paths:
        folder = os.path.dirname(p)
        if DISC_FOLDER.match(os.path.basename(folder)):  # "CD1": the album's folder is the one above it
            folder = os.path.dirname(folder)
        folders.add(os.path.basename(folder))
    years = set()
    for folder in folders:
        found = {int(y) for y in YEAR_IN_NAME.findall(folder)}
        if len(found) == 1:
            years |= found
        elif len(found) > 1:
            return 0
    if not years:
        per_file = []
        for p in paths:
            found = {int(y) for y in YEAR_IN_NAME.findall(os.path.splitext(os.path.basename(p))[0])}
            if len(found) != 1:
                return 0
            per_file.append(found.pop())
        years = set(per_file)
    if len(years) == 1:
        year = years.pop()
        return year if _plausible_year(year) else 0
    return 0


def year_online(artist, album, search):
    """The album's first release year on MusicBrainz, or ("", "") if no release matches it well:
    (year, the release's title)."""
    if not (album or "").strip() or album == health.UNKNOWN_ALBUM:
        return "", ""
    hits = [h for h in search(artist if artist != health.UNKNOWN_ARTIST else "", album)
            if h.get("year") and h.get("score", 0) >= 80 and _same(h.get("title"), album)
            and (not artist or artist == health.UNKNOWN_ARTIST or _same(h.get("artist"), artist)
                 or _norm(artist) in _norm(h.get("artist")))]
    if not hits:
        return "", ""
    best = min(hits, key=lambda h: h["year"])  # the earliest: the original, not a reissue
    return best["year"], best.get("title", "")


def numbers_from_names(songs):
    """Track (and disc) numbers from an album's file names: [{path, title, track_no, disc_no}] in the order they
    give, or [] unless every song has one, no two share it and they run about as far as the songs do. A "CD2"
    folder gives its songs disc 2."""
    out, seen = [], set()
    for s in songs:
        stem = os.path.splitext(os.path.basename(s["path"]))[0]
        m = NUMBERED_NAME.match(stem)
        if not m:
            return []
        disc = int(m.group(1)) if m.group(1) else 0
        number = int(m.group(2))
        if not disc:
            folder = DISC_FOLDER.match(os.path.basename(os.path.dirname(s["path"])))
            disc = int(folder.group(1)) if folder else 0
        if number <= 0 or (disc, number) in seen:
            return []
        seen.add((disc, number))
        out.append({"path": s["path"], "title": s.get("title") or stem, "track_no": number, "disc_no": disc})
    per_disc = {}
    for r in out:
        per_disc[r["disc_no"]] = per_disc.get(r["disc_no"], 0) + 1
    if any(r["track_no"] > 2 * per_disc[r["disc_no"]] + 2 for r in out):
        return []  # "99 Problems" and "7 Rings": titles that start with a number, not track numbers
    return sorted(out, key=lambda r: (r["disc_no"], r["track_no"]))


def numbers_online(artist, album, songs, search, release, tries=3):
    """Track numbers from a MusicBrainz release with as many tracks as the album, matched to its songs by title:
    ([{path, title, track_no, disc_no}], the release's title), or ([], "") unless every song matches one track
    and no two the same."""
    if not (album or "").strip() or album == health.UNKNOWN_ALBUM or not songs:
        return [], ""
    who = artist if artist != health.UNKNOWN_ARTIST else ""
    hits = [h for h in search(who, album) if h.get("score", 0) >= 80 and _same(h.get("title"), album)
            and h.get("tracks") == len(songs)]
    for hit in hits[:tries]:
        full = release(hit["id"])
        by_title = {}
        for t in full.get("tracks") or []:
            by_title.setdefault(_norm(t["title"]), []).append(t)
        out, used = [], set()
        for s in songs:
            found = by_title.get(_norm(s.get("title")), [])
            if len(found) != 1 or id(found[0]) in used:
                break
            used.add(id(found[0]))
            multi = (full.get("discs") or 1) > 1
            out.append({"path": s["path"], "title": s.get("title") or "", "track_no": found[0]["number"],
                        "disc_no": found[0]["disc"] if multi else 0})
        else:
            return sorted(out, key=lambda r: (r["disc_no"], r["track_no"])), full.get("title") or hit.get("title", "")
    return [], ""


def _clean_name(name):
    name = name.replace("_", " ").strip()
    while True:
        bare = TRAILING_EXTRA.sub("", name).strip()  # "Album (1997) [FLAC]" → "Album"
        if bare == name or not bare:
            break
        name = bare
    name = LEADING_YEAR.sub("", name).strip() or name  # "1997 - Album" → "Album"
    return " ".join(name.split())


def _meaningful(name, roots):
    return bool(name) and name.casefold() not in GENERIC and name not in roots


def guess_from_path(path, roots=()):
    """What a song's folders and file name say about its artist and album: {"artist", "album"} (either may be "").
    Artist/Album/song, "Artist - Album"/song and "Artist - Title" file names are understood; a library folder
    (one in `roots`) or a generic one ("Music", "Downloads") says nothing."""
    roots = {os.path.normpath(r) for r in roots}
    folder = os.path.dirname(path)
    if DISC_FOLDER.match(os.path.basename(folder)):
        folder = os.path.dirname(folder)
    in_root = os.path.normpath(folder) in roots
    album_dir = "" if in_root else os.path.basename(folder)
    parent = os.path.dirname(folder)
    artist_dir = "" if in_root or os.path.normpath(parent) in roots or parent == folder else os.path.basename(parent)
    artist, album = "", ""
    dash = ARTIST_DASH.match(_clean_name(album_dir)) if album_dir else None
    if dash and _meaningful(dash.group(1), roots):
        artist, album = dash.group(1).strip(), _clean_name(dash.group(2))
    else:
        album = _clean_name(album_dir) if _meaningful(_clean_name(album_dir), roots) else ""
        artist = _clean_name(artist_dir) if album and _meaningful(_clean_name(artist_dir), roots) else ""
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = NUMBERED_NAME.sub("", stem, count=1) or stem
    named = ARTIST_DASH.match(stem.replace("_", " "))
    if named and not artist and _meaningful(named.group(1).strip(), roots) and not named.group(1).strip().isdigit():
        artist = named.group(1).strip()
    return {"artist": artist, "album": album}


def untagged_groups(songs, roots=()):
    """Songs without an artist or album, grouped by folder and by what was guessed for them:
    [{folder, artist, album, paths, missing_artist, missing_album}] where something was guessed for a gap.
    Only the gaps are filled: a song's own artist or album stays."""
    groups = {}
    for s in songs:
        no_artist = s.get("artist") == health.UNKNOWN_ARTIST
        no_album = s.get("album") == health.UNKNOWN_ALBUM
        guess = guess_from_path(s["path"], roots)
        artist = guess["artist"] if no_artist else ""
        album = guess["album"] if no_album else ""
        if not (artist or album):
            continue
        key = (os.path.dirname(s["path"]), artist, album)
        g = groups.setdefault(key, {"folder": key[0], "artist": artist, "album": album, "paths": [],
                                    "missing_artist": False, "missing_album": False})
        g["paths"].append(s["path"])
        g["missing_artist"] |= no_artist
        g["missing_album"] |= no_album
    return sorted(groups.values(), key=lambda g: (g["folder"].casefold(), g["artist"].casefold()))
