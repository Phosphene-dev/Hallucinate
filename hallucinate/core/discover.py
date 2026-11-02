"""Discover: finding music again in your own library. Everything here reads only this computer's library and
listening history (nothing goes online), on the library's reader thread, and is plain SQL and Python (no Qt) so it
can be tested on its own.

- forgotten(): albums, songs and artists you played a lot or loved but not for a while, deep cuts from the artists
  you play most (their songs you've never played), and albums added long ago and never played.
- on_this_day(): what you listened to around today's date one, two, … years ago.
- daily_mixes(): a few mixes made fresh each day from what you listen to, each around a genre (and an era, where
  one genre covers several), mostly songs you play with some you haven't yet.

Anything can be marked "Not interested" (dismiss()): it's left out of every shelf from then on, until it's let
back in from Settings (undismiss(), dismissed())."""
import datetime
import random
import time

from . import genres
from .i18n import fill, translate
from .insights import _ALBUM_COLS, _month_year

DAY = 86400
KINDS = ("album", "song", "artist")


def _album_artist_key():
    return "CASE WHEN t.album_artist != '' THEN t.s_aa ELSE t.s_artist END"


def _not_dismissed(kind, column):
    return f"{column} NOT IN (SELECT key FROM discover_dismissed WHERE kind = '{kind}')"


# --- "Not interested" ----------------------------------------------------------------------------------------
def dismiss(db, kind, key, label="", now=None):
    if kind not in KINDS or not key:
        return
    db.conn.execute("INSERT OR REPLACE INTO discover_dismissed(kind, key, label, at) VALUES(?,?,?,?)",
                    (kind, str(key), str(label or "")[:200], time.time() if now is None else now))
    db.conn.commit()


def undismiss(db, kind, key):
    db.conn.execute("DELETE FROM discover_dismissed WHERE kind=? AND key=?", (kind, str(key)))
    db.conn.commit()


def undismiss_all(db):
    db.conn.execute("DELETE FROM discover_dismissed")
    db.conn.commit()


def dismissed(db):
    """[{"kind", "key", "label", "at"}], newest first (Settings lists them, each to let back in)."""
    return db._rows("SELECT kind, key, label, at FROM discover_dismissed ORDER BY at DESC")


def artist_key(row):
    from .db import fold

    return fold(row.get("album_artist") or row.get("artist") or "")


# --- forgotten favourites --------------------------------------------------------------------------------------
def forgotten(db, now=None, min_days=90, limit=24, seed=None):
    """{"albums", "songs", "artists", "deepCuts", "neverPlayed"}: each a list of rows with a "reason" (why it's
    there, in a few words)."""
    now = time.time() if now is None else now
    cutoff = now - max(7, int(min_days)) * DAY
    rng = random.Random(seed if seed is not None else datetime.date.fromtimestamp(now).isoformat())

    albums = db._rows(
        f"""SELECT {_ALBUM_COLS}, SUM(p.count) AS plays, MAX(p.last) AS last
            FROM tracks t JOIN plays p ON p.path = t.path
            WHERE {_not_dismissed('album', 't.album_key')}
            GROUP BY t.album_key HAVING MAX(p.last) < ? AND SUM(p.count) >= 3
            ORDER BY plays DESC, last LIMIT ?""", (cutoff, limit))
    for a in albums:
        a["reason"] = fill(translate("Discover", "Played %1 times, last in %2"), a["plays"], _month_year(a["last"]))

    songs = db._rows(
        f"""SELECT t.*, COALESCE(p.count, 0) AS plays, p.last AS last,
                   l.path IS NOT NULL AS liked, COALESCE(r.stars, 0) AS stars
            FROM tracks t LEFT JOIN plays p ON p.path = t.path
            LEFT JOIN likes l ON l.path = t.path LEFT JOIN ratings r ON r.path = t.path
            WHERE (p.last IS NULL OR p.last < ?)
              AND (COALESCE(p.count, 0) >= 5 OR l.path IS NOT NULL OR COALESCE(r.stars, 0) >= 4)
              AND {_not_dismissed('song', 't.path')}
            ORDER BY COALESCE(p.count, 0) + 5 * (l.path IS NOT NULL) + 2 * COALESCE(r.stars, 0) DESC, t.s_title
            LIMIT ?""", (cutoff, limit * 2))
    for s in songs:
        if s["last"]:
            s["reason"] = fill(translate("Discover", "Last played %1"), _month_year(s["last"]))
        else:
            s["reason"] = translate("Discover", "Loved, never played here")

    artists = db._rows(
        f"""SELECT MIN(CASE WHEN t.album_artist != '' THEN t.album_artist ELSE t.artist END) AS name,
                   SUM(p.count) AS plays, MAX(p.last) AS last, COUNT(DISTINCT t.album_key) AS albums,
                   COUNT(*) AS tracks, MAX(t.art) AS art
            FROM tracks t JOIN plays p ON p.path = t.path
            WHERE {_not_dismissed('artist', _album_artist_key())}
            GROUP BY {_album_artist_key()} HAVING MAX(p.last) < ? AND SUM(p.count) >= 10
            ORDER BY plays DESC LIMIT ?""", (cutoff, limit))
    for a in artists:
        a["reason"] = fill(translate("Discover", "Last played %1"), _month_year(a["last"]))

    # deep cuts: the songs you've never played by the artists you play most
    top = [r[0] for r in db.conn.execute(
        f"""SELECT {_album_artist_key()} AS k FROM tracks t JOIN plays p ON p.path = t.path
            GROUP BY k ORDER BY SUM(p.count) DESC LIMIT 15""")]
    deep = []
    if top:
        marks = ",".join("?" * len(top))
        pool = db._rows(
            f"""SELECT t.* FROM tracks t LEFT JOIN plays p ON p.path = t.path LEFT JOIN skips k ON k.path = t.path
                WHERE {_album_artist_key()} IN ({marks}) AND p.path IS NULL AND COALESCE(k.count, 0) < 2
                  AND {_not_dismissed('song', 't.path')}
                LIMIT 2000""", top)
        rng.shuffle(pool)
        per_artist = {}
        for s in pool:  # a few from each, not a whole album from one
            k = artist_key(s)
            if per_artist.get(k, 0) < 3:
                per_artist[k] = per_artist.get(k, 0) + 1
                s["reason"] = fill(translate("Discover", "Never played, by %1"), s.get("album_artist") or s["artist"])
                deep.append(s)
            if len(deep) >= limit:
                break

    never = db._rows(
        f"""SELECT {_ALBUM_COLS}, MIN(t.added) AS added FROM tracks t
            WHERE NOT EXISTS (SELECT 1 FROM tracks t2 JOIN plays p ON p.path = t2.path
                              WHERE t2.album_key = t.album_key)
              AND {_not_dismissed('album', 't.album_key')}
            GROUP BY t.album_key HAVING MIN(t.added) < ?
            ORDER BY random() LIMIT ?""", (now - 30 * DAY, limit))
    for a in never:
        a["reason"] = fill(translate("Discover", "Added %1, never played"), _month_year(a["added"]))

    return {"albums": albums, "songs": songs[:limit], "artists": artists, "deepCuts": deep, "neverPlayed": never}


