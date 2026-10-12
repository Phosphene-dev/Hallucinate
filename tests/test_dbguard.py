"""The library database: daily backups, and a damaged one set aside and restored rather than failing to start."""
import os
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
