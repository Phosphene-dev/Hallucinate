import pytest
from conftest import make_mp3, wait_for


def test_background_scan_and_directory_watcher(qapp, tmp_path):
    pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
    from hallucinate.library import Library

    root = tmp_path / "watched"
    root.mkdir()
    db_path = tmp_path / "library.db"
    art_dir = tmp_path / "art"
    art_dir.mkdir()
    library = Library(db_path, art_dir)
    try:
        library.addFolder(str(root))
        assert wait_for(lambda: not library.scanning, timeout=10)
        assert str(root) in library._watcher.directories()
        make_mp3(root / "new.mp3", "Watcher Song", "Watcher Artist", "Watcher Album")
        assert wait_for(lambda: library.trackCount == 1, timeout=10)

        (root / "new.mp3").unlink()
        assert wait_for(lambda: library.trackCount == 0, timeout=10)
        assert wait_for(lambda: not library.scanning, timeout=5)
    finally:
        assert wait_for(lambda: not library.scanning, timeout=10)
        library.shutdown()


def test_scanning_at_start_and_watching_can_be_switched_off(qapp, tmp_path):
    from hallucinate.library import Library

    root = tmp_path / "music"
    root.mkdir()
    (tmp_path / "art").mkdir()
    library = Library(tmp_path / "library.db", tmp_path / "art")
    try:
        assert library.empty() and library.scanAtStart and library.watching
        library.addFolder(str(root))
        assert wait_for(lambda: not library.scanning, timeout=10)
        assert str(root) in library._watcher.directories()
        library.setWatching(False)
        assert not library.watching and not library._watcher.directories()
        library.setWatching(True)
        assert str(root) in library._watcher.directories()  # back as it was, without a scan
        library.setScanAtStart(False)
        again = Library(tmp_path / "library.db", tmp_path / "art")
        assert not again.scanAtStart  # remembered
        again.shutdown()
    finally:
        library.setScanAtStart(True)
        assert wait_for(lambda: not library.scanning, timeout=10)
        library.shutdown()


def test_songs_show_up_while_a_first_scan_is_still_running(qapp, tmp_path, monkeypatch):
    """Issue 91: the pages said songs appear as they're found, but they came only when the scan ended."""
    from hallucinate import library as library_module
    from hallucinate.core import tags
    from hallucinate.library import Library

    root = tmp_path / "music"
    root.mkdir()
    for i in range(60):
        make_mp3(root / f"{i:02}.mp3", f"Song {i}", "Artist", "Album")
    slow = tags.read_track

    def read_slowly(*a, **k):
        import time
        time.sleep(0.06)  # a slow disk: the whole scan takes several seconds
        return slow(*a, **k)

    monkeypatch.setattr(tags, "read_track", read_slowly)
    monkeypatch.setattr(library_module, "LIVE_FIRST_S", 0.5)
    (tmp_path / "art").mkdir()
    library = Library(tmp_path / "library.db", tmp_path / "art")
    try:
        library.addFolder(str(root))
        assert wait_for(lambda: library.scanning, timeout=5)
        assert wait_for(lambda: library.trackCount > 0 or not library.scanning, timeout=15)
        assert library.scanning and 0 < library.trackCount < 60  # some, while it's still going
        assert wait_for(lambda: not library.scanning and library.trackCount == 60, timeout=20)
    finally:
        assert wait_for(lambda: not library.scanning, timeout=20)
        library.shutdown()
