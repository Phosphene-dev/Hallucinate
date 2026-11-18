"""Library health checks."""
from hallucinate.core import health


def add(db, path, album="A", artist="Band", album_artist=None, year=2000, genre="Pop", track=1, art="/c.jpg",
        codec="FLAC", bitrate=900_000, title=None, duration=100.0, rg=-6.0):
    aa = album_artist or artist
    db.upsert_track({
        "path": path, "mtime": 0, "size": 1, "title": title or path, "artist": artist,
        "album_artist": aa, "aa_tag": 1, "album": album, "album_key": f"{aa}|{album}", "track_no": track,
        "disc_no": 0, "year": year, "genre": genre, "duration": duration, "fmt": codec, "codec": codec,
        "bitrate": bitrate, "sample_rate": 44100, "art": art, "rg_track": rg, "rg_album": rg, "rg_peak": 0.9,
    })


def by_id(report):
    return {c["id"]: c for c in report["checks"]}


def test_healthy_library(db):
    add(db, "/m/a/1", track=1)
    add(db, "/m/a/2", track=2)
    report = health.report(db)
    assert report["issues"] == 0 and report["score"] == 100 and report["albums"] == 1


def test_finds_each_kind_of_problem(db, tmp_path):
    add(db, "/m/nocover/1", album="Bare", art="", year=0, genre="", track=0)
    add(db, "/m/nocover/2", album="Bare", art="", year=0, genre="", track=0)
    add(db, "/m/split/1", album="Split", artist="X", album_artist="X")
    add(db, "/m/split/2", album="Split", artist="X", album_artist="X feat. Y")
    add(db, "/m/u/1", artist="Unknown Artist", album="Unknown Album")
    add(db, "/m/low/1", album="Low", codec="MP3", bitrate=96_000)
    add(db, "/m/dup/1", album="D1", title="Same", duration=200)
    add(db, "/m/dup/2", album="D2", title="Same", duration=200)
    db.add_folder(str(tmp_path / "gone"))
    checks = by_id(health.report(db))
    assert [a["album"] for a in checks["covers"]["items"]] == ["Bare"]
    assert checks["year"]["count"] == 1 and checks["genre"]["count"] == 1 and checks["numbers"]["count"] == 1
    assert checks["split"]["count"] == 1 and checks["split"]["items"][0]["parts"] == 2
    assert checks["untagged"]["count"] == 1 and checks["untagged"]["items"][0]["path"] == "/m/u/1"
    assert [t["path"] for t in checks["bitrate"]["items"]] == ["/m/low/1"]
    assert checks["duplicates"]["count"] == 2
    assert checks["folders"]["items"] == [{"path": str(tmp_path / "gone")}]
    report = health.report(db)
    assert report["score"] <= 60  # a missing folder caps the score
    assert report["checks"][-1]["count"] == 0 or all(c["count"] for c in report["checks"])  # problems first


def test_library_runs_the_report(qapp, tmp_path, db, scan, music):
    from conftest import wait_for

    from hallucinate.library import Library

    scan(music)
    lib = Library(tmp_path / "lib.db", tmp_path / "art")
    try:
        lib.checkHealth()
        assert wait_for(lambda: lib.health.get("checks") and not lib.health["loading"])
        assert {c["id"] for c in lib.health["checks"]} >= {"covers", "duplicates", "folders"}
    finally:
        lib.shutdown()


def test_keeping_the_best_copy_of_each_duplicate(db):
    add(db, "/m/dup/a.mp3", album="Single", title="Song", codec="MP3", bitrate=320_000, duration=200)
    add(db, "/m/dup/b.flac", album="Album", title="Song", codec="FLAC", bitrate=900_000, duration=200)
    add(db, "/m/dup/c.mp3", album="Live", title="Song", codec="MP3", bitrate=128_000, duration=200.4)
    add(db, "/m/two/x.mp3", album="X", title="Other", artist="Duo", codec="MP3", bitrate=192_000, duration=90)
    add(db, "/m/two/y.mp3", album="Y", title="Other", artist="Duo", codec="MP3", bitrate=256_000, duration=90)
    add(db, "/m/alone.mp3", album="Z", title="Unique", codec="MP3", duration=50)
    assert sorted(health.extra_copies(db)) == ["/m/dup/a.mp3", "/m/dup/c.mp3", "/m/two/x.mp3"]  # lossless, then bitrate
    assert by_id(health.report(db))["duplicates"]["extra"] == 3


