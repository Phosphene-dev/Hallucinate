"""Bring play counts, skips, ratings and playlists over from other music players.

Each reader returns {"source", "songs": [{path, artist, title, plays, skips, rating (0–5), last_played (unix)}],
"playlists": [{name, entries: [{path, artist, title}]}]}. Supported:

- Strawberry and Clementine (their SQLite library database)
- Rhythmbox (rhythmdb.xml, with playlists.xml next to it)
- MusicBee, iTunes and Apple Music (the iTunes-style library XML; MusicBee writes one when "make library and
  playlists accessible to other applications" is on)
- foobar2000 (play counts written into the files' tags by foo_playcount; its playlists come over as M3U files)

`merge` matches songs to the library (path, then artist and title, then file name) and folds the numbers in
without counting twice when an import is repeated: play and skip counts take the larger of the two, the last
play the later, and a rating only fills in a song you haven't rated."""
import datetime as dt
import os
import plistlib
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
import xml.parsers.expat
from urllib.parse import unquote, urlparse

from .db import fold


def _url_path(url):
    """A file path from a file:// URL (or the string itself when it is already a path)."""
    if not url:
        return ""
    url = str(url)
    if not url.lower().startswith("file:"):
        return url
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if parsed.netloc and parsed.netloc not in ("", "localhost"):  # file://server/share
        path = f"//{parsed.netloc}{path}"
    if len(path) > 2 and path[0] == "/" and path[2] == ":":  # /C:/Music -> C:/Music
        path = path[1:]
    return os.path.normpath(path) if os.sep == "\\" else path


def _rating5(value, scale):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0
    if v <= 0:
        return 0
    return max(1, min(5, round(v / scale * 5)))


def _int(value):
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _empty(source):
    return {"source": source, "songs": [], "playlists": []}


