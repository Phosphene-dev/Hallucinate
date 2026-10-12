"""Removing albums from the library (files kept, rescans leave them out) and moving them to the trash."""
import os
import shutil

import pytest
from conftest import make_mp3, wait_for

from hallucinate.core.db import Database


@pytest.fixture
def lib(qapp, tmp_path):
    from hallucinate.library import Library

    root = tmp_path / "Music"
    for album, artist in (("First", "Band"), ("Second", "Band")):
        folder = root / artist / album
        folder.mkdir(parents=True)
        make_mp3(folder / "01.mp3", f"{album} one", artist, album, artist, "1/2")
        make_mp3(folder / "02.mp3", f"{album} two", artist, album, artist, "2/2")
        (folder / "cover.jpg").write_bytes(b"\xff\xd8\xff not really")
    library = Library(tmp_path / "library.db", tmp_path / "art")
    library.addFolder(str(root))
    assert wait_for(lambda: library.trackCount == 4 and not library.scanning, timeout=10)
    yield library, root
    assert wait_for(lambda: not library.scanning, timeout=10)
    library.shutdown()


def album_key(library, album):
    return next(library.albums.get(i)["album_key"] for i in range(library.albums.count)
                if library.albums.get(i)["album"] == album)


def test_remove_album_keeps_files_and_survives_rescans(lib):
    library, root = lib
    removed = []
    library.albumsRemoved.connect(removed.append)
    key = album_key(library, "First")
    assert len(library.albumPaths([key])) == 2
    library.removeAlbums([key])
    assert wait_for(lambda: library.trackCount == 2 and removed, timeout=5)
    assert removed[0]["kind"] == "hidden" and removed[0]["songs"] == 2 and library.hiddenCount == 2
    assert (root / "Band" / "First" / "01.mp3").exists()  # the files stay where they are
    library.rescan()
    assert wait_for(lambda: not library.scanning, timeout=10)
    assert library.trackCount == 2  # and a rescan doesn't bring them back
    library.restoreHidden()
    assert wait_for(lambda: library.trackCount == 4 and not library.scanning, timeout=10)
    assert library.hiddenCount == 0


def test_trash_album_moves_files_and_its_emptied_folder(lib, monkeypatch, tmp_path):
    from hallucinate import library as library_module

    library, root = lib
    trash = tmp_path / "Trash"
    trash.mkdir()

    class FakeQFile:  # the real one would fill the test machine's trash
        @staticmethod
        def moveToTrash(path):
            shutil.move(path, trash / os.path.basename(path))
            return True

    monkeypatch.setattr(library_module, "QFile", FakeQFile)
    removed = []
    library.albumsRemoved.connect(removed.append)
    library.trashAlbums([album_key(library, "First")])
    assert wait_for(lambda: removed and library.trackCount == 2, timeout=5)
    assert {k: removed[0][k] for k in ("kind", "albums", "songs", "failed")} == {
        "kind": "trashed", "albums": 1, "songs": 2, "failed": 0}
    assert not (root / "Band" / "First").exists()  # only the cover was left, so the folder went too
    assert sorted(p.name for p in trash.iterdir()) == ["01.mp3", "02.mp3", "First"]
    assert (root / "Band").exists() and (root / "Band" / "Second" / "01.mp3").exists()


def test_trash_failure_keeps_the_album(lib, monkeypatch):
    from hallucinate import library as library_module

    library, _root = lib

    class NoTrash:  # e.g. the Flatpak, which can only read the music folder
        @staticmethod
        def moveToTrash(path):
            return False

    monkeypatch.setattr(library_module, "QFile", NoTrash)
    removed = []
    library.albumsRemoved.connect(removed.append)
    library.trashAlbums([album_key(library, "Second")])
    assert wait_for(lambda: removed, timeout=5)
    assert removed[0]["failed"] == 2 and removed[0]["songs"] == 0
    assert library.trackCount == 4


def test_hiding_a_cue_song_hides_its_whole_file(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    for n in (1, 2, 3):
        db.upsert_track({"path": f"/m/a_b%c.flac#{n}", "mtime": 1, "size": 1, "title": f"t{n}", "artist": "x",
                         "album_artist": "x", "aa_tag": 1, "album": "A", "album_key": "k", "track_no": n,
                         "disc_no": 0, "duration": 60.0, "year": 0, "genre": "", "fmt": "FLAC", "bitrate": 0, "sample_rate": 0})
    db.upsert_track({"path": "/m/aXb%c.flac#1", "mtime": 1, "size": 1, "title": "other", "artist": "x",
                     "album_artist": "x", "aa_tag": 1, "album": "B", "album_key": "k2", "track_no": 1,
                     "disc_no": 0, "duration": 60.0, "year": 0, "genre": "", "fmt": "FLAC", "bitrate": 0, "sample_rate": 0})
    db.commit()
    assert db.hide_paths(["/m/a_b%c.flac#2"]) == 3
    assert db.hidden_paths() == {"/m/a_b%c.flac"}
    assert [t["title"] for t in db.album_tracks("k2")] == ["other"]  # LIKE wildcards in the name are literal
    assert db.unhide_all() == 1 and db.hidden_paths() == set()
    db.close()