# --- on this day -----------------------------------------------------------------------------------------------
def on_this_day(db, now=None, window_days=3, years=10, per_year=12):
    """[{"years", "label", "year", "albums", "songs"}], one for each year (1, 2, … years ago) you listened around
    today's date, nearest first."""
    now = time.time() if now is None else now
    today = datetime.date.fromtimestamp(now)
    out = []
    for back in range(1, years + 1):
        try:
            centre = today.replace(year=today.year - back)
        except ValueError:  # (29 February)
            centre = today.replace(year=today.year - back, day=28)
        lo = time.mktime((centre - datetime.timedelta(days=window_days)).timetuple())
        hi = time.mktime((centre + datetime.timedelta(days=window_days + 1)).timetuple())
        counts = db.conn.execute(
            "SELECT path, COUNT(*) AS n FROM play_log WHERE ts >= ? AND ts < ? AND path IS NOT NULL "
            "GROUP BY path ORDER BY n DESC LIMIT 500", (lo, hi)).fetchall()
        if not counts:
            continue
        paths = [r[0] for r in counts]
        marks = ",".join("?" * len(paths))
        rank = {p: i for i, p in enumerate(paths)}
        songs = sorted(db._rows(
            f"SELECT t.* FROM tracks t WHERE t.path IN ({marks}) AND {_not_dismissed('song', 't.path')}", paths),
            key=lambda s: rank.get(s["path"], 1 << 30))
        if not songs:
            continue
        by_path, album_plays = dict(counts), {}
        for s in songs:
            album_plays[s["album_key"]] = album_plays.get(s["album_key"], 0) + by_path[s["path"]]
        keys = sorted(album_plays, key=lambda k: -album_plays[k])[:per_year]
        kmarks = ",".join("?" * len(keys))
        by_key = {a["album_key"]: a for a in db._rows(
            f"SELECT {_ALBUM_COLS} FROM tracks t WHERE t.album_key IN ({kmarks}) "
            f"AND {_not_dismissed('album', 't.album_key')} GROUP BY t.album_key", keys)}
        albums = [by_key[k] for k in keys if k in by_key]
        label = translate("Discover", "%n year(s) ago", None, back)
        for a in albums:
            a["reason"] = fill(translate("Discover", "Around this day in %1"), centre.year)
        out.append({"years": back, "year": centre.year, "label": label, "albums": albums,
                    "songs": songs[:per_year * 2]})
    return out


