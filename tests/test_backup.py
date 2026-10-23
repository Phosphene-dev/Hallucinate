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


def test_a_damaged_or_crafted_backup_restores_what_is_sound(tmp_path):
    make(tmp_path, "dst").close()
    crafted = {"format": "hallucinate-backup", "version": 1,
               "likes": [{"path": "/music/ok.flac", "liked_at": 1.0}, {"liked_at": 2}, "junk", {"path": ["x"]}],
               "ratings": [{"path": "/music/ok.flac", "stars": 99}],
               "plays": [{"path": "/m.flac", "count": "lots"}],
               "playlists": [{"name": "P", "paths": ["/a.flac", 5, None]}, {"paths": []}],
               "stations": [{"url": "file:///etc/passwd", "name": "x"}, {"url": "http://fm/live", "name": "FM",
                                                                         "homepage": "file:///C:/x.exe"}],
               "podcasts": [{"title": "S", "feed_url": "https://s/feed",
                             "episodes": [{"guid": "1", "url": "file:///etc/shadow"}, {"title": "no guid"}]}],
               "play_log": {"not": "a list"}}
    out = tmp_path / "crafted.hallucinate-backup"
    out.write_bytes(gzip.compress(json.dumps(crafted).encode()))
    backup.restore(backup.read(out), tmp_path / "dst.db", tmp_path / "dst-streams.db")
    dst = Database(tmp_path / "dst.db")
    assert [r[0] for r in dst.conn.execute("SELECT path FROM likes")] == ["/music/ok.flac"]
    assert dst.conn.execute("SELECT stars FROM ratings").fetchone()[0] == 5
    assert [r[0] for r in dst.conn.execute("SELECT path FROM playlist_items")] == ["/a.flac"]
    dst.close()
    s2 = StreamsDB(tmp_path / "dst-streams.db")
    assert [(s["url"], s["homepage"]) for s in s2.stations()] == [("http://fm/live", "")]
    assert [e["url"] for e in s2.episodes()] == [""]
    s2.close()


def test_a_backup_bomb_is_refused(tmp_path):
    bomb = tmp_path / "bomb.hallucinate-backup"
    bomb.write_bytes(gzip.compress(b'{"format": "hallucinate-backup", "x": "' + b"a" * (backup.MAX_BYTES + 10) + b'"}'))
    with pytest.raises(ValueError):
        backup.read(bomb)


def test_imported_listens_without_a_song_survive_a_restore(tmp_path):
    src = make(tmp_path, "src")
    src.import_plays([{"ts": 500, "artist": "Björk", "title": "Joga", "album": "Homogenic"}], "lastfm")
    src.close()
    out = tmp_path / "mine.hallucinate-backup"
    backup.export(tmp_path / "src.db", None, out)
    make(tmp_path, "dst").close()
    backup.restore(backup.read(out), tmp_path / "dst.db", None)
    # an older backup without the folded names gets them back
    old = {"format": "hallucinate-backup", "version": 1,
           "play_log": [{"ts": 600, "artist": "Sigur Rós", "title": "Hoppípolla", "album": "Takk"}]}
    backup.restore(old, tmp_path / "dst.db", None)
    dst = Database(tmp_path / "dst.db")
    rows = [tuple(r) for r in dst.conn.execute("SELECT ts, path, s_artist, s_title, s_album FROM play_log ORDER BY ts")]
    assert rows == [(500, None, "bjork", "joga", "homogenic"), (600, None, "sigur ros", "hoppipolla", "takk")]
    dst.close()


def test_playlist_folders_are_kept_renamed_and_backed_up(tmp_path):
    src = make(tmp_path, "src")
    run = src.create_playlist("Run")
    walk = src.create_playlist("Walk")
    calm = src.create_smart_playlist("Calm", '{"match": "all", "rules": []}')
    src.set_playlist_folder(run, False, "  Workout ")
    src.set_playlist_folder(calm, True, "Moods")
    assert {p["name"]: p["folder"] for p in src.playlists()} == {"Run": "Workout", "Walk": ""}
    assert src.playlist_folders() == ["Moods", "Workout"]
    assert src.playlist_folders() == sorted(src.playlist_folders())
    copy = src.duplicate_playlist(run, "Run (copy)")
    assert {p["id"]: p["folder"] for p in src.playlists()}[copy] == "Workout"  # a copy sits beside it
    src.rename_playlist_folder("Workout", "Moods")  # renamed to one that exists: the two are one
    assert src.playlist_folders() == ["Moods"]
    src.set_playlist_folder(walk, False, "Out")
    src.close()
    out = tmp_path / "b.hallucinate-backup"
    backup.export(tmp_path / "src.db", None, out)
    make(tmp_path, "dst").close()
    backup.restore(backup.read(out), tmp_path / "dst.db", tmp_path / "dst-streams.db")
    dst = Database(tmp_path / "dst.db")
    assert {p["name"]: p["folder"] for p in dst.playlists()} == {"Run": "Moods", "Run (copy)": "Moods", "Walk": "Out"}
    assert [s["folder"] for s in dst.smart_playlists()] == ["Moods"]
    dst.rename_playlist_folder("Moods", "")  # Ungroup: the playlists stay, in no folder
    assert dst.playlist_folders() == ["Out"] and len(dst.playlists()) == 3
    dst.close()