# --- Strawberry / Clementine ------------------------------------------------------------------------------------
def read_sqlite_player(path):
    """Strawberry's or Clementine's library database."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "songs" not in tables:
            raise ValueError("Not a Strawberry or Clementine library")
        cols = {r[1] for r in con.execute("PRAGMA table_info(songs)")}
        loc = "url" if "url" in cols else "filename" if "filename" in cols else None
        if loc is None:
            raise ValueError("Not a Strawberry or Clementine library")
        source = "Strawberry" if loc == "url" else "Clementine"
        out = _empty(source)
        skip = "skipcount" if "skipcount" in cols else "0"
        rows = con.execute(f"SELECT rowid AS id, {loc} AS loc, artist, title, playcount, {skip} AS skips, "
                           "lastplayed, rating FROM songs")
        by_id = {}
        for r in rows:
            song = {"path": _url_path(r["loc"]), "artist": r["artist"] or "", "title": r["title"] or "",
                    "plays": _int(r["playcount"]), "skips": _int(r["skips"]),
                    "rating": _rating5(r["rating"], 1.0) if (r["rating"] or 0) >= 0 else 0,
                    "last_played": max(0, int(r["lastplayed"] or 0))}
            by_id[r["id"]] = song
            out["songs"].append(song)
        if {"playlists", "playlist_items"} <= tables:
            items_cols = {r[1] for r in con.execute("PRAGMA table_info(playlist_items)")}
            link = "collection_id" if "collection_id" in items_cols else "library_id" if "library_id" in items_cols else None
            url_col = "url" if "url" in items_cols else None
            for pl in con.execute("SELECT rowid AS id, name FROM playlists ORDER BY rowid"):
                entries = []
                select = ", ".join(c for c in (link, url_col, "artist" if "artist" in items_cols else None,
                                               "title" if "title" in items_cols else None) if c)
                for it in con.execute(f"SELECT {select} FROM playlist_items WHERE playlist=? ORDER BY rowid", (pl["id"],)):
                    it = dict(it)
                    song = by_id.get(it.get(link)) if link else None
                    if song:
                        entries.append({"path": song["path"], "artist": song["artist"], "title": song["title"]})
                    elif it.get(url_col):
                        entries.append({"path": _url_path(it[url_col]), "artist": it.get("artist") or "",
                                        "title": it.get("title") or ""})
                if entries and pl["name"]:
                    out["playlists"].append({"name": pl["name"], "entries": entries})
        return out
    finally:
        con.close()


# --- Rhythmbox ---------------------------------------------------------------------------------------------------
def read_rhythmbox(path):
    """rhythmdb.xml (and playlists.xml beside it)."""
    out = _empty("Rhythmbox")
    root = ET.parse(path).getroot()
    if root.tag != "rhythmdb":
        raise ValueError("Not a Rhythmbox database")
    for e in root.iter("entry"):
        if e.get("type") != "song":
            continue
        out["songs"].append({
            "path": _url_path(e.findtext("location") or ""), "artist": e.findtext("artist") or "",
            "title": e.findtext("title") or "", "plays": _int(e.findtext("play-count")), "skips": 0,
            "rating": _rating5(e.findtext("rating"), 5), "last_played": _int(e.findtext("last-played")),
        })
    lists = os.path.join(os.path.dirname(path), "playlists.xml")
    if os.path.isfile(lists):
        for pl in ET.parse(lists).getroot().iter("playlist"):
            if pl.get("type") != "static" or not pl.get("name"):
                continue
            entries = [{"path": _url_path(loc.text or ""), "artist": "", "title": ""} for loc in pl.iter("location")]
            if entries:
                out["playlists"].append({"name": pl.get("name"), "entries": entries})
    return out


# --- iTunes-style XML (MusicBee, iTunes, Apple Music) --------------------------------------------------------------
def read_itunes_xml(path):
    with open(path, "rb") as fh:
        data = plistlib.load(fh)
    if not isinstance(data, dict) or "Tracks" not in data:
        raise ValueError("Not an iTunes-style library XML")
    app = str(data.get("Application Version", ""))
    out = _empty("MusicBee" if "musicbee" in str(data.get("Music Folder", "")).lower() or "MusicBee" in app
                 else "iTunes library")
    by_id = {}
    for tid, t in data["Tracks"].items():
        if not isinstance(t, dict) or not t.get("Location"):
            continue
        played = t.get("Play Date UTC")
        last = int(played.replace(tzinfo=dt.timezone.utc).timestamp()) if isinstance(played, dt.datetime) else 0
        song = {"path": _url_path(t["Location"]), "artist": t.get("Artist", ""), "title": t.get("Name", ""),
                "plays": _int(t.get("Play Count")), "skips": _int(t.get("Skip Count")),
                "rating": 0 if t.get("Rating Computed") else _rating5(t.get("Rating"), 100), "last_played": last}
        by_id[str(tid)] = song
        out["songs"].append(song)
    for pl in data.get("Playlists", []):
        if (not isinstance(pl, dict) or pl.get("Master") or pl.get("Distinguished Kind") or pl.get("Smart Info")
                or pl.get("Folder") or pl.get("Visible") is False or not pl.get("Name")):
            continue
        entries = []
        for item in pl.get("Playlist Items", []):
            song = by_id.get(str(item.get("Track ID")))
            if song:
                entries.append({"path": song["path"], "artist": song["artist"], "title": song["title"]})
        if entries:
            out["playlists"].append({"name": pl["Name"], "entries": entries})
    return out


# --- foobar2000 (statistics in tags) -------------------------------------------------------------------------------
_PLAYCOUNT_KEYS = ("PLAY_COUNT", "PLAY_COUNTER", "PLAYCOUNT", "FMPS_PLAYCOUNT", "TXXX:PLAY_COUNT",
                   "TXXX:PLAY_COUNTER", "----:com.apple.iTunes:PLAY_COUNT")
_LASTPLAYED_KEYS = ("LAST_PLAYED", "LAST_PLAYED_TIMESTAMP", "TXXX:LAST_PLAYED", "----:com.apple.iTunes:LAST_PLAYED")


def _tag(tags, keys):
    for key in keys:
        for k in (key, key.lower()):
            try:
                value = tags.get(k)
            except Exception:  # noqa: BLE001
                value = None
            if value:
                value = value[0] if isinstance(value, list) else value
                text = getattr(value, "text", value)
                text = text[0] if isinstance(text, list) and text else text
                if isinstance(text, bytes):
                    text = text.decode("utf-8", "replace")
                return str(text)
    return ""


def _last_played(text):
    text = (text or "").strip()
    if not text:
        return 0
    if text.isdigit():
        value = int(text)
        return value // 10_000_000 - 11_644_473_600 if value > 10**15 else value  # Windows FILETIME or unix
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return int(time.mktime(time.strptime(text[:19], fmt)))
        except ValueError:
            continue
    return 0


def read_tag_statistics(paths, should_stop=lambda: False):
    """Play counts that foobar2000 (foo_playcount) and similar players wrote into the files' tags."""
    import mutagen

    out = _empty("foobar2000")
    for path in paths:
        if should_stop():
            break
        try:
            f = mutagen.File(path)
        except Exception:  # noqa: BLE001
            continue
        tags = getattr(f, "tags", None)
        if not tags:
            continue
        plays = _int(_tag(tags, _PLAYCOUNT_KEYS))
        if plays:
            out["songs"].append({"path": path, "artist": "", "title": "", "plays": plays, "skips": 0, "rating": 0,
                                 "last_played": _last_played(_tag(tags, _LASTPLAYED_KEYS))})
    return out


