"""Composers to browse: who wrote what in the library, and one composer's page (their works, each with its
movements in order, then their other songs and the albums they're on). A song may credit several composers
("Lennon; McCartney"): it counts for each of them.

Pure functions over a Database."""
import re
from collections import Counter

from .genres import fold  # (as db.fold; db uses this module)

# several composers in one tag: separate values (read as "; ") or written with a separator (not "/" or "&":
# "Lennon/McCartney" and "Simon & Garfunkel" are each one credit as often as not)
_SPLIT = re.compile(r"\s*[;|\x00]\s*")


def split(text):
    """The composers credited in a tag's text, each once."""
    out, seen = [], set()
    for part in _SPLIT.split(text or ""):
        name = " ".join(part.split())
        if name and fold(name) not in seen:
            seen.add(fold(name))
            out.append(name)
    return out


def has(text, name):
    wanted = fold(name or "").strip()
    return bool(wanted) and any(fold(c) == wanted for c in split(text))


def _like(name):
    return "%" + fold(name).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def overview(db):
    """[{name, tracks, works, albums, seconds, art, albumKey}] for every composer, most songs first."""
    names, tracks, seconds, works, albums, cover = {}, Counter(), Counter(), {}, {}, {}
    for composer, work, album_key, duration, art in db.conn.execute(
            "SELECT composer, work, album_key, duration, art FROM tracks WHERE composer != ''"):
        for name in split(composer):
            key = fold(name)
            names.setdefault(key, name)
            tracks[key] += 1
            seconds[key] += duration or 0
            if work:
                works.setdefault(key, set()).add(fold(work))
            albums.setdefault(key, set()).add(album_key)
            if art and key not in cover:
                cover[key] = (art, album_key)
    out = [{"name": name, "tracks": tracks[key], "seconds": float(seconds[key]),
            "works": len(works.get(key, ())), "albums": len(albums[key]),
            "art": cover.get(key, ("", ""))[0], "albumKey": cover.get(key, ("", ""))[1]}
           for key, name in names.items()]
    out.sort(key=lambda c: (-c["tracks"], fold(c["name"])))
    return out


def tracks(db, name):
    """Every song a composer wrote: work by work (movements in order), then the rest album by album."""
    rows = [r for r in db._rows("SELECT * FROM tracks WHERE s_composer LIKE ? ESCAPE '\\'", (_like(name),))
            if has(r["composer"], name)]
    rows.sort(key=lambda r: (not r["work"], fold(r["work"]), r["movement_no"] or 0, fold(r["album"]),
                             r["disc_no"] or 0, r["track_no"] or 0, fold(r["title"])))
    return rows


def page(db, name):
    """One composer: {name, tracks, seconds, works: [{work, songs, seconds}], others (songs without a work),
    albumList, performers (who plays them, most songs first)}."""
    rows = tracks(db, name)
    wanted = fold(name)
    shown = name
    works, others, album_rows, performers = {}, [], {}, Counter()
    for r in rows:
        for c in split(r["composer"]):
            if fold(c) == wanted:
                shown = c
        if r["work"]:
            w = works.setdefault(fold(r["work"]), {"work": r["work"], "songs": [], "seconds": 0.0})
            w["songs"].append(r)
            w["seconds"] += r["duration"] or 0
        else:
            others.append(r)
        a = album_rows.setdefault(r["album_key"], {
            "album_key": r["album_key"], "album": r["album"], "album_artist": r["album_artist"],
            "year": r["year"] or 0, "n": 0, "art": ""})
        a["n"] += 1
        a["art"] = a["art"] or r["art"] or ""
        performers[r["artist"] or r["album_artist"] or ""] += 1
    performers.pop("", None)
    return {"name": shown, "tracks": len(rows), "seconds": sum(r["duration"] or 0 for r in rows),
            "works": list(works.values()), "others": others,
            "albumList": sorted(album_rows.values(), key=lambda a: (-a["n"], fold(a["album"]))),
            "performers": [{"name": n, "tracks": k} for n, k in performers.most_common(12)
                           if fold(n) != wanted]}
