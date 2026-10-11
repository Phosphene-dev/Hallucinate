"""Listening recaps: a week, a month or a year of your listening, summed up.

Pure functions over a Database, built on core.history's filters. A period is "week:YYYY-MM-DD" (any day in the
week; weeks start on Monday), "month:YYYY-MM" or "year:YYYY"; `step` moves to the previous or next one."""
import datetime
import time

from . import history

KINDS = ("week", "month", "year")


def current(kind, now=None):
    """The period of `kind` containing `now`."""
    today = datetime.date.fromtimestamp(time.time() if now is None else now)
    if kind == "week":
        return "week:" + (today - datetime.timedelta(days=today.weekday())).isoformat()
    if kind == "month":
        return f"month:{today:%Y-%m}"
    return f"year:{today.year}"


def parse(period):
    """(kind, first day, day after the last) for a period string; ValueError when it isn't one."""
    kind, _, value = (period or "").partition(":")
    if kind == "week":
        day = datetime.date.fromisoformat(value)
        first = day - datetime.timedelta(days=day.weekday())
        return kind, first, first + datetime.timedelta(days=7)
    if kind == "month":
        first = datetime.date.fromisoformat(value + "-01")
        return kind, first, (first + datetime.timedelta(days=32)).replace(day=1)
    if kind == "year":
        first = datetime.date(int(value), 1, 1)
        return kind, first, datetime.date(first.year + 1, 1, 1)
    raise ValueError(f"not a recap period: {period!r}")


def step(period, delta):
    """The period `delta` steps before (negative) or after (positive) `period`."""
    kind, first, _end = parse(period)
    if kind == "week":
        return "week:" + (first + datetime.timedelta(days=7 * delta)).isoformat()
    if kind == "month":
        months = first.year * 12 + first.month - 1 + delta
        return f"month:{months // 12:04d}-{months % 12 + 1:02d}"
    return f"year:{first.year + delta}"


def title(period, now=None):
    """"This week", "Last month", "September 2026", "Week of 5 Oct 2026", "2026"…"""
    kind, first, end = parse(period)
    if period == current(kind, now):
        return {"week": "This week", "month": "This month", "year": "This year"}[kind]
    if period == step(current(kind, now), -1):
        return {"week": "Last week", "month": "Last month", "year": "Last year"}[kind]
    if kind == "week":
        return f"Week of {first.day} {first:%b %Y}"
    if kind == "month":
        return f"{first:%B %Y}"
    return str(first.year)


def _ts(day):
    return time.mktime(day.timetuple())


def _top(db, group, cols, start, end, limit):
    """Most played in the window, grouped by `group`; aggregates the log alone, then looks up the library
    (album key, cover, length) only for the winners through one of their files."""
    rows = db._rows(
        f"""SELECT {cols}, MAX(l.path) AS path, COUNT(*) AS plays, COALESCE(SUM(l.duration), 0) AS seconds
            FROM play_log l WHERE l.ts >= ? AND l.ts < ? GROUP BY {group}
            ORDER BY plays DESC, seconds DESC LIMIT ?""",
        (start, end, limit),
    )
    for r in rows:
        t = db.conn.execute(
            "SELECT album_key, art, duration FROM tracks WHERE path = ?", (r["path"] or "",)
        ).fetchone()
        r["album_key"], r["art"], r["duration"] = (t["album_key"], t["art"], t["duration"]) if t else ("", "", 0)
        r["path"] = r["path"] or ""
    return rows