# --- finding and reading --------------------------------------------------------------------------------------------
def known_locations():
    """[{"name", "path"}] for other players' libraries found in their usual places on this computer."""
    home = os.path.expanduser("~")
    data = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    candidates = [
        ("Strawberry", os.path.join(data, "strawberry", "strawberry", "strawberry.db")),
        ("Clementine", os.path.join(config, "Clementine", "clementine.db")),
        ("Rhythmbox", os.path.join(data, "rhythmbox", "rhythmdb.xml")),
        ("iTunes", os.path.join(home, "Music", "iTunes", "iTunes Music Library.xml")),
        ("iTunes", os.path.join(home, "Music", "iTunes", "iTunes Library.xml")),
        ("MusicBee", os.path.join(home, "Music", "MusicBee", "iTunes Music Library.xml")),
    ]
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        candidates += [("Strawberry", os.path.join(local, "strawberry", "strawberry", "strawberry.db")),
                       ("Clementine", os.path.join(home, ".config", "Clementine", "clementine.db"))]
    if sys.platform == "darwin":
        candidates.append(("Strawberry", os.path.join(home, "Library", "Application Support", "Strawberry",
                                                       "Strawberry", "strawberry.db")))
    seen, found = set(), []
    for name, path in candidates:
        if os.path.isfile(path) and path not in seen:
            seen.add(path)
            found.append({"name": name, "path": path})
    return found


def read(path):
    """Whatever player library `path` is (by its contents). A damaged file raises ValueError."""
    with open(path, "rb") as fh:
        head = fh.read(512)
    try:
        if head.startswith(b"SQLite format 3"):
            return read_sqlite_player(path)
        text = head.decode("utf-8", "replace")
        if "<rhythmdb" in text:
            return read_rhythmbox(path)
        if "<plist" in text or "<!DOCTYPE plist" in text:
            return read_itunes_xml(path)
    except (ET.ParseError, xml.parsers.expat.ExpatError, plistlib.InvalidFileException, sqlite3.DatabaseError,
            AttributeError, TypeError, KeyError) as exc:
        raise ValueError(f"That file looks damaged ({exc.__class__.__name__})") from exc
    raise ValueError("That isn't a library file Hallucinate can read (Strawberry, Clementine, Rhythmbox, "
                     "MusicBee or iTunes)")


def merge(db, imported, now=None):
    """Fold an imported library into ours. Returns {"source", "songs", "matched", "plays", "skips", "ratings",
    "playlists"}."""
    tracks = db._rows("SELECT path, s_artist, s_title FROM tracks")
    by_path = {r["path"] for r in tracks}
    by_casepath = {r["path"].casefold(): r["path"] for r in tracks}
    by_tags = {}
    by_name = {}
    for r in tracks:
        by_tags.setdefault((r["s_artist"], r["s_title"]), r["path"])
        by_name.setdefault(os.path.basename(r["path"]).casefold(), r["path"])

    def match(e):
        p = e.get("path") or ""
        if p in by_path:
            return p
        if p.casefold() in by_casepath:  # Windows paths in another case
            return by_casepath[p.casefold()]
        if e.get("title"):
            hit = by_tags.get((fold(e.get("artist") or ""), fold(e["title"])))
            if hit:
                return hit
        return by_name.get(os.path.basename(p.replace("\\", "/")).casefold()) if p else None

    rated = set(db.ratings())
    result = {"source": imported["source"], "songs": len(imported["songs"]), "matched": 0, "plays": 0, "skips": 0,
              "ratings": 0, "playlists": 0}
    for song in imported["songs"]:
        path = match(song)
        if not path:
            continue
        result["matched"] += 1
        plays, last = song.get("plays", 0), song.get("last_played", 0)
        if plays or last:
            cur = db.conn.execute("SELECT count, last FROM plays WHERE path=?", (path,)).fetchone()
            count, prev = (cur[0], cur[1]) if cur else (0, 0.0)
            if plays > count or last > prev:
                db.conn.execute(
                    "INSERT INTO plays(path, count, last) VALUES(?,?,?) "
                    "ON CONFLICT(path) DO UPDATE SET count=excluded.count, last=excluded.last",
                    (path, max(count, plays), max(prev, float(last or 0))))
                result["plays"] += max(0, plays - count)
        if song.get("skips"):
            cur = db.conn.execute("SELECT count FROM skips WHERE path=?", (path,)).fetchone()
            have = cur[0] if cur else 0
            if song["skips"] > have:
                db.conn.execute(
                    "INSERT INTO skips(path, count, last) VALUES(?,?,?) "
                    "ON CONFLICT(path) DO UPDATE SET count=excluded.count",
                    (path, song["skips"], float(song.get("last_played") or 0)))
                result["skips"] += song["skips"] - have
        if song.get("rating") and path not in rated:
            db.set_rating(path, song["rating"])
            rated.add(path)
            result["ratings"] += 1
    existing = {r[0].casefold() for r in db.conn.execute("SELECT name FROM playlists")}
    for pl in imported["playlists"]:
        if pl["name"].casefold() in existing:
            continue  # imported before (or you have one with that name)
        paths = [p for p in (match(e) for e in pl["entries"]) if p]
        if paths:
            pid = db.create_playlist(pl["name"])
            db.playlist_add(pid, paths)
            existing.add(pl["name"].casefold())
            result["playlists"] += 1
    db.commit()
    return result
