"""Composers, works and movements (classical music), and tempo and key: read from tags and CUE sheets,
written by the tag editor, browsed by composer, found by search, sorted and used in smart playlists."""
import sqlite3

import pytest
from audio import FFMPEG, encode

from hallucinate.core import albums, composers, cue, genre_views, tagedit
from hallucinate.core import rules as R
from hallucinate.core.db import Database
from hallucinate.core.tags import music_key, read_track

needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
FIELDS = {"composer": "Béla Bartók", "work": "Concerto for Orchestra", "movement": "Elegia", "bpm": "92",
          "music_key": "F#m"}


@needs_ffmpeg
@pytest.mark.parametrize("ext", ["mp3", "flac", "ogg", "opus", "m4a", "wv"])
def test_composer_work_movement_tempo_and_key_are_written_and_read_back(tmp_path, ext):
    path = encode(tmp_path / f"a.{ext}", ext, seconds=0.5, title="x")
    tagedit.write_tags(str(path), FIELDS)
    t = read_track(str(path))
    assert (t["composer"], t["work"], t["movement"], t["bpm"], t["music_key"]) == \
        ("Béla Bartók", "Concerto for Orchestra", "Elegia", 92, "F#m")
    tagedit.write_tags(str(path), {k: "" for k in FIELDS})
    t = read_track(str(path))
    assert (t["composer"], t["work"], t["movement"], t["bpm"], t["music_key"]) == ("", "", "", 0, "")


@needs_ffmpeg
def test_several_composers_and_the_movement_number_are_read(tmp_path):
    import mutagen

    path = encode(tmp_path / "a.flac", "flac", seconds=0.5, title="x")
    f = mutagen.File(path)
    f.tags["COMPOSER"] = ["John Lennon", "Paul McCartney"]
    f.tags["MOVEMENT"] = ["3"]
    f.tags["BPM"] = ["127.6"]
    f.tags["INITIALKEY"] = ["A minor"]
    f.save()
    t = read_track(str(path))
    assert t["composer"] == "John Lennon; Paul McCartney" and t["movement_no"] == 3
    assert t["bpm"] == 128 and t["music_key"] == "Am"


def test_keys_are_spelled_one_way():
    assert [music_key(k) for k in ("A minor", "a", "Gb major", "E♭", "f# min", "8A", "", "AM")] == \
        ["Am", "Am", "Gb", "Eb", "F#m", "8A", "", "A"]


def test_a_cue_sheets_songwriters_are_the_songs_composers():
    sheet = cue.parse('SONGWRITER "Bach"\nTITLE "Suites"\nFILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "Prelude"\n'
                      '    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "Allemande"\n    SONGWRITER "J. S. Bach"\n'
                      '    INDEX 01 01:00:00\n')
    whole = {"path": "/m/a.flac", "duration": 120.0, "album": "", "artist": "Cellist", "bpm": 90, "music_key": "G"}
    rows = cue.tracks(whole, sheet, sheet["files"][0])
    assert [r["composer"] for r in rows] == ["Bach", "J. S. Bach"]
    assert rows[0]["bpm"] == 0 and rows[0]["music_key"] == ""  # the whole file's, not this song's


def _add(db, path, title, composer="", work="", movement_no=0, album="LP", bpm=0, key=""):
    db.upsert_track({
        "path": path, "mtime": 0, "size": 1, "title": title, "artist": "Orchestra", "album_artist": "Orchestra",
        "aa_tag": 1, "album": album, "album_key": "o|" + album.lower(), "track_no": movement_no or 9,
        "disc_no": 0, "year": 2000, "genre": "Classical", "duration": 300, "fmt": "FLAC", "codec": "FLAC",
        "bitrate": 0, "sample_rate": 44100, "composer": composer, "work": work, "movement": title,
        "movement_no": movement_no, "bpm": bpm, "music_key": key,
    })


@pytest.fixture
def classical(db):
    _add(db, "/m/3", "Finale", "Béla Bartók", "Concerto for Orchestra", 3, bpm=140, key="F")
    _add(db, "/m/1", "Introduzione", "Béla Bartók", "Concerto for Orchestra", 1, bpm=60, key="F")
    _add(db, "/m/2", "Giuoco delle coppie", "Bela Bartok", "Concerto for Orchestra", 2)
    _add(db, "/m/4", "Romanian Dance", "Béla Bartók; Zoltán Kodály", album="Dances", bpm=100, key="Am")
    _add(db, "/m/5", "Something else", "", album="Dances")
    db.commit()
    return db


