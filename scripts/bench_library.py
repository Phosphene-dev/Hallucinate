"""Time the heavy library queries against a synthetic library (50,000 songs by default).

    python scripts/bench_library.py [--tracks 50000] [--plays 200000] [--db /tmp/bench.db]

Builds the database once (reused when it exists), then prints how long each page's queries take. Covers are
small generated images so the colour wall has real pixels to read. Run it before and after performance work."""
import argparse
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hallucinate.core import albums as album_views  # noqa: E402
from hallucinate.core import artists as artist_views  # noqa: E402
from hallucinate.core import health, history, insights  # noqa: E402
from hallucinate.core.db import Database  # noqa: E402

GENRES = ["Rock", "Jazz", "Folk", "Ambient", "Hip-Hop", "Classical", "Electronic", "Soul", "Metal", "Pop"]


def build(db_path, n_tracks, n_plays, art_dir):
    from PySide6.QtGui import QColor, QGuiApplication, QImage  # noqa: F401

    rnd = random.Random(1)
    db = Database(db_path)
    art_dir.mkdir(parents=True, exist_ok=True)
    per_album = 10
    n_albums = n_tracks // per_album
    artists = [f"Artist {i:04d}" for i in range(max(1, n_albums // 4))]
    covers = []
    for i in range(min(n_albums, 2000)):  # 2,000 distinct cover images, shared round-robin
        path = art_dir / f"c{i}.png"
        if not path.exists():
            img = QImage(64, 64, QImage.Format.Format_RGB32)
            img.fill(QColor.fromHsvF(rnd.random(), 0.3 + 0.7 * rnd.random(), 0.3 + 0.7 * rnd.random()))
            img.save(str(path))
        covers.append(str(path))
    for a in range(n_albums):
        artist = artists[a % len(artists)]
        album = f"Album {a:05d}"
        year = rnd.choice([0] + list(range(1960, 2026)))
        genre = rnd.choice(GENRES + [""])
        art = covers[a % len(covers)] if rnd.random() > 0.05 else ""
        for t in range(per_album):
            db.upsert_track({
                "path": f"/music/{artist}/{album}/{t:02d}.flac", "mtime": 0, "size": 30_000_000,
                "title": f"Song {a}-{t}", "artist": artist, "album_artist": artist, "aa_tag": 1, "album": album,
                "album_key": f"{artist}|{album}", "track_no": t + 1, "disc_no": 0, "year": year, "genre": genre,
                "duration": 180.0 + rnd.random() * 120, "fmt": "FLAC", "codec": "FLAC", "bitrate": 900_000,
                "sample_rate": 44100, "art": art,
            })
    db.commit()
    paths = [r[0] for r in db.conn.execute("SELECT path FROM tracks")]
    now = time.time()
    for _ in range(n_plays):
        db.conn.execute(
            "INSERT OR IGNORE INTO play_log(ts, path, artist, title, album, duration, source) "
            "SELECT ?, path, artist, title, album, duration, 'local' FROM tracks WHERE path = ?",
            (now - rnd.random() * 3 * 365 * 86400, rnd.choice(paths)))
    db.conn.execute(
        "INSERT OR REPLACE INTO plays(path, count, last) SELECT path, COUNT(*), MAX(ts) FROM play_log GROUP BY path")
    db.commit()
    db.close()


def timed(label, fn, results):
    start = time.perf_counter()
    out = fn()
    ms = (time.perf_counter() - start) * 1000
    results.append((label, ms))
    print(f"{ms:9.1f} ms  {label}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", type=int, default=50_000)
    ap.add_argument("--plays", type=int, default=200_000)
    ap.add_argument("--db", default="/tmp/hallucinate-bench/bench.db")
    args = ap.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication(sys.argv)  # noqa: F841 - QImage needs it
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        print(f"Building {args.tracks} tracks and {args.plays} plays…")
        build(db_path, args.tracks, args.plays, db_path.parent / "art")
    db = Database(db_path)
    from hallucinate.library import Library
    from hallucinate.themes import cover_color

    results = []
    albums = timed("library: albums()", db.albums, results)
    timed("library: artists()", db.artists, results)
    timed("library: tracks()", db.tracks, results)
    timed("timeline rows", lambda: Library._timeline_rows(albums), results)
    db.conn.execute("DELETE FROM album_colors")

    def wall(cached):
        cache = album_views.cached_colors(db)
        measured = {}
        for a in albums:
            art = a.get("art") or ""
            known = cache.get(a["album_key"])
            if known and known[0] == art:
                a["cover"] = known[1]
            elif art:
                c = cover_color(art)
                if c:
                    a["cover"] = c
                    measured[a["album_key"]] = (art, c)
        if measured:
            album_views.store_colors(db, measured)
        albums.sort(key=album_views.colour_order)

    timed("colour wall, first time (measures covers)", lambda: wall(False), results)
    timed("colour wall, cached", lambda: wall(True), results)
    timed("health report", lambda: health.report(db), results)
    timed("home: library facts", lambda: insights.library_facts(db), results)
    timed("home: rediscover", lambda: insights.rediscover_albums(db), results)
    timed("home: on this day", lambda: insights.on_this_day(db), results)
    timed("home: heatmap", lambda: insights.listening_heatmap(db), results)
    timed("history: first page", lambda: history.plays(db, limit=200), results)
    timed("history: summary", lambda: history.summary(db), results)
    timed("history: daily totals", lambda: history.daily_totals(db), results)
    timed("history: search 'song 12'", lambda: history.plays(db, query="song 12", limit=200), results)
    timed("history: 53-week heatmap", lambda: insights.listening_heatmap(db, weeks=53), results)
    artist = albums[len(albums) // 2]["album_artist"]
    timed("artist profile", lambda: artist_views.profile(db, artist), results)
    timed("album notes", lambda: album_views.liner_notes(db, albums[0]["album_key"]), results)
    timed("stats: all time", lambda: db.listening_stats(None), results)
    timed("stats: 30 days", lambda: db.listening_stats(time.time() - 30 * 86400), results)
    timed("search 'artist 01'", lambda: db.search("artist 01"), results)
    slow = [r for r in results if r[1] > 250]
    print("\nOver 250 ms:" if slow else "\nNothing over 250 ms.")
    for label, ms in slow:
        print(f"  {label}: {ms:.0f} ms")


if __name__ == "__main__":
    main()