def test_library_removes_extra_copies(qapp, tmp_path):
    from conftest import wait_for

    from hallucinate.core.db import Database
    from hallucinate.library import Library

    path = tmp_path / "library.db"
    seed = Database(path)
    add(seed, "/m/a.mp3", album="One", title="Song", codec="MP3", bitrate=128_000, duration=200)
    add(seed, "/m/b.flac", album="Two", title="Song", codec="FLAC", duration=200)
    seed.commit()
    seed.close()
    lib = Library(path, tmp_path / "art")
    try:
        assert wait_for(lambda: lib.trackCount == 2, timeout=10)
        lib.removeExtraCopies()
        assert wait_for(lambda: lib.trackCount == 1 and lib.hiddenCount == 1, timeout=10)
        assert [t["path"] for t in lib.allTracks()] == ["/m/b.flac"]
    finally:
        lib.shutdown()


def test_counts_are_not_capped_by_the_items_shown(db):
    n = health.LIMIT + 50
    for i in range(n):
        add(db, f"/m/u/{i}", artist="Unknown Artist", album="Unknown Album", codec="MP3", bitrate=64_000,
            title="Same", duration=100)
    checks = by_id(health.report(db))
    for check in ("untagged", "bitrate", "duplicates"):
        assert checks[check]["count"] == n and len(checks[check]["items"]) == health.LIMIT, check


def test_extra_copies_round_lengths_as_the_duplicate_query_does(db):
    add(db, "/m/a.mp3", album="One", title="Song", codec="MP3", bitrate=128_000, duration=100.5)
    add(db, "/m/b.flac", album="Two", title="Song", duration=101.4)  # SQL: both round to 101
    assert health.extra_copies(db) == ["/m/a.mp3"]


def test_damaged_covers_are_found(db, tmp_path):
    """A cover that stops part way shows blank or garbled: Library health lists its album (Repair covers fixes it)."""
    whole, cut = tmp_path / "whole.png", tmp_path / "cut.jpg"
    whole.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 20 + b"IEND\xaeB`\x82")
    cut.write_bytes(b"\xff\xd8\xff\xe0" + b"\0" * 5000)  # no end-of-image mark
    add(db, "/m/w/1", album="Whole", art=str(whole))
    add(db, "/m/c/1", album="Cut", art=str(cut))
    add(db, "/m/g/1", album="Gone", art=str(tmp_path / "unplugged.jpg"))
    checks = by_id(health.report(db))
    assert [a["album"] for a in checks["damagedcovers"]["items"]] == ["Cut"]


def test_merging_duplicates_carries_likes_plays_and_playlists(db):
    """The copy kept gets the others' plays (added up), like, rating (its own wins), listens and playlist places
    (a playlist with both keeps one)."""
    add(db, "/m/a.mp3", album="One", title="Song", codec="MP3", bitrate=128_000, duration=200)
    add(db, "/m/b.flac", album="Two", title="Song", codec="FLAC", duration=200)
    db.set_liked("/m/a.mp3", True)
    db.set_rating("/m/a.mp3", 4)
    for t in (100.0, 200.0, 300.0):
        db.record_play("/m/a.mp3", t)
    db.record_play("/m/b.flac", 400.0)
    both, one = db.create_playlist("Both"), db.create_playlist("One")
    db.playlist_add(both, ["/m/a.mp3", "/m/b.flac"])
    db.playlist_add(one, ["/m/a.mp3"])
    groups = health.duplicate_groups(db)
    assert [[r["path"] for r in g] for g in groups] == [["/m/b.flac", "/m/a.mp3"]]  # lossless first
    db.merge_user_data([("/m/a.mp3", "/m/b.flac")])
    q = lambda sql, *a: [tuple(r) for r in db.conn.execute(sql, a).fetchall()]  # noqa: E731
    assert q("SELECT path FROM likes") == [("/m/b.flac",)]
    assert q("SELECT path, stars FROM ratings") == [("/m/b.flac", 4)]
    assert q("SELECT path, count, last FROM plays") == [("/m/b.flac", 4, 400.0)]
    assert {r[0] for r in q("SELECT path FROM play_log")} == {"/m/b.flac"}
    assert [r[0] for r in q("SELECT path FROM playlist_items WHERE playlist_id=? ORDER BY pos", both)] == ["/m/b.flac"]
    assert [r[0] for r in q("SELECT path FROM playlist_items WHERE playlist_id=?", one)] == ["/m/b.flac"]
    # its own rating wins
    add(db, "/m/c.ogg", album="Three", title="Song", codec="VORBIS", bitrate=96_000, duration=200)
    db.set_rating("/m/c.ogg", 1)
    db.merge_user_data([("/m/c.ogg", "/m/b.flac")])
    assert q("SELECT path, stars FROM ratings") == [("/m/b.flac", 4)]


