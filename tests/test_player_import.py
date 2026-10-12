"""Importing play counts, skips, ratings and playlists from other players."""
import datetime as dt
import plistlib
import sqlite3

import pytest

from hallucinate.core import player_import as pi


def add(db, path, artist, title):
    db.upsert_track({
        "path": path, "mtime": 0, "size": 1, "title": title, "artist": artist, "album_artist": artist, "aa_tag": 1,
        "album": "B", "album_key": f"{artist}|B", "track_no": 1, "disc_no": 0, "year": 2000, "genre": "",
        "duration": 100.0, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 44100,
    })


@pytest.fixture
def lib(db):
    add(db, "/music/a.flac", "Aurora Vale", "Echoes of Dawn")
    add(db, "/music/b.flac", "Blue Harbor", "Lantern Bay")
    add(db, "/music/c.flac", "Cinder Fox", "Foxfire")
    db.commit()
    return db


def strawberry(path, clementine=False):
    loc = "filename" if clementine else "url"
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE songs({loc} TEXT, artist TEXT, title TEXT, playcount INT, skipcount INT, "
                "lastplayed INT, rating REAL)")
    con.executemany(f"INSERT INTO songs({loc}, artist, title, playcount, skipcount, lastplayed, rating) "
                    "VALUES(?,?,?,?,?,?,?)", [
                        ("file:///music/a.flac", "Aurora Vale", "Echoes of Dawn", 12, 1, 1_700_000_000, 0.8),
                        ("file:///old/place/b.flac", "Blue Harbor", "Lantern Bay", 3, 4, 1_600_000_000, -1),
                        ("file:///gone.flac", "Nobody", "Nothing", 9, 0, 0, 1.0)])
    link = "library_id" if clementine else "collection_id"
    con.execute("CREATE TABLE playlists(name TEXT)")
    con.execute(f"CREATE TABLE playlist_items(playlist INT, {link} INT, url TEXT, artist TEXT, title TEXT)")
    con.execute("INSERT INTO playlists(name) VALUES('Road trip')")
    con.executemany(f"INSERT INTO playlist_items(playlist, {link}, url) VALUES(1,?,?)",
                    [(2, None), (None, "file:///music/c.flac")])
    con.commit()
    con.close()
    return str(path)


@pytest.mark.parametrize("clementine", [False, True])
def test_strawberry_and_clementine(lib, tmp_path, clementine):
    data = pi.read(strawberry(tmp_path / "library.db", clementine))
    assert data["source"] == ("Clementine" if clementine else "Strawberry")
    result = pi.merge(lib, data)
    assert (result["songs"], result["matched"], result["ratings"], result["playlists"]) == (3, 2, 1, 1)
    plays = {r["path"]: (r["count"], r["last"]) for r in lib._rows("SELECT * FROM plays")}
    assert plays == {"/music/a.flac": (12, 1_700_000_000), "/music/b.flac": (3, 1_600_000_000)}  # b by artist+title
    assert lib.skip_counts() == {"/music/a.flac": 1, "/music/b.flac": 4}
    assert lib.ratings() == {"/music/a.flac": 4}
    (pl,) = lib._rows("SELECT id, name FROM playlists")
    assert pl["name"] == "Road trip"
    assert [r["path"] for r in lib._rows("SELECT path FROM playlist_items ORDER BY pos")] == ["/music/b.flac",
                                                                                            "/music/c.flac"]
    again = pi.merge(lib, data)  # importing again changes nothing
    assert (again["plays"], again["skips"], again["ratings"], again["playlists"]) == (0, 0, 0, 0)
    assert lib._rows("SELECT count FROM plays WHERE path='/music/a.flac'")[0]["count"] == 12


def test_ratings_set_here_are_kept_and_counts_only_go_up(lib, tmp_path):
    lib.set_rating("/music/a.flac", 2)
    for _ in range(20):
        lib.record_play("/music/a.flac")
    result = pi.merge(lib, pi.read(strawberry(tmp_path / "s.db")))
    assert lib.ratings()["/music/a.flac"] == 2 and result["ratings"] == 0
    assert lib._rows("SELECT count FROM plays WHERE path='/music/a.flac'")[0]["count"] == 20


