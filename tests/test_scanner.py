import shutil

from conftest import make_mp3, touch_newer


def test_initial_scan(db, scan, music):
    stats = scan(music)
    assert stats["added"] == 4
    assert stats["errors"] == 1  # junk.mp3
    assert db.counts() == {"tracks": 4, "albums": 3, "artists": 3}


def test_tags_and_albums(db, scan, music):
    scan(music)
    albums = {a["album"]: a for a in db.albums()}
    nl = albums["Northern Lights"]
    assert nl["n"] == 2 and nl["album_artist"] == "Aurora Vale"
    assert nl["art"] and nl["art"].endswith(".png")
    tracks = db.album_tracks(nl["album_key"])
    assert [t["title"] for t in tracks] == ["Echoes of Dawn", "Midnight Rain"]
    assert tracks[0]["track_no"] == 1 and tracks[0]["duration"] > 0
    assert tracks[1]["art"] == nl["art"]
    assert albums["Tidal"]["n"] == 1  # WAV with ID3 tags
    loose = albums["Unknown Album"]
    assert db.album_tracks(loose["album_key"])[0]["title"] == "loose"


def test_scan_stores_format_and_probe_bitrate(db, scan, music):
    scan(music)
    rows = {r["fmt"]: r for r in db.tracks()}
    assert rows["MP3"]["codec"] == "MP3"
    assert rows["WAV"]["codec"] == "WAV"
    assert rows["MP3"]["bitrate"] > 0
    assert rows["WAV"]["bitrate"] > 0


def test_incremental_rescan_skips_unchanged(db, scan, music):
    scan(music)
    stats = scan(music)
    assert (stats["added"], stats["updated"], stats["removed"]) == (0, 0, 0)
    assert stats["unchanged"] == 4


def test_modified_and_removed(db, scan, music):
    scan(music)
    p = music / "Aurora Vale" / "Northern Lights" / "02.mp3"
    make_mp3(p, "Sunrise Static", "Aurora Vale", "Northern Lights", "Aurora Vale", "2/2")
    touch_newer(p)
    assert scan(music)["updated"] == 1
    assert db.search("sunrise")["tracks"] and not db.search("midnight")["tracks"]

    p.unlink()
    assert scan(music)["removed"] == 1
    assert not db.search("sunrise")["tracks"]


def test_missing_folder_keeps_library(db, scan, music, tmp_path):
    scan(music)
    moved = tmp_path / "gone"
    shutil.move(str(music), str(moved))
    stats = scan(music)
    assert stats["removed"] == 0 and db.counts()["tracks"] == 4


def test_various_artists(db, scan, tmp_path):
    d = tmp_path / "comp"
    d.mkdir()
    make_mp3(d / "1.mp3", "One", "Alpha", "Mix")
    make_mp3(d / "2.mp3", "Two", "Beta", "Mix")
    scan(d)
    assert db.albums()[0]["album_artist"] == "Various Artists"


def test_remove_folder(db, scan, music):
    scan(music)
    db.add_folder(str(music))
    db.remove_folder(str(music))
    assert db.counts()["tracks"] == 0 and db.folders() == []


def test_unreadable_folder_keeps_its_songs(db, scan, music):
    import os

    import pytest

    if os.geteuid() == 0:
        pytest.skip("root reads every folder")
    scan(music)
    locked = music / "Aurora Vale"
    locked.chmod(0)
    try:
        stats = scan(music)
    finally:
        locked.chmod(0o755)
    assert stats["removed"] == 0 and db.counts()["tracks"] == 4


def test_unreadable_folder_and_file_keep_their_songs(db, scan, music, monkeypatch):
    """os.walk failing on a folder, or a file failing to stat or read: what's already there stays."""
    import os

    from hallucinate.core import scanner, tags

    scan(music)
    real_walk, real_stat, real_read = os.walk, os.stat, tags.read_track
    locked = str(music / "Aurora Vale")

    def walk(top, onerror=None, **kw):
        for root, dirs, files in real_walk(top, onerror=onerror, **kw):
            if root == locked:
                err = PermissionError(13, "Permission denied")
                err.filename = locked
                onerror(err)
                dirs[:] = []
                continue
            yield root, dirs, files

    def stat(path, *a, **kw):
        if str(path).endswith("01.wav"):
            raise PermissionError(13, "Permission denied")
        return real_stat(path, *a, **kw)

    monkeypatch.setattr(scanner.os, "walk", walk)
    monkeypatch.setattr(scanner.os, "stat", stat)
    touch_newer(music / "loose.mp3")
    monkeypatch.setattr(tags, "read_track", lambda path, **kw: None if path.endswith("loose.mp3") else real_read(path, **kw))
    stats = scan(music)
    assert stats["removed"] == 0 and db.counts()["tracks"] == 4