def test_composers_are_listed_and_have_a_page_with_works_in_movement_order(classical):
    names = {c["name"]: c for c in composers.overview(classical)}
    assert names["Béla Bartók"]["tracks"] == 4 and names["Béla Bartók"]["works"] == 1
    assert names["Zoltán Kodály"]["tracks"] == 1  # a song crediting two counts for both
    page = composers.page(classical, "bela bartok")
    assert page["name"] in ("Béla Bartók", "Bela Bartok") and page["tracks"] == 4
    (work,) = page["works"]
    assert work["work"] == "Concerto for Orchestra"
    assert [s["path"] for s in work["songs"]] == ["/m/1", "/m/2", "/m/3"]
    assert [s["path"] for s in page["others"]] == ["/m/4"]
    assert [t["path"] for t in composers.tracks(classical, "zoltan kodaly")] == ["/m/4"]
    assert composers.tracks(classical, "Bart") == []  # a whole name, not part of one


def test_songs_are_found_by_composer_and_sorted_by_composer_or_tempo(classical):
    assert {t["path"] for t in classical.search("kodaly", groups=False)["tracks"]} == {"/m/4"}
    songs = classical.song_list()
    by_bpm = [t["path"] for t in sorted(songs, key=genre_views.song_sort_key("bpm"))]
    assert by_bpm[:3] == ["/m/1", "/m/4", "/m/3"]  # slowest first, the unknown ones last
    by_composer = [t["path"] for t in sorted(songs, key=genre_views.song_sort_key("composer"))]
    assert by_composer[-1] == "/m/5"


def test_smart_playlists_by_composer_tempo_and_key(classical):
    def found(*rules, sort="title"):
        return [t["path"] for t in R.matching_tracks(classical, {"match": "all", "rules": list(rules), "sort": sort})]

    assert set(found({"field": "composer", "op": "is", "value": "Zoltan Kodaly"})) == {"/m/4"}
    assert set(found({"field": "composer", "op": "is_not", "value": "Béla Bartók"})) == {"/m/5"}
    assert set(found({"field": "bpm", "op": "lt", "value": 120})) == {"/m/1", "/m/4"}  # not the unknown ones
    assert set(found({"field": "music_key", "op": "is_empty", "value": ""})) == {"/m/2", "/m/5"}
    assert set(found({"field": "music_key", "op": "is", "value": "am"})) == {"/m/4"}
    assert found({"field": "work", "op": "contains", "value": "concerto"}, sort="composer") == ["/m/1", "/m/2", "/m/3"]
    assert found({"field": "bpm", "op": "gt", "value": 0}, sort="bpm_desc") == ["/m/3", "/m/4", "/m/1"]


def test_an_albums_page_lists_who_wrote_it(classical):
    notes = albums.liner_notes(classical, "o|dances")
    assert notes["composers"] == ["Béla Bartók", "Zoltán Kodály"]


def test_an_older_library_gains_the_columns_and_reads_its_files_again(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    db = Database(path)
    db.close()
    # as 0.9.9.9 left it: none of the new columns, and the search index without genre or composer
    conn.execute("DROP INDEX idx_tracks_scomposer")
    for c in ("composer", "s_composer", "work", "movement", "movement_no", "bpm", "music_key"):
        conn.execute(f"ALTER TABLE tracks DROP COLUMN {c}")
    conn.execute("DROP TABLE tracks_fts")
    conn.execute("CREATE VIRTUAL TABLE tracks_fts USING fts5(title, artist, album)")
    conn.execute("INSERT INTO tracks(path, mtime, size, title, artist, album_artist, album, album_key, added) "
                 "VALUES('/m/a.flac', 5, 1, 'A', 'B', 'B', 'C', 'b|c', 0)")
    conn.execute("INSERT INTO tracks(path, mtime, size, title, artist, album_artist, album, album_key, added) "
                 "VALUES('subsonic://s1/x', 5, 1, 'S', 'B', 'B', 'C', 'b|c', 0)")
    conn.commit()
    conn.close()
    db = Database(path)
    try:
        mtimes = dict(db.conn.execute("SELECT path, mtime FROM tracks"))
        assert mtimes == {"/m/a.flac": 0, "subsonic://s1/x": 5}  # files read again; a server's songs left alone
        assert {r[1] for r in db.conn.execute("PRAGMA table_info(tracks_fts)")} >= {"genre", "composer"}
        assert [t["path"] for t in db.search("A", groups=False)["tracks"]] == ["/m/a.flac"]
    finally:
        db.close()
