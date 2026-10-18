"""Genres to browse: every genre in the library with what it holds, and one genre's own page (its albums,
artists and songs, and the genres that go with it). Songs count for each of their genres ("IDM; Ambient" is
under both), so a genre page finds every song tagged with it, main genre or not.

Pure functions over a Database."""
from collections import Counter

from . import genres as genre_names
from .db import fold


def overview(db):
    """[{name, albums, artists, tracks, seconds, art, albumKey}] for every genre, most songs first. `art` is a
    cover from the genre's biggest album."""
    names, tracks, seconds, albums, artists = {}, Counter(), Counter(), {}, {}
    album_size, cover = Counter(), {}
    for genre, album_key, s_aa, duration, art in db.conn.execute(
            "SELECT genre, album_key, s_aa, duration, art FROM tracks WHERE genre != ''"):
        for name in genre_names.split(genre):
            key = fold(name)
            names.setdefault(key, name)
            tracks[key] += 1
            seconds[key] += duration or 0
            albums.setdefault(key, set()).add(album_key)
            artists.setdefault(key, set()).add(s_aa)
            album_size[(key, album_key)] += 1
            if art and (key, album_key) not in cover:
                cover[(key, album_key)] = art
    out = []
    for key, name in names.items():
        best = max(albums[key], key=lambda a: (album_size[(key, a)], (key, a) in cover, a))
        out.append({"name": name, "tracks": tracks[key], "seconds": float(seconds[key]),
                    "albums": len(albums[key]), "artists": len(artists[key]),
                    "art": cover.get((key, best), ""), "albumKey": best})
    out.sort(key=lambda g: (-g["tracks"], fold(g["name"])))
    return out


def page(db, name, top=200):
    """One genre: {name, tracks, albums, artists, seconds, albumList, artistList, songs (the most played,
    up to `top`), related: [{name, tracks}]}. `name` is matched case- and accent-insensitively."""
    sql, args = genre_names.prefilter(name, "t.s_genre")  # most songs ruled out without calling into Python
    rows = db._rows(
        f"""SELECT t.*, COALESCE(p.count, 0) AS plays FROM tracks t LEFT JOIN plays p ON p.path = t.path
            WHERE {sql} AND genre_has(t.genre, ?)""",
        (*args, name),
    )
    wanted = fold(name)
    shown = name
    related, album_rows, artist_rows = Counter(), {}, {}
    seconds = 0.0
    for r in rows:
        seconds += r["duration"] or 0
        for g in genre_names.split(r["genre"]):
            if fold(g) == wanted:
                shown = g
            else:
                related[g] += 1
        a = album_rows.setdefault(r["album_key"], {
            "album_key": r["album_key"], "album": r["album"], "album_artist": r["album_artist"],
            "year": r["year"] or 0, "n": 0, "duration": 0.0, "art": "", "plays": 0})
        a["n"] += 1
        a["duration"] += r["duration"] or 0
        a["plays"] += r["plays"]
        a["art"] = a["art"] or r["art"] or ""
        artist = r["album_artist"] or r["artist"] or ""
        ar = artist_rows.setdefault(fold(artist), {"name": artist, "tracks": 0, "plays": 0, "art": ""})
        ar["tracks"] += 1
        ar["plays"] += r["plays"]
        ar["art"] = ar["art"] or r["art"] or ""
    album_list = sorted(album_rows.values(), key=lambda a: (-a["plays"], -a["n"], fold(a["album"])))
    artist_list = sorted(artist_rows.values(), key=lambda a: (-a["tracks"], -a["plays"], fold(a["name"])))
    songs = sorted(rows, key=lambda r: (-r["plays"], fold(r["title"])))[:top]
    return {"name": shown, "tracks": len(rows), "albums": len(album_rows), "artists": len(artist_rows),
            "seconds": seconds, "albumList": album_list, "artistList": artist_list, "songs": songs,
            "related": [{"name": g, "tracks": n} for g, n in related.most_common(12)]}


def tracks(db, name):
    """Every song of a genre, album by album, for playing it all."""
    sql, args = genre_names.prefilter(name)
    return db._rows(
        f"""SELECT * FROM tracks WHERE {sql} AND genre_has(genre, ?)
            ORDER BY s_aa, year, album_key, disc_no, track_no""",
        (*args, name),
    )


# How the Songs page can be ordered: a key for sorting song rows (dicts as the Songs page holds them)
SONG_SORTS = ("title", "artist", "album", "genre", "year")


def song_sort_key(sort):
    def text(v):
        return fold(v or "")

    if sort == "artist":
        return lambda t: (text(t.get("artist")), text(t.get("album")), t.get("disc_no") or 0, t.get("track_no") or 0)
    if sort == "album":
        return lambda t: (text(t.get("album")), t.get("disc_no") or 0, t.get("track_no") or 0)
    if sort == "genre":  # by main genre; songs without one last
        return lambda t: (not t.get("genre"), text(genre_names.main(t.get("genre"))), text(t.get("artist")),
                          text(t.get("album")), t.get("disc_no") or 0, t.get("track_no") or 0)
    if sort == "year":
        return lambda t: (-(t.get("year") or 0), text(t.get("album")), t.get("disc_no") or 0, t.get("track_no") or 0)
    return None
