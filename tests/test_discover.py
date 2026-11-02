"""Discover's shelves, from a small library with a made-up listening history: what you played a lot but not
lately, deep cuts, albums never played, what you played on this day in earlier years, and the daily mixes; and
"Not interested" leaving things out until they're let back in."""
import datetime
import time

import pytest

from hallucinate.core import discover

DAY = 86400
NOW = time.mktime(datetime.date(2026, 11, 2).timetuple()) + 12 * 3600


def song(i, artist, album, genre, year, added_days_ago=400):
    return {"path": f"/m/{artist}/{album}/{i}.flac", "mtime": 1, "size": 1, "title": f"{album} {i}", "artist": artist,
            "album_artist": artist, "aa_tag": 1, "album": album, "album_key": f"{artist}|{album}", "track_no": i,
            "disc_no": 1, "year": year, "genre": genre, "duration": 200.0, "fmt": "FLAC", "codec": "FLAC",
            "bitrate": 0, "sample_rate": 44100, "added": NOW - added_days_ago * DAY}


@pytest.fixture
def db(tmp_path):
    from hallucinate.core.db import Database

    db = Database(tmp_path / "lib.db")
    lib = []
    for artist, genre, year in (("Aurora", "Rock", 1994), ("Bloom", "Rock", 1997), ("Cinder", "Jazz", 1961),
                                ("Delta", "Jazz", 1965), ("Ember", "Electronic", 2015)):
        for album in ("One", "Two"):
            for i in range(1, 9):
                t = song(i, artist, album, genre, year)
                lib.append(t)
                db.upsert_track(t)
    db.upsert_track(song(1, "Fresh", "Unheard", "Pop", 2024, added_days_ago=200))
    db.conn.execute("UPDATE tracks SET added = ?", (NOW - 400 * DAY,))  # (the scan stamps "added" itself)
    # Aurora's first album: loved two years ago, not since; Bloom and Cinder: played lately
    for t in lib:
        if t["album_key"] == "Aurora|One":
            for k in range(6):
                db.record_play(t["path"], NOW - (730 + k) * DAY)
        elif t["artist"] in ("Bloom", "Cinder") and t["album"] == "One":
            for k in range(4):
                db.record_play(t["path"], NOW - (2 + k) * DAY)
    db.set_liked(lib[-1]["path"], True)  # (an Ember song, liked and never played)
    db.commit()
    yield db
    db.close()


def test_forgotten_favourites(db):
    f = discover.forgotten(db, NOW)
    assert [a["album_key"] for a in f["albums"]] == ["Aurora|One"]
    assert "Played" in f["albums"][0]["reason"]
    paths = {s["path"] for s in f["songs"]}
    assert any("/Aurora/One/" in p for p in paths) and any("/Ember/" in p for p in paths)  # played much, and liked
    assert [a["name"] for a in f["artists"]] == ["Aurora"]
    assert f["deepCuts"] and all("/Bloom/" in s["path"] or "/Cinder/" in s["path"] or "/Aurora/Two/" in s["path"]
                                 for s in f["deepCuts"])  # the most played artists' songs never played
    assert "Fresh|Unheard" in [a["album_key"] for a in f["neverPlayed"]]
    assert "Bloom|One" not in [a["album_key"] for a in f["neverPlayed"]]


def test_not_interested_leaves_it_out_until_let_back(db):
    discover.dismiss(db, "album", "Aurora|One", "One by Aurora", now=NOW)
    discover.dismiss(db, "artist", "aurora", "Aurora", now=NOW)
    f = discover.forgotten(db, NOW)
    assert f["albums"] == [] and f["artists"] == []
    assert [d["label"] for d in discover.dismissed(db)] == ["One by Aurora", "Aurora"]
    discover.undismiss(db, "album", "Aurora|One")
    assert [a["album_key"] for a in discover.forgotten(db, NOW)["albums"]] == ["Aurora|One"]
    discover.undismiss_all(db)
    assert discover.dismissed(db) == []
    discover.dismiss(db, "nonsense", "x")  # (an unknown kind is ignored)
    assert discover.dismissed(db) == []


def test_on_this_day(db):
    days = discover.on_this_day(db, NOW)
    assert [d["years"] for d in days] == [2]
    assert days[0]["albums"][0]["album_key"] == "Aurora|One" and days[0]["year"] == 2024
    assert days[0]["label"] == "2 years ago"


def test_daily_mixes_are_fresh_each_day_and_steady_within_it(db):
    mixes = discover.daily_mixes(db, NOW, size=12)
    assert mixes and {m["title"] for m in mixes} >= {"Rock mix", "Jazz mix"}
    rock = next(m for m in mixes if m["title"] == "Rock mix")
    assert all(s["genre"] == "Rock" for s in rock["songs"])
    assert any(s["artist"] == "Aurora" for s in rock["songs"]) and rock["subtitle"].endswith("and more")
    assert max(sum(1 for s in rock["songs"] if s["artist"] == a) for a in ("Aurora", "Bloom")) <= 6  # shared out
    again = discover.daily_mixes(db, NOW + 3600, size=12)
    assert [s["path"] for s in again[0]["songs"]] == [s["path"] for s in mixes[0]["songs"]]  # same all day
    tomorrow = discover.daily_mixes(db, NOW + DAY, size=12)
    assert [s["path"] for s in tomorrow[0]["songs"]] != [s["path"] for s in mixes[0]["songs"]]


def test_an_empty_library_has_nothing_to_show(tmp_path):
    from hallucinate.core.db import Database

    db = Database(tmp_path / "empty.db")
    assert discover.daily_mixes(db, NOW) == [] and discover.on_this_day(db, NOW) == []
    assert all(v == [] for v in discover.forgotten(db, NOW).values())
    db.close()
