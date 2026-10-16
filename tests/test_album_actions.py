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
    assert wait_for(lambda: library.trackCount == 4 and library.albums.count == 2 and not library.scanning, timeout=10)
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


def test_cached_album_models_are_freed_not_leaked(lib, qapp):
    """Album/artist song models used to stay alive (children of the library) after every reload; now they're
    replaced, pages are told (detailRevision), and the old ones are deleted. The cache is also capped."""
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtTest import QTest

    from hallucinate import library as library_module

    library, _root = lib
    key = album_key(library, "First")
    destroyed = []
    first = library.albumTracksModel(key)
    first.destroyed.connect(lambda *_: destroyed.append(1))
    revision = library.detailRevision
    library.reload()
    assert wait_for(lambda: library.detailRevision > revision, timeout=5)
    fresh = library.albumTracksModel(key)
    assert fresh is not first and fresh.count == 2
    QTest.qWait(2200)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert destroyed  # the replaced model was freed

    library_module.DETAIL_CACHE, old = 1, library_module.DETAIL_CACHE
    try:
        library.albumTracksModel(album_key(library, "Second"))
        assert len(library._detail) == 1  # capped: the least recently used went
    finally:
        library_module.DETAIL_CACHE = old


def test_remove_and_trash_single_songs(lib, monkeypatch, tmp_path):
    """Songs (from a song's menu, Library health or a selection) go the same two ways as albums."""
    from hallucinate import library as library_module

    library, root = lib
    removed = []
    library.albumsRemoved.connect(removed.append)
    first = library.albumPaths([album_key(library, "First")])
    library.removeSongs([first[0]])
    assert wait_for(lambda: library.trackCount == 3 and removed, timeout=5)
    assert {k: removed[0][k] for k in ("kind", "albums", "songs")} == {"kind": "hidden", "albums": 0, "songs": 1}
    assert os.path.exists(first[0]) and library.hiddenCount == 1

    trash = tmp_path / "Trash"
    trash.mkdir()

    class FakeQFile:
        @staticmethod
        def moveToTrash(path):
            shutil.move(path, trash / os.path.basename(path))
            return True

    monkeypatch.setattr(library_module, "QFile", FakeQFile)
    library.trashSongs([first[1]])
    assert wait_for(lambda: library.trackCount == 2 and len(removed) == 2, timeout=5)
    assert {k: removed[1][k] for k in ("kind", "songs", "failed")} == {"kind": "trashed", "songs": 1, "failed": 0}
    assert not os.path.exists(first[1]) and (trash / os.path.basename(first[1])).exists()
    assert os.path.exists(first[0])  # the hidden one is still on disk, so the folder stays


def test_track_info_for_a_songs_menu(lib):
    library, _root = lib
    path = library.albumPaths([album_key(library, "Second")])[0]
    info = library.trackInfo(path)
    assert info["album"] == "Second" and info["album_artist"] == "Band" and info["album_key"]
    assert info["exists"] is True and info["cue"] is False
    assert library.trackInfo("/nowhere/missing.flac")["exists"] is False
