"""Backups: everything of yours goes out to one file and merges back in."""
import gzip
import json

import pytest

from hallucinate.core import backup
from hallucinate.core.db import Database
from hallucinate.core.streams_db import StreamsDB


def make(tmp_path, name):
    db = Database(tmp_path / f"{name}.db")
    db.add_folder("/music")
    db.upsert_track({"path": "/music/a.flac", "mtime": 0, "size": 1, "title": "A", "artist": "X", "album_artist": "X",
                     "aa_tag": 1, "album": "L", "album_key": "k", "track_no": 1, "disc_no": 0, "year": 2000,
                     "genre": "", "duration": 100.0, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 0})
    return db


def test_backup_and_restore(tmp_path):
    src = make(tmp_path, "src")
    src.set_liked("/music/a.flac", True)
    src.set_rating("/music/a.flac", 5)
    src.record_play("/music/a.flac")
    pid = src.create_playlist("Mine")
    src.playlist_add(pid, ["/music/a.flac"])
    src.commit()
    src.close()
    streams = StreamsDB(tmp_path / "src-streams.db")
    streams.add_station({"name": "FM", "url": "http://fm/live"})
    show = streams.add_podcast({"title": "Show", "feed_url": "https://show/feed"})
    streams.merge_episodes(show, [{"guid": "1", "title": "One", "url": "https://show/1.mp3", "duration": 600}])
    ep = streams.episodes(show)[0]["id"]
    streams.set_position(ep, 120)
    streams.set_up_next(ep, True)
    sid = streams.stations()[0]["id"]
    streams.log_radio_song(sid, "FM", "Enduser", "Death Vest", ts=1000)
    streams.add_listen_time("station", sid, "FM", 600)
    streams.add_listen_time("podcast", show, "Show", 300)
    streams.close()

    out = tmp_path / "mine.hallucinate-backup"
    summary = backup.export(tmp_path / "src.db", tmp_path / "src-streams.db", out)
    assert summary == {"likes": 1, "ratings": 1, "playlists": 1, "listens": 1, "stations": 1, "podcasts": 1}
    assert json.loads(gzip.open(out).read())["format"] == "hallucinate-backup"

    make(tmp_path, "dst").close()
    restored = backup.restore(backup.read(out), tmp_path / "dst.db", tmp_path / "dst-streams.db")
    assert restored == summary
    backup.restore(backup.read(out), tmp_path / "dst.db", tmp_path / "dst-streams.db")  # twice: no doubles
    dst = Database(tmp_path / "dst.db")
    assert dst.conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0] == 1
    assert dst.conn.execute("SELECT stars FROM ratings").fetchone()[0] == 5
    assert dst.conn.execute("SELECT COUNT(*) FROM play_log").fetchone()[0] == 1
    assert dst.conn.execute("SELECT COUNT(*) FROM playlist_items").fetchone()[0] == 1
    dst.close()
    s2 = StreamsDB(tmp_path / "dst-streams.db")
    assert [s["name"] for s in s2.stations()] == ["FM"]
    e = s2.episodes()[0]
    assert e["position"] == 120 and e["up_next"] > 0
    assert [(r["station"], r["title"]) for r in s2.radio_log()] == [("FM", "Death Vest")]
    assert s2.listening("station")["seconds"] == 600 and s2.listening("podcast")["seconds"] == 300
    s2.close()


def test_not_a_backup(tmp_path):
    (tmp_path / "junk").write_bytes(b"not gzip")
    with pytest.raises(ValueError):
        backup.read(tmp_path / "junk")
    with gzip.open(tmp_path / "other", "wb") as f:
        f.write(b'{"format": "something else"}')
    with pytest.raises(ValueError):
        backup.read(tmp_path / "other")
