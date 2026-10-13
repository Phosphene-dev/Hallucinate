"""The library database: daily backups, and a damaged one set aside and restored rather than failing to start."""
import json
import os
import sqlite3
import time

from hallucinate import dbguard
from hallucinate.core.db import Database


def make_db(path, liked):
    db = Database(path)
    db.set_liked(liked, True)
    db.commit()
    db.close()


def damage(path):
    with open(path, "r+b") as f:
        f.seek(4096)  # past the header, into the tables
        f.write(os.urandom(8192))


def test_healthy_database_is_left_alone(tmp_path):
    make_db(tmp_path / "library.db", "/m/a.flac")
    assert dbguard.check(tmp_path / "library.db", tmp_path / "backups") == ""
    assert dbguard.check(tmp_path / "missing.db", tmp_path / "backups") == ""  # first run


def test_daily_backups_rotate(tmp_path):
    make_db(tmp_path / "library.db", "/m/a.flac")
    backups = tmp_path / "backups"
    for _ in range(7):
        dbguard.backup_now(tmp_path / "library.db", backups, keep=5)
        time.sleep(1.01)  # backups are named by the second
    assert len(dbguard.backups(backups)) == 5
    assert dbguard.backup_if_due(tmp_path / "library.db", backups) is None  # newest is fresh: nothing to do


def test_damaged_database_is_restored_from_backup(tmp_path):
    db_path, backups = tmp_path / "library.db", tmp_path / "backups"
    make_db(db_path, "/m/loved.flac")
    for i in range(200):  # enough pages that damage lands in the data
        Database(db_path).set_liked(f"/m/{i}.flac", True)
    db = Database(db_path)
    db.commit()
    db.close()
    dbguard.backup_now(db_path, backups)
    damage(db_path)
    message = dbguard.check(db_path, backups)
    assert "backup" in message and "restored" in message
    assert list(tmp_path.glob("library.db.damaged-*"))  # the damaged copy is kept, never deleted
    db = Database(db_path)
    assert db.conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0] >= 1
    db.close()


def test_damaged_database_without_backup_starts_fresh(tmp_path):
    db_path = tmp_path / "library.db"
    db_path.write_bytes(b"SQLite format 3\x00" + os.urandom(20000))
    message = dbguard.check(db_path, tmp_path / "backups")
    assert "no backup" in message and not db_path.exists()
    Database(db_path).close()  # a fresh one opens fine


def test_caches_are_trimmed_oldest_first(tmp_path):
    from hallucinate import cachetrim

    now = time.time()
    for i in range(10):
        f = tmp_path / f"{i}.jpg"
        f.write_bytes(b"x" * 1000)
        os.utime(f, (now - 1000 + i, now - 1000 + i))  # 0 is the least recently used
    cachetrim.touch_if_stale(tmp_path / "0.jpg")  # not a week old: left as is
    assert cachetrim.trim(tmp_path, 4500) == 6000
    assert sorted(p.name for p in tmp_path.iterdir()) == ["6.jpg", "7.jpg", "8.jpg", "9.jpg"]
    assert cachetrim.trim(tmp_path, 4500) == 0


def test_a_cleanly_closed_database_skips_the_full_check(tmp_path, monkeypatch):
    """The integrity check reads the whole file, which takes most of a second for a big library: after a clean
    exit with nothing changed since, it is skipped (but not for more than a week)."""
    db = tmp_path / "library.db"
    sqlite3.connect(db).execute("CREATE TABLE t (x)").connection.close()
    checks = []
    real = dbguard._healthy
    monkeypatch.setattr(dbguard, "_healthy", lambda p: checks.append(p) or real(p))
    backups = tmp_path / "backups"

    assert dbguard.check(db, backups) == "" and len(checks) == 1  # no marker yet: checked
    dbguard.mark_clean(db)
    assert dbguard.check(db, backups) == "" and len(checks) == 1  # clean exit, unchanged: skipped
    assert dbguard.check(db, backups) == "" and len(checks) == 2  # the marker is used up: this run "crashed"

    dbguard.mark_clean(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()
    assert dbguard.check(db, backups) == "" and len(checks) == 3  # changed since the clean exit: checked

    dbguard.mark_clean(db)
    marker = json.loads((tmp_path / "library.db.clean").read_text())
    marker["checked"] -= 8 * 24 * 3600
    (tmp_path / "library.db.clean").write_text(json.dumps(marker))
    assert dbguard.check(db, backups) == "" and len(checks) == 4  # a week since the last full check


def test_a_skipped_check_still_finds_damage_after_a_crash(tmp_path):
    db = tmp_path / "library.db"
    sqlite3.connect(db).execute("CREATE TABLE t (x)").connection.close()
    assert dbguard.check(db, tmp_path / "backups") == ""
    dbguard.mark_clean(db)
    db.write_bytes(b"not a database" * 100)  # changed (and damaged) after the clean exit
    assert "damaged" in dbguard.check(db, tmp_path / "backups")
