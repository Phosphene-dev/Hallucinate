"""Organize files from their tags: the plan, moving (never over a file), the library following, undo."""
import os

import pytest
from conftest import make_mp3

from hallucinate.core import organize
from hallucinate.core.db import Database
from hallucinate.core.scanner import Scanner


def test_a_pattern_makes_safe_paths():
    t = {"album_artist": "AC/DC", "artist": "AC/DC", "album": "Back: in Black?", "title": "Hells Bells",
         "track_no": 1, "disc_no": 0, "year": 1980}
    assert organize.render(t, organize.PRESETS["artist_album"]) == "AC_DC/Back_ in Black_/01 Hells Bells"
    assert organize.render(t, organize.PRESETS["artist_year_album"]) == "AC_DC/1980 - Back_ in Black_/01 Hells Bells"
    # no year: no stray dash; a second disc: "2-"; no number: just the title
    t2 = dict(t, year=0, disc_no=2, track_no=3)
    assert organize.render(t2, organize.PRESETS["artist_year_album"], discs=2) == "AC_DC/Back_ in Black_/2-03 Hells Bells"
    assert organize.render(dict(t, track_no=0), "{albumartist}/{title}") == "AC_DC/Hells Bells"
    assert organize.render(dict(t, album_artist="Unknown Artist", artist="Unknown Artist"), "{albumartist}/{title}") == "Unknown/Hells Bells"
    assert organize.clean("con") == "_con" and organize.clean(" ...x. ") == "x" and len(organize.clean("a" * 300)) == 120
    with pytest.raises(organize.PatternError):
        organize.check_pattern("{albumartist}/{album}")  # no {title}
    with pytest.raises(organize.PatternError):
        organize.check_pattern("{nope}/{title}")


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "Music"
    messy = root / "downloads" / "stuff"
    messy.mkdir(parents=True)
    make_mp3(messy / "a.mp3", "Echoes", "Aurora Vale", "Northern Lights", "Aurora Vale", "1/2")
    make_mp3(messy / "b.mp3", "Midnight Rain", "Aurora Vale", "Northern Lights", "Aurora Vale", "2/2")
    (messy / "a.lrc").write_text("[00:01.00]hi")
    (messy / "cover.jpg").write_bytes(b"\xff\xd8\xff fake")
    db = Database(tmp_path / "lib.db")
    db.add_folder(str(root))
    (tmp_path / "art").mkdir()
    scanner = Scanner(db, tmp_path / "art")
    scanner.scan([str(root)])
    yield root, db, scanner, tmp_path
    db.close()


def test_songs_move_into_the_pattern_and_their_likes_follow(lib):
    root, db, scanner, tmp = lib
    old = str(root / "downloads" / "stuff" / "a.mp3")
    db.set_liked(old, True)
    db.commit()
    plan = organize.plan(db.tracks(), db.folders(), organize.PRESETS["artist_album"])
    dsts = sorted(os.path.relpath(m["dst"], root) for m in plan["moves"])
    assert dsts == [os.path.join("Aurora Vale", "Northern Lights", "01 Echoes.mp3"),
                    os.path.join("Aurora Vale", "Northern Lights", "02 Midnight Rain.mp3")]
    journal = tmp / "organize.json"
    result = organize.apply(db, scanner, plan["moves"], db.folders(), journal)
    assert result == {"moved": 2, "errors": []}
    new = str(root / "Aurora Vale" / "Northern Lights" / "01 Echoes.mp3")
    assert os.path.isfile(new) and not os.path.exists(old)
    assert sorted(t["path"] for t in db.tracks()) == sorted(m["dst"] for m in plan["moves"])
    assert db.conn.execute("SELECT COUNT(*) FROM likes WHERE path=?", (new,)).fetchone()[0] == 1
    # the lyrics and the folder's cover came along; the emptied folders are gone
    assert os.path.isfile(root / "Aurora Vale" / "Northern Lights" / "01 Echoes.lrc")
    assert os.path.isfile(root / "Aurora Vale" / "Northern Lights" / "cover.jpg")
    assert not os.path.exists(root / "downloads")
    # the folder watcher leaves the folders it touched be (a rescan mid-way would race the likes)
    from hallucinate.core import tagedit
    assert all(tagedit.written_recently(str(d)) for d in (root, root / "Aurora Vale", root / "Aurora Vale" / "Northern Lights"))
    # done again: nothing to do
    assert organize.plan(db.tracks(), db.folders(), organize.PRESETS["artist_album"])["moves"] == []
    # undo: back where they were, the like with it
    back = organize.undo(db, scanner, journal, db.folders())
    assert back["moved"] == 2 and os.path.isfile(old) and not os.path.exists(root / "Aurora Vale")
    assert db.conn.execute("SELECT COUNT(*) FROM likes WHERE path=?", (old,)).fetchone()[0] == 1
    assert os.path.isfile(root / "downloads" / "stuff" / "a.lrc") and os.path.isfile(root / "downloads" / "stuff" / "cover.jpg")
    assert not journal.exists()


def test_nothing_is_ever_moved_over_a_file(lib):
    root, db, scanner, tmp = lib
    taken = root / "Aurora Vale" / "Northern Lights"
    taken.mkdir(parents=True)
    (taken / "01 Echoes.mp3").write_bytes(b"someone else's")
    plan = organize.plan(db.tracks(), db.folders(), organize.PRESETS["artist_album"])
    names = sorted(os.path.basename(m["dst"]) for m in plan["moves"])
    assert names == ["01 Echoes (2).mp3", "02 Midnight Rain.mp3"]
    # and if a file appears there between the plan and the move, that one isn't moved
    (taken / "02 Midnight Rain.mp3").write_bytes(b"late")
    result = organize.apply(db, scanner, plan["moves"], db.folders(), tmp / "j.json")
    assert result["moved"] == 1 and len(result["errors"]) == 1
    assert (taken / "01 Echoes.mp3").read_bytes() == b"someone else's"
    assert (taken / "02 Midnight Rain.mp3").read_bytes() == b"late"


def test_cue_songs_and_server_songs_stay(lib):
    root, db, scanner, tmp = lib
    rows = [dict(t) for t in db.tracks()]
    rows.append(dict(rows[0], path=str(root / "x.flac") + "#2"))
    rows.append(dict(rows[0], path="subsonic://srv/12"))
    plan = organize.plan(rows, db.folders(), organize.PRESETS["artist_album"])
    assert {s["why"] for s in plan["skipped"]} == {"cue", "server"} and len(plan["moves"]) == 2


def test_a_file_that_cant_be_read_again_keeps_its_place_in_the_library(lib):
    root, db, scanner, tmp = lib
    junk = root / "downloads" / "stuff" / "a.mp3"
    plan = organize.plan(db.tracks(), db.folders(), organize.PRESETS["artist_album"])
    junk.write_bytes(b"not audio any more")
    organize.apply(db, scanner, plan["moves"], db.folders(), tmp / "j.json")
    paths = {t["path"] for t in db.tracks()}
    assert str(root / "Aurora Vale" / "Northern Lights" / "01 Echoes.mp3") in paths and len(paths) == 2
