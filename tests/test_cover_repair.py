"""Library health → Repair covers: scaled covers made again, damaged covers taken from songs read afresh."""
from conftest import wait_for

from hallucinate.core import paths
from hallucinate.core.tags import folder_art_whole


def test_repair_covers_starts_them_over(qapp, tmp_path, music):
    from hallucinate.library import Library

    lib = Library(tmp_path / "lib.db", tmp_path / "art")
    try:
        lib.addFolder(str(music))
        assert wait_for(lambda: lib.trackCount >= 3 and not lib.scanning, timeout=10)
        (art,) = {r["art"] for r in lib._db.tracks() if r["art"]}
        assert folder_art_whole(art)
        with open(art, "r+b") as fh:  # as a cover written by a tool that stopped half way would be
            fh.truncate(20)
        assert not folder_art_whole(art)
        thumbs = paths.data_dir() / "thumbs"
        thumbs.mkdir(parents=True, exist_ok=True)
        (thumbs / "old.jpg").write_bytes(b"stale")
        before = lib.artRevision

        lib.repairCovers()
        assert not (thumbs / "old.jpg").exists() and lib.artRevision > before
        assert wait_for(lambda: not lib.scanning, timeout=15)
        (fixed,) = {r["art"] for r in lib._db.tracks() if r["art"]}
        assert folder_art_whole(fixed)  # read again from the song
    finally:
        lib.shutdown()
