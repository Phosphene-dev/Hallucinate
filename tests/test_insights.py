"""Home's library insights: facts, rediscover, on this day, listening heatmap."""
import datetime
import time

import pytest

from hallucinate.core import insights

DAY = 86_400
NOW = time.mktime(datetime.datetime(2026, 10, 11, 20, 0).timetuple())  # a Sunday evening


def add(db, path, album, codec="FLAC", duration=200.0, size=10_000_000, artist=None):
    artist = artist or f"{album} Band"
    db.upsert_track({
        "path": path, "mtime": 0, "size": size, "title": path.rsplit("/", 1)[1], "artist": artist,
        "album_artist": artist, "aa_tag": 1, "album": album, "album_key": f"{artist}|{album}", "track_no": 1,
        "disc_no": 0, "year": 2000, "genre": "", "duration": duration, "fmt": codec, "codec": codec,
        "bitrate": 900_000, "sample_rate": 44100,
    })


@pytest.fixture
def lib(db):
    add(db, "/m/a1", "Old Love", "FLAC")
    add(db, "/m/a2", "Old Love", "FLAC")
    add(db, "/m/b1", "Fresh", "MP3", size=4_000_000)
    add(db, "/m/c1", "Untouched", "ALAC")
    add(db, "/m/d1", "Odd", "OPUS", duration=100.0)
    for _ in range(5):
        db.record_play("/m/a1", NOW - 200 * DAY)  # loved, then forgotten
    db.record_play("/m/b1", NOW - 2 * DAY)
    db.record_play("/m/b1", NOW - 1 * DAY)
    db.record_play("/m/b1", NOW - 1 * DAY + 60)
    db.record_play("/m/d1", NOW - 365 * DAY)  # a year ago today
    db.record_play("/m/d1", NOW - 731 * DAY)  # and the year before (around the same date)
    db.commit()
    return db


def test_library_facts(lib):
    facts = insights.library_facts(lib, top_formats=2)
    assert facts["tracks"] == 5 and facts["albums"] == 4
    assert facts["seconds"] == 900.0 and facts["bytes"] == 44_000_000
    assert facts["lossless"] == pytest.approx(3 / 5)
    assert [f["name"] for f in facts["formats"]] == ["FLAC", "ALAC", "Other"]
    assert sum(f["share"] for f in facts["formats"]) == pytest.approx(1.0)


def test_rediscover_prefers_loved_but_forgotten_albums(lib):
    albums = insights.rediscover_albums(lib, now=NOW, limit=3)
    assert albums[0]["album"] == "Old Love" and albums[0]["reason"] == "Last played Mar 2026"
    names = [a["album"] for a in albums]
    assert "Fresh" not in names  # played this week
    assert "Untouched" in names and next(a for a in albums if a["album"] == "Untouched")["reason"] == "Never played"


def test_on_this_day(lib):
    albums = insights.on_this_day(lib, now=NOW)
    assert [a["album"] for a in albums] == ["Odd"]
    assert albums[0]["reason"] == "Played on this day in 2025, 2024"
    assert insights.on_this_day(lib, now=NOW + 30 * DAY) == []


def test_listening_heatmap(lib):
    heat = insights.listening_heatmap(lib, now=NOW, weeks=4)
    assert len(heat["days"]) == 28
    assert heat["first"] == "2026-09-14"  # Monday, four weeks back
    assert heat["today"] == 27  # Sunday is the last cell
    assert heat["days"][26] == 2 and heat["days"][25] == 1 and heat["total"] == 3
    assert heat["streak"] == 2 and heat["activeDays"] == 2 and heat["max"] == 2


def test_empty_library(db):
    assert insights.library_facts(db)["lossless"] == 0.0
    assert insights.rediscover_albums(db, now=NOW) == []
    assert insights.on_this_day(db, now=NOW) == []
    assert insights.listening_heatmap(db, now=NOW)["total"] == 0


def test_user_library_exposes_home_data(qapp, lib):
    from conftest import wait_for

    from hallucinate.userlib import UserLibrary

    ul = UserLibrary(lib.conn.execute("PRAGMA database_list").fetchone()["file"])
    try:
        assert wait_for(lambda: ul.home.get("facts", {}).get("tracks") == 5)
        assert set(ul.home) == {"facts", "heatmap", "topArtists", "playlists"}
        assert len(ul.home["heatmap"]["days"]) == 26 * 7
        assert wait_for(lambda: ul.rediscover.count >= 3)
        assert all(ul.rediscover.get(i)["reason"] for i in range(ul.rediscover.count))
    finally:
        ul.shutdown()


def test_random_album_avoids_the_current_pick(qapp, tmp_path, db, scan, music):
    from conftest import wait_for

    from hallucinate.library import Library

    scan(music)
    lib = Library(tmp_path / "lib.db", tmp_path / "art")
    try:
        assert wait_for(lambda: lib.albumCount >= 2)
        first = lib.randomAlbum("")
        assert first["album_key"]
        assert all(lib.randomAlbum(first["album_key"])["album_key"] != first["album_key"] for _ in range(10))
    finally:
        lib.shutdown()


def test_most_played_albums_lately(lib):
    albums = insights.top_albums(lib, now=NOW, days=30)
    assert [(a["album"], a["plays"]) for a in albums] == [("Fresh", 3)]  # Old Love's plays are from long ago
    lib.conn.execute("DELETE FROM tracks WHERE album = 'Fresh'")
    assert insights.top_albums(lib, now=NOW, days=30) == []  # gone from the library: no card leading nowhere


def test_playlist_cards_liked_first_then_most_recently_added(lib):
    lib.conn.execute("UPDATE tracks SET art = '/art/' || album")
    first = lib.create_playlist("First")
    lib.playlist_add(first, ["/m/a1", "/m/a2", "/m/b1", "/m/c1", "/m/d1"])
    second = lib.create_playlist("Second")
    lib.playlist_add(second, ["/m/b1"])
    assert [c["id"] for c in insights.playlist_cards(lib)] in ([second, first], [first, second])
    lib.set_liked("/m/c1", True)
    cards = insights.playlist_cards(lib)
    assert cards[0]["id"] == -1 and cards[0]["n"] == 1 and cards[0]["arts"] == ["/art/Untouched"]
    by_id = {c["id"]: c for c in cards}
    assert by_id[first]["n"] == 5 and len(by_id[first]["arts"]) == 4  # four different covers at most
    assert insights.playlist_cards(lib, limit=2)[0]["id"] == -1 and len(insights.playlist_cards(lib, limit=2)) == 2
