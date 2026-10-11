"""Artist pages: profile facts, listening, most played, discography and "appears on"."""
import datetime
import time

from hallucinate.core import artists

DAY = 86_400
NOW = time.mktime(datetime.datetime(2026, 10, 11, 20, 0).timetuple())


def add(db, path, artist, album, year, album_artist=None, genre="Folk"):
    aa = album_artist or artist
    db.upsert_track({
        "path": path, "mtime": 0, "size": 1, "title": path, "artist": artist, "album_artist": aa, "aa_tag": 1,
        "album": album, "album_key": f"{aa}|{album}", "track_no": 1, "disc_no": 0, "year": year, "genre": genre,
        "duration": 200.0, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 44100,
    })


def test_profile(db):
    add(db, "/a/1", "Ada", "First", 1999, genre="Folk; Dream Pop")
    add(db, "/a/2", "Ada", "First", 1999)
    add(db, "/a/3", "Ada", "Second", 2004)
    add(db, "/v/1", "Ada", "Various Things", 2010, album_artist="Various Artists")
    add(db, "/b/1", "Bo", "Other", 2001)
    for i in range(3):
        db.record_play("/a/2", NOW - 10 * DAY + i * 600)
    db.record_play("/a/1", NOW - 40 * DAY)
    for i in range(5):
        db.record_play("/b/1", NOW - DAY + i * 600)
    p = artists.profile(db, "ada", now=NOW)
    assert p["albums"] == 2 and p["tracks"] == 3 and p["firstYear"] == 1999 and p["lastYear"] == 2004
    assert p["genres"][0] == "Folk" and "Dream Pop" in p["genres"]
    assert p["plays"] == 4 and p["listenSeconds"] == 800.0 and p["rank"] == 2  # Bo has more plays
    assert [t["path"] for t in p["topTracks"][:2]] == ["/a/2", "/a/1"]
    assert [a["album"] for a in p["appearsOn"]] == ["Various Things"]
    assert len(p["months"]) == 12 and p["months"][-1]["plays"] == 3 and p["months"][-2]["plays"] == 1
    empty = artists.profile(db, "Nobody", now=NOW)
    assert empty["tracks"] == 0 and empty["plays"] == 0 and empty["rank"] == 0


def test_discography_groups_by_year():
    out = artists.discography([{"album": "B", "year": 2004}, {"album": "a", "year": 1999},
                               {"album": "C", "year": 0}, {"album": "A2", "year": 1999}])
    assert [y["year"] for y in out] == [1999, 2004, 0]
    assert [a["album"] for a in out[0]["albums"]] == ["a", "A2"]


def test_library_artist_profile(qapp, tmp_path, db, scan, music):
    from conftest import wait_for

    from hallucinate.library import Library

    scan(music)
    lib = Library(tmp_path / "lib.db", tmp_path / "art")
    try:
        assert wait_for(lambda: lib.artistCount >= 2)
        data = lib.artistProfile("Aurora Vale")
        assert data["tracks"] == 2 and data["discography"][0]["albums"][0]["album"] == "Northern Lights"
        assert data["topTracks"] and "artUrl" in data["topTracks"][0]
        assert isinstance(lib.artistPalette("Aurora Vale"), list)
    finally:
        lib.shutdown()
