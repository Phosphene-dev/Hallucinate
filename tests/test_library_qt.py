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
