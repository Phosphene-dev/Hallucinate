"""Listening recaps: periods, totals, tops, discoveries and patterns."""
import datetime
import time

import pytest

from hallucinate.core import recap

DAY = 86_400
NOW = time.mktime(datetime.datetime(2026, 10, 11, 20, 0).timetuple())  # a Sunday


def at(y, m, d, h=12):
    return time.mktime(datetime.datetime(y, m, d, h).timetuple())


def add(db, path, artist, album, genre="Folk", duration=200.0):
    db.upsert_track({
        "path": path, "mtime": 0, "size": 1, "title": path.rsplit("/", 1)[1], "artist": artist,
        "album_artist": artist, "aa_tag": 1, "album": album, "album_key": f"{artist}|{album}", "track_no": 1,
        "disc_no": 0, "year": 2000, "genre": genre, "duration": duration, "fmt": "FLAC", "codec": "FLAC",
        "bitrate": 0, "sample_rate": 44100,
    })


def test_periods():
    assert recap.current("week", NOW) == "week:2026-10-05"
    assert recap.current("month", NOW) == "month:2026-10"
    assert recap.current("year", NOW) == "year:2026"
    assert recap.step("month:2026-01", -1) == "month:2025-12" and recap.step("month:2026-12", 1) == "month:2027-01"
    assert recap.step("week:2026-10-08", 1) == "week:2026-10-12"
    assert recap.parse("week:2026-10-08")[1] == datetime.date(2026, 10, 5)
    assert recap.title("month:2026-10", NOW) == "This month" and recap.title("month:2026-09", NOW) == "Last month"
    assert recap.title("month:2026-03", NOW) == "March 2026" and recap.title("year:2024", NOW) == "2024"
    assert recap.title("week:2026-09-14", NOW) == "Week of 14 Sep 2026"
    with pytest.raises(ValueError):
        recap.parse("decade:1990")


def test_month_recap(db):
    add(db, "/m/old", "Old Friend", "Before", genre="Jazz")
    add(db, "/m/a", "Ada", "One", genre="Folk; Dream Pop")
    add(db, "/m/b", "Bo", "Two", genre="Rock")
    db.record_play("/m/old", at(2026, 8, 1))  # heard before October
    for i, day in enumerate((3, 3, 4, 5, 9)):
        db.record_play("/m/a", at(2026, 10, day, 21) + i)
    db.record_play("/m/b", at(2026, 10, 9, 8))
    db.record_play("/m/old", at(2026, 10, 9, 9))
    db.record_play("/m/a", at(2026, 9, 20))  # previous month
    r = recap.recap(db, "month:2026-10", now=NOW)
    assert r["title"] == "This month" and r["start"] == "2026-10-01" and r["end"] == "2026-10-31"
    assert r["summary"]["plays"] == 7 and r["summary"]["seconds"] == 1400.0
    assert r["change"] == pytest.approx(6.0)  # 1400 s against 200 s in September
    assert [a["name"] for a in r["topArtists"]] == ["Ada", "Bo", "Old Friend"]
    assert r["topArtists"][0]["plays"] == 5 and r["topSongs"][0]["path"] == "/m/a"
    assert r["topAlbums"][0]["album_key"] == "Ada|One"
    assert r["discoveryCount"] == 1 and r["discoveries"][0]["name"] == "Bo"  # Ada was heard in September
    assert set(r["genres"][:2]) == {"Folk", "Dream Pop"}  # tied, then alphabetical
    assert r["busiestDay"]["day"] == "2026-10-09" and r["busiestDay"]["plays"] == 3
    assert r["hours"][21] == 5 and sum(r["hours"]) == 7 and r["weekdays"][4] == 3  # 9 Oct 2026 is a Friday
    assert r["streak"] == 3 and r["months"] == [] and r["hasNext"] is False


def test_year_recap_and_empty_period(db):
    add(db, "/m/a", "Ada", "One")
    db.record_play("/m/a", at(2025, 2, 1))
    db.record_play("/m/a", at(2025, 2, 2))
    db.record_play("/m/a", at(2025, 7, 1))
    r = recap.recap(db, "year:2025", now=NOW)
    assert [m["plays"] for m in r["months"]][:7] == [0, 2, 0, 0, 0, 0, 1] and r["hasNext"] is True
    assert r["change"] is None  # nothing in 2024 to compare with
    empty = recap.recap(db, "week:2026-10-05", now=NOW)
    assert empty["summary"]["plays"] == 0 and empty["topArtists"] == [] and empty["busiestDay"] is None


def test_user_library_recap(qapp, db, tmp_path):
    from conftest import wait_for
    from PySide6.QtGui import QColor, QImage

    from hallucinate.userlib import UserLibrary

    add(db, "/m/a", "Ada", "One")
    db.record_play("/m/a", time.time() - 60)
    db.commit()
    ul = UserLibrary(db.conn.execute("PRAGMA database_list").fetchone()["file"])
    try:
        ul.loadRecap("month")
        assert wait_for(lambda: ul.recap.get("summary", {}).get("plays") == 1 and not ul.recap["loading"])
        assert ul.recap["topArtists"][0]["name"] == "Ada" and "artUrl" in ul.recap["topArtists"][0]
        ul.stepRecap(-1)
        assert wait_for(lambda: not ul.recap["loading"] and ul.recap["summary"]["plays"] == 0)
        img = QImage(20, 10, QImage.Format.Format_RGB32)
        img.fill(QColor("red"))
        import os

        os.environ["HOME"] = str(tmp_path)
        saved = ul.saveRecapImage(img)
        assert saved.endswith(".png") and os.path.exists(saved)
        assert os.path.basename(os.path.dirname(saved)) == "Hallucinate"  # its own folder (the Flatpak may write only there)
        assert ul.saveRecapImage(QImage()) == ""
    finally:
        ul.shutdown()