def test_rhythmbox(lib, tmp_path):
    (tmp_path / "rhythmdb.xml").write_text("""<?xml version="1.0"?>
<rhythmdb version="2.0">
  <entry type="song"><title>Foxfire</title><artist>Cinder Fox</artist><location>file:///music/c.flac</location>
    <play-count>7</play-count><rating>5</rating><last-played>1690000000</last-played></entry>
  <entry type="iradio"><title>A station</title><location>http://radio</location></entry>
</rhythmdb>""", encoding="utf-8")
    (tmp_path / "playlists.xml").write_text("""<?xml version="1.0"?>
<rhythmdb-playlists>
  <playlist name="Favourites" type="static"><location>file:///music/c.flac</location>
    <location>file:///music/a.flac</location></playlist>
  <playlist name="Recently added" type="automatic"/>
</rhythmdb-playlists>""", encoding="utf-8")
    result = pi.merge(lib, pi.read(str(tmp_path / "rhythmdb.xml")))
    assert (result["source"], result["matched"], result["ratings"], result["playlists"]) == ("Rhythmbox", 1, 1, 1)
    assert lib.ratings() == {"/music/c.flac": 5}


def test_itunes_style_xml_from_musicbee(lib, tmp_path):
    data = {
        "Music Folder": "file://localhost/C:/Users/me/Music/MusicBee/",
        "Tracks": {
            "1": {"Track ID": 1, "Name": "Echoes of Dawn", "Artist": "Aurora Vale", "Play Count": 5, "Skip Count": 2,
                  "Rating": 60, "Play Date UTC": dt.datetime(2024, 1, 2, 3, 4, 5),
                  "Location": "file://localhost/C:/Users/me/Music/a.flac"},
            "2": {"Track ID": 2, "Name": "Lantern Bay", "Artist": "Blue Harbor", "Rating": 80, "Rating Computed": True,
                  "Location": "file://localhost/C:/Users/me/Music/b.flac"},
        },
        "Playlists": [
            {"Name": "Library", "Master": True, "Playlist Items": [{"Track ID": 1}, {"Track ID": 2}]},
            {"Name": "Smart", "Smart Info": b"x", "Playlist Items": [{"Track ID": 1}]},
            {"Name": "Evening", "Playlist Items": [{"Track ID": 2}, {"Track ID": 1}]},
        ],
    }
    with open(tmp_path / "iTunes Music Library.xml", "wb") as fh:
        plistlib.dump(data, fh)
    imported = pi.read(str(tmp_path / "iTunes Music Library.xml"))
    assert imported["source"] == "MusicBee"
    assert imported["songs"][0]["path"].replace("\\", "/").endswith("Users/me/Music/a.flac")
    result = pi.merge(lib, imported)
    assert (result["matched"], result["ratings"], result["playlists"]) == (2, 1, 1)  # computed ratings ignored
    assert lib.ratings() == {"/music/a.flac": 3}
    assert lib.skip_counts() == {"/music/a.flac": 2}


def test_foobar2000_counts_from_tags(lib, tmp_path):
    from audio import FFMPEG, encode

    if not FFMPEG:
        pytest.skip("ffmpeg not installed")
    import mutagen

    song = str(encode(tmp_path / "x.flac", "flac", seconds=1, title="Foxfire", artist="Cinder Fox"))
    f = mutagen.File(song)
    f["PLAY_COUNTER"] = "9"
    f["LAST_PLAYED"] = "2023-05-06 07:08:09"
    f.save()
    data = pi.read_tag_statistics([song, str(tmp_path / "missing.flac")])
    assert [(s["plays"], s["last_played"] > 0) for s in data["songs"]] == [(9, True)]


def test_unknown_files_are_refused(tmp_path):
    (tmp_path / "x.xml").write_text("<html/>")
    with pytest.raises(ValueError):
        pi.read(str(tmp_path / "x.xml"))
    assert pi._url_path("file:///music/a%20b.flac") == "/music/a b.flac"
    assert pi._url_path("/plain/path.flac") == "/plain/path.flac"


def test_known_locations_finds_strawberry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    db = tmp_path / "data" / "strawberry" / "strawberry" / "strawberry.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"SQLite format 3\x00")
    assert {"name": "Strawberry", "path": str(db)} in pi.known_locations()