# --- daily mixes ----------------------------------------------------------------------------------------------
def _decade(year):
    return (int(year) // 10) * 10 if year and int(year) >= 1900 else 0


def _decade_label(decade):
    return translate("Discover", "the '%1s").replace("%1", f"{decade % 100:02d}") if decade else ""


def daily_mixes(db, now=None, count=4, size=40, fresh=0.25, max_per_artist=3):
    """Up to `count` mixes for today: [{"id", "title", "subtitle", "arts", "songs"}]. The same all day (seeded by
    the date), different tomorrow. Each is around one of the genres you listen to most (with an era when that
    genre spans several decades of your listening); about `fresh` of each mix are songs from it you haven't
    played yet. A library without genres gets mixes by era instead."""
    now = time.time() if now is None else now
    today = datetime.date.fromtimestamp(now).isoformat()
    played = db._rows(
        f"""SELECT t.path, t.genre, t.year, {_album_artist_key()} AS ak, p.count AS plays, p.last AS last
            FROM tracks t JOIN plays p ON p.path = t.path
            WHERE {_not_dismissed('song', 't.path')}""")
    if not played:
        return []
    # how much of your listening each genre (and genre + decade) is, recent listening counting for more
    weight_g, weight_gd, weight_d = {}, {}, {}
    for r in played:
        recent = 1.0 + (1.0 if r["last"] and now - r["last"] < 60 * DAY else 0.0)
        w = (r["plays"] or 0) * recent
        g = genres.main(r["genre"])
        d = _decade(r["year"])
        if g:
            weight_g[g] = weight_g.get(g, 0) + w
            if d:
                weight_gd[(g, d)] = weight_gd.get((g, d), 0) + w
        if d:
            weight_d[d] = weight_d.get(d, 0) + w
    clusters = []
    for g, w in sorted(weight_g.items(), key=lambda kv: -kv[1]):
        decades = sorted(((d, wd) for (gg, d), wd in weight_gd.items() if gg == g), key=lambda kv: -kv[1])
        if len(decades) >= 2 and decades[0][1] < 0.7 * w:  # a genre spread over eras: its biggest era as its own mix
            clusters.append(("gd", g, decades[0][0]))
        else:
            clusters.append(("g", g, 0))
        if len(clusters) >= count:
            break
    if len(clusters) < count:
        for d, _w in sorted(weight_d.items(), key=lambda kv: -kv[1]):
            if len(clusters) >= count:
                break
            if not any(c[2] == d and c[0] == "d" for c in clusters):
                clusters.append(("d", "", d))
    mixes = []
    plays_by_path = {r["path"]: r["plays"] or 0 for r in played}
    for kind, g, d in clusters[:count]:
        where, params = ["1"], []
        if g:
            sql, ps = genres.prefilter(g, "t.s_genre")
            where.append(sql)
            params += ps
        if d:
            where.append("t.year >= ? AND t.year < ?")
            params += [d, d + 10]
        rows = db._rows(
            f"SELECT t.* FROM tracks t WHERE {' AND '.join(where)} AND {_not_dismissed('song', 't.path')} LIMIT 20000",
            params)
        if g:
            rows = [r for r in rows if genres.main(r["genre"]) and genres.has(r["genre"], g)]
        if len(rows) < 8:
            continue
        rng = random.Random(f"{today}:{kind}:{g}:{d}")
        known = [r for r in rows if r["path"] in plays_by_path]
        new = [r for r in rows if r["path"] not in plays_by_path]
        # known songs drawn with your plays as the odds; new ones at random
        known.sort(key=lambda r: -(plays_by_path[r["path"]] + 1) * rng.random())
        rng.shuffle(new)
        want_new = int(size * fresh) if new else 0
        picked, per_artist = [], {}
        artists = len({artist_key(r) for r in rows}) or 1
        cap = max(max_per_artist, -(-size // artists))  # (a genre with only a few artists: more of each)

        def take(pool, n):
            for r in pool:
                if n <= 0:
                    break
                k = artist_key(r)
                if per_artist.get(k, 0) >= cap or r in picked:
                    continue
                per_artist[k] = per_artist.get(k, 0) + 1
                picked.append(r)
                n -= 1

        take(known, size - want_new)
        take(new, size - len(picked))
        take(known, size - len(picked))  # (not enough new ones: more you know)
        if len(picked) < 8:
            continue
        rng.shuffle(picked)
        if kind == "gd":
            title = fill(translate("Discover", "%1 from %2"), g, _decade_label(d))
        elif kind == "g":
            title = fill(translate("Discover", "%1 mix"), g)
        else:
            title = fill(translate("Discover", "Music from %1"), _decade_label(d))
        names = []
        for r in picked:
            name = r.get("album_artist") or r.get("artist") or ""
            if name and name not in names:
                names.append(name)
        subtitle = fill(translate("Discover", "%1 and more"), ", ".join(names[:3])) if names else ""
        arts = []
        for r in picked:
            if r.get("art") and r["art"] not in arts:
                arts.append(r["art"])
            if len(arts) >= 4:
                break
        mixes.append({"id": f"{kind}:{g}:{d}", "title": title, "subtitle": subtitle, "arts": arts, "songs": picked})
    return mixes
