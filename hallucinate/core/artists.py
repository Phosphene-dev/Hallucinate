"""An artist's page: what you have by them and how you've listened to them.

Pure functions over a Database. Artists are matched the way the library groups them: case- and accent-folded
album artist (`s_aa`) for their own albums, and track artist for songs on other people's records."""
import datetime
import time

from . import genres as genre_names
from .db import fold

DAY = 86_400


def profile(db, name, now=None, top=5, months=12):
    """Facts, your listening and most played songs for one artist (see the keys below)."""
    now = time.time() if now is None else now
    key = fold(name)
    row = db.conn.execute(
        """SELECT COUNT(*) AS tracks, COUNT(DISTINCT album_key) AS albums, COALESCE(SUM(duration), 0) AS seconds,
                  MIN(CASE WHEN year > 0 THEN year END) AS first_year, MAX(year) AS last_year
           FROM tracks WHERE s_aa = ?""",
        (key,),
    ).fetchone()
    genres = {}
    for (g,) in db.conn.execute("SELECT genre FROM tracks WHERE s_aa = ? AND genre != ''", (key,)):
        for pos, part in enumerate(genre_names.split(g)):
            genres[part] = genres.get(part, 0) + (2 if pos == 0 else 1)  # the main genre counts more
    listens = db.conn.execute(
        """SELECT COUNT(*) AS plays, COALESCE(SUM(duration), 0) AS seconds, MIN(ts) AS first, MAX(ts) AS last
           FROM play_log WHERE s_artist = ?""",
        (key,),
    ).fetchone()
    # How this artist ranks among everyone you've played (by listens in the log)
    rank = 0
    if listens["plays"]:
        rank = 1 + db.conn.execute(
            """SELECT COUNT(*) FROM (SELECT COUNT(*) AS n FROM play_log GROUP BY s_artist)
               WHERE n > ?""",
            (listens["plays"],),
        ).fetchone()[0]
    # Plays per month for the last `months` months, oldest first
    today = datetime.date.fromtimestamp(now)
    starts = []
    y, m = today.year, today.month
    for _ in range(months):
        starts.append(datetime.date(y, m, 1))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    starts.reverse()
    first_ts = time.mktime(starts[0].timetuple())
    per_month = {s.strftime("%Y-%m"): 0 for s in starts}
    for (ts,) in db.conn.execute("SELECT ts FROM play_log WHERE s_artist = ? AND ts >= ?", (key, first_ts)):
        label = datetime.date.fromtimestamp(ts).strftime("%Y-%m")
        if label in per_month:
            per_month[label] += 1
    top_tracks = db._rows(
        """SELECT t.*, COALESCE(p.count, 0) AS plays FROM tracks t LEFT JOIN plays p ON p.path = t.path
           WHERE t.s_aa = ? OR t.s_artist = ?
           ORDER BY plays DESC, t.year, t.album_key, t.disc_no, t.track_no LIMIT ?""",
        (key, key, top),
    )
    appears_on = db._rows(
        """SELECT album_key, MIN(album) AS album, MIN(album_artist) AS album_artist, MAX(year) AS year,
                  COUNT(*) AS n, SUM(duration) AS duration, MAX(art) AS art
           FROM tracks WHERE s_artist = ? AND s_aa != ? GROUP BY album_key ORDER BY MAX(year), MIN(s_album)""",
        (key, key),
    )
    return {
        "tracks": row["tracks"], "albums": row["albums"], "seconds": float(row["seconds"]),
        "firstYear": row["first_year"] or 0, "lastYear": row["last_year"] or 0,
        "genres": [g for g, _ in sorted(genres.items(), key=lambda kv: (-kv[1], kv[0]))[:3]],
        "plays": listens["plays"], "listenSeconds": float(listens["seconds"]),
        "firstPlayed": listens["first"] or 0, "lastPlayed": listens["last"] or 0, "rank": rank,
        "months": [{"month": k, "plays": v} for k, v in per_month.items()],
        "topTracks": top_tracks, "appearsOn": appears_on,
    }


def discography(albums):
    """The artist's albums grouped by year, oldest first; albums without a year last.

    Returns [{"year": 1998, "albums": [...]}, ...]."""
    years = {}
    for a in albums:
        years.setdefault(a.get("year") or 0, []).append(a)
    order = sorted(y for y in years if y > 0) + ([0] if 0 in years else [])
    return [{"year": y, "albums": sorted(years[y], key=lambda a: (a.get("album") or "").casefold())} for y in order]