def recap(db, period, now=None, limit=5):
    """Everything the recap page shows for one period:

    title, kind, start/end (ISO dates), the history summary, change in listening time against the previous
    period (`change`, a ratio, None when there is nothing to compare), top artists/albums/songs, artists heard
    for the first time (`discoveries`, `discoveryCount`), top genres, busiest day, listening by hour of day and by
    weekday, the longest streak of days in a row, albums added, and for a year listening per month."""
    kind, first, end_day = parse(period)
    start, end = _ts(first), _ts(end_day)
    summary = history.summary(db, start=start, end=end)
    prev_kind, prev_first, prev_end = parse(step(period, -1))
    previous = history.summary(db, start=_ts(prev_first), end=_ts(prev_end))
    change = (summary["seconds"] - previous["seconds"]) / previous["seconds"] if previous["seconds"] else None

    artists = _top(db, "l.s_artist", "MIN(l.artist) AS name", start, end, limit)
    albums = _top(db, "l.s_artist, l.s_album", "MIN(l.album) AS album, MIN(l.artist) AS album_artist",
                  start, end, limit)
    songs = _top(db, "l.s_artist, l.s_title", "MIN(l.title) AS title, MIN(l.artist) AS artist, MIN(l.album) AS album",
                 start, end, limit)
    discoveries = db._rows(
        """SELECT MIN(l.artist) AS name, COUNT(*) AS plays, MAX(l.path) AS path
           FROM play_log l
           WHERE l.ts >= ? AND l.ts < ?
             AND NOT EXISTS (SELECT 1 FROM play_log o WHERE o.s_artist = l.s_artist AND o.ts < ?)
           GROUP BY l.s_artist ORDER BY plays DESC""",
        (start, end, start),
    )
    for d in discoveries[:limit]:
        t = db.conn.execute("SELECT art FROM tracks WHERE path = ?", (d["path"] or "",)).fetchone()
        d["art"] = t["art"] if t else ""
    genres = {}
    for g, n in db.conn.execute(
        """SELECT t.genre, COUNT(*) FROM play_log l JOIN tracks t ON t.path = l.path
           WHERE l.ts >= ? AND l.ts < ? AND t.genre != '' GROUP BY t.genre""",
        (start, end),
    ):
        for part in g.replace(";", "/").split("/"):
            part = part.strip()
            if part:
                genres[part] = genres.get(part, 0) + n

    days = history.daily_totals(db, start=start, end=end)
    busiest = max(days.items(), key=lambda kv: (kv[1]["seconds"], kv[1]["plays"]), default=None)
    hours, weekdays = [0] * 24, [0] * 7
    for (ts,) in db.conn.execute("SELECT ts FROM play_log WHERE ts >= ? AND ts < ?", (start, end)):
        when = datetime.datetime.fromtimestamp(ts)
        hours[when.hour] += 1
        weekdays[when.weekday()] += 1
    streak = run = 0
    day = first
    while day < end_day:
        run = run + 1 if day.isoformat() in days else 0
        streak = max(streak, run)
        day += datetime.timedelta(days=1)
    added = db.conn.execute(
        "SELECT COUNT(DISTINCT album_key) FROM tracks WHERE added >= ? AND added < ?", (start, end)
    ).fetchone()[0]
    months = []
    if kind == "year":
        for m in range(1, 13):
            a = _ts(datetime.date(first.year, m, 1))
            b = _ts(datetime.date(first.year + (m == 12), 1 if m == 12 else m + 1, 1))
            row = db.conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM play_log WHERE ts >= ? AND ts < ?", (a, b)
            ).fetchone()
            months.append({"month": f"{first.year}-{m:02d}", "plays": row[0], "seconds": float(row[1])})
    return {
        "period": period, "kind": kind, "title": title(period, now),
        "start": first.isoformat(), "end": (end_day - datetime.timedelta(days=1)).isoformat(),
        "summary": summary, "change": change,
        "topArtists": artists, "topAlbums": albums, "topSongs": songs,
        "discoveries": discoveries[:limit], "discoveryCount": len(discoveries),
        "genres": [g for g, _ in sorted(genres.items(), key=lambda kv: (-kv[1], kv[0]))[:3]],
        "busiestDay": {"day": busiest[0], **busiest[1]} if busiest else None,
        "hours": hours, "weekdays": weekdays, "streak": streak, "albumsAdded": added, "months": months,
        "hasNext": _ts(end_day) <= (time.time() if now is None else now),
    }