def test_library_merges_duplicates_into_the_copy_chosen(qapp, tmp_path, monkeypatch):
    """The review's choice is kept (here the MP3, though the FLAC is better); with trash, the other file goes to
    the trash, but never when both paths are the same file, or the copy kept isn't a file here."""
    import os
    import shutil

    from conftest import wait_for

    import hallucinate.library as library_module
    from hallucinate.core.db import Database
    from hallucinate.library import Library

    music, trash = tmp_path / "m", tmp_path / "Trash"
    music.mkdir()
    trash.mkdir()
    for name in ("a.mp3", "b.flac", "c.ogg"):
        (music / name).write_bytes(b"x")
    os.symlink(music / "c.ogg", music / "d.ogg")  # one file seen twice

    class FakeQFile:  # the real one would fill the test machine's trash
        @staticmethod
        def moveToTrash(path):
            shutil.move(path, trash / os.path.basename(path))
            return True

    monkeypatch.setattr(library_module, "QFile", FakeQFile)
    a, b, c, d = (str(music / n) for n in ("a.mp3", "b.flac", "c.ogg", "d.ogg"))
    path = tmp_path / "library.db"
    seed = Database(path)
    seed.add_folder(str(music))
    add(seed, a, album="One", title="Song", codec="MP3", bitrate=128_000, duration=200)
    add(seed, b, album="Two", title="Song", codec="FLAC", duration=200)
    add(seed, c, album="Three", title="Other", duration=100)
    add(seed, d, album="Four", title="Other", duration=100)
    cue = str(music / "live.flac#3")  # a CUE sheet's song: never dropped (its file holds its whole album)
    add(seed, cue, album="Live", title="Song", codec="MP3", bitrate=96_000, duration=200)
    seed.conn.execute("UPDATE tracks SET file=? WHERE path=?", (str(music / "live.flac"), cue))
    seed.set_liked(b, True)
    seed.commit()
    seed.close()
    lib = Library(path, tmp_path / "art")
    found, removed = [], []
    lib.duplicateGroupsLoaded.connect(found.append)
    lib.albumsRemoved.connect(removed.append)
    try:
        assert wait_for(lambda: lib.trackCount == 5, timeout=10)
        lib.loadDuplicateGroups()
        assert wait_for(lambda: found, timeout=10)
        song = next(g for g in found[0] if g["copies"][0]["title"] == "Song")
        assert [x["path"] for x in song["copies"]] == [b, a, cue] and song["copies"][0]["liked"]
        assert song["copies"][2]["cue"]
        lib.mergeDuplicates([{"keep": a, "drop": [b, cue]}, {"keep": c, "drop": [d]}], True)
        assert wait_for(lambda: removed and lib.trackCount == 3, timeout=10)
        assert removed[0]["kind"] == "merged" and removed[0]["merged"] == 2 and removed[0]["trashed"] == 1
        assert sorted(t["path"] for t in lib.allTracks()) == sorted([a, c, cue])
        assert sorted(p.name for p in trash.iterdir()) == ["b.flac"]  # the link's file stayed: it's c itself
        assert os.path.exists(c) and lib.hiddenCount == 1
        db = Database(path)
        assert [tuple(r) for r in db.conn.execute("SELECT path FROM likes")] == [(a,)]
        db.close()
    finally:
        lib.shutdown()
