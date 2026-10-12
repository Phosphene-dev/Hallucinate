"""Skip tracking: what counts as a skip, storage, smart playlist rules and radio."""
import pytest
from audio import FFMPEG, encode
from conftest import wait_for

from hallucinate.core import radio, rules


def add(db, path, artist="A", genre="Pop"):
    db.upsert_track({
        "path": path, "mtime": 0, "size": 1, "title": path, "artist": artist, "album_artist": artist, "aa_tag": 1,
        "album": "B", "album_key": f"{artist}|B", "track_no": 1, "disc_no": 0, "year": 2000, "genre": genre,
        "duration": 100.0, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 44100,
    })


def test_skips_are_stored_and_usable_in_smart_playlists(db):
    for p in ("/a", "/b", "/c"):
        add(db, p)
    for _ in range(3):
        db.record_skip("/a")
    db.record_skip("/b")
    assert db.skip_counts() == {"/a": 3, "/b": 1}
    often = {"match": "all", "rules": [{"field": "skips", "op": "ge", "value": 2}], "sort": "title", "limit": 0}
    assert [t["path"] for t in rules.matching_tracks(db, often)] == ["/a"]
    never = {"match": "all", "rules": [{"field": "skips", "op": "eq", "value": 0}], "sort": "title", "limit": 0}
    assert [t["path"] for t in rules.matching_tracks(db, never)] == ["/c"]
    assert rules.describe(often).startswith("Skip count is at least 2")


def test_radio_plays_often_skipped_songs_less(db):
    import random

    add(db, "/seed", artist="S", genre="Jazz")
    add(db, "/skipped", artist="X", genre="Jazz")
    add(db, "/fine", artist="Y", genre="Jazz")
    for _ in range(20):
        db.record_skip("/skipped")
    db.commit()
    firsts = [radio.radio_tracks(db, ["/seed"], limit=1, rng=random.Random(i))[0]["path"] for i in range(40)]
    assert firsts.count("/fine") > firsts.count("/skipped")
    db.conn.execute("INSERT INTO likes(path, liked_at) VALUES('/skipped', 0)")  # liked songs aren't held back
    db.commit()
    firsts = [radio.radio_tracks(db, ["/seed"], limit=1, rng=random.Random(i))[0]["path"] for i in range(40)]
    assert firsts.count("/skipped") >= firsts.count("/fine")


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_player_reports_skips_only_for_songs_moved_on_from(qapp, tmp_path):
    from hallucinate.player import Player

    songs = [{"id": i, "path": str(encode(tmp_path / f"s{i}.flac", "flac", seconds=6, title=f"S{i}")),
              "title": f"S{i}", "artist": "A", "album": "B", "duration": 6.0, "artUrl": ""} for i in range(3)]
    player = Player()
    skipped = []
    player.skipped.connect(lambda t: skipped.append(t["title"]))
    try:
        player.playList(songs, 0)
        player.next()  # straight away: browsing the queue, not a skip
        assert player.currentIndex == 1 and skipped == []
        assert wait_for(lambda: player.position > 1800, 6)
        player.next()
        assert skipped == ["S1"]
        player.pause()
        player.playIndex(0)  # paused: not a skip
        assert skipped == ["S1"]
    finally:
        player.shutdown()