def test_moved_song_keeps_your_data(db, scan, music):
    scan(music)
    old = str(music / "Aurora Vale" / "Northern Lights" / "02.mp3")
    added = db.track_by_path(old)["added"]
    db.set_liked(old, True)
    db.set_rating(old, 4)
    db.record_play(old)
    db.record_skip(old)
    pid = db.create_playlist("Mine")
    db.playlist_add(pid, [old])
    db.set_lyrics(old, "", "la la", "test")
    dest = music / "Moved"
    dest.mkdir()
    new = str(dest / "Midnight Rain.mp3")
    shutil.move(old, new)
    stats = scan(music)
    assert stats["removed"] == 1 and stats["moved"] == 1
    assert db.track_by_path(new)["added"] == added
    assert db.liked_paths() == {new}
    assert db.ratings() == {new: 4}
    assert db.most_played()[0]["path"] == new
    assert db.skip_counts() == {new: 1}
    assert [t["path"] for t in db.playlist_tracks(pid)] == [new]
    assert db.get_lyrics(new)["plain"] == "la la"
    assert [r[0] for r in db.conn.execute("SELECT path FROM play_log")] == [new]


def test_ambiguous_moves_are_left_alone(db, scan, tmp_path):
    d = tmp_path / "m"
    d.mkdir()
    make_mp3(d / "a.mp3", "Same", "Artist", "One")
    make_mp3(d / "b.mp3", "Same", "Artist", "Two")
    scan(d)
    db.set_liked(str(d / "a.mp3"), True)
    shutil.move(str(d / "a.mp3"), str(d / "c.mp3"))
    shutil.move(str(d / "b.mp3"), str(d / "e.mp3"))
    stats = scan(d)
    assert stats["moved"] == 0 and stats["removed"] == 2
    assert db.liked_paths() == {str(d / "a.mp3")}  # kept under the old path, as before


def test_disc_folders_without_an_album_artist_make_one_album(db, scan, tmp_path):
    from hallucinate.core import tags

    root = tmp_path / "Mixes" / "Big Box"
    for disc in ("CD1", "cd 2", "Disc_3"):
        (root / disc).mkdir(parents=True)
    make_mp3(root / "CD1" / "1.mp3", "One", "Alpha", "Big Box")
    make_mp3(root / "cd 2" / "1.mp3", "Two", "Beta", "Big Box")
    make_mp3(root / "Disc_3" / "1.mp3", "Three", "Gamma", "Big Box")
    other = tmp_path / "Mixes" / "Other" / "CD1"
    other.mkdir(parents=True)
    make_mp3(other / "1.mp3", "Four", "Delta", "Big Box")  # another box of the same name stays apart
    scan(tmp_path / "Mixes")
    keys = {t["title"]: t["album_key"] for t in db.tracks()}
    assert keys["One"] == keys["Two"] == keys["Three"] != keys["Four"]
    assert tags.album_folder("/m/Live") == "/m/Live" and tags.album_folder("/m/Live/CD10") == "/m/Live"


def test_disc_folders_are_read_again_after_the_upgrade(tmp_path):
    from hallucinate.core.db import Database

    db = Database(tmp_path / "old.db")
    for path, aa in (("/m/Box/CD1/1.mp3", 0), ("/m/Box/CD1/2.mp3", 1), ("/m/Album/1.mp3", 0)):
        db.upsert_track({"path": path, "mtime": 5, "size": 1, "title": path, "artist": "A", "album_artist": "A",
                         "aa_tag": aa, "album": "B", "album_key": "k", "track_no": 1, "disc_no": 0, "year": 0,
                         "genre": "", "duration": 1.0, "fmt": "MP3", "codec": "MP3", "bitrate": 0, "sample_rate": 0})
    db.conn.execute("PRAGMA user_version = 0")
    db.commit()
    db.close()
    db = Database(tmp_path / "old.db")
    assert {r[0]: r[1] for r in db.conn.execute("SELECT path, mtime FROM tracks")} == {
        "/m/Box/CD1/1.mp3": 0, "/m/Box/CD1/2.mp3": 5, "/m/Album/1.mp3": 5}
    db.close()
