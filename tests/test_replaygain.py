"""ReplayGain analysis: BS.1770 loudness, gating, album gain, storage, and decoding real files."""
import os
import subprocess

import numpy as np
import pytest
from audio import FFMPEG
from conftest import wait_for

from hallucinate import loudness
from hallucinate.core import health

needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")


def tone(seconds, rate=48000, freq=997.0, amp=1.0, channels=2):
    t = np.arange(int(rate * seconds)) / rate
    sig = amp * np.sin(2 * np.pi * freq * t)
    return np.stack([sig] * channels, axis=1)


def measure(samples, rate=48000, step=4096):
    m = loudness.Meter()
    for i in range(0, len(samples), step):
        m.add(samples[i:i + step], rate)
    return loudness.track_result(m)


@pytest.mark.parametrize("rate", [44100, 48000, 96000])
def test_calibration_tone_reads_zero_lufs(rate):
    # BS.1770: a full-scale 997 Hz sine in both channels measures 0 LUFS
    r = measure(tone(10, rate), rate)
    assert r["loudness"] == pytest.approx(0.0, abs=0.05)
    assert r["gain"] == pytest.approx(-18.0, abs=0.05) and r["peak"] == pytest.approx(1.0, abs=1e-3)


def test_level_mono_and_k_weighting():
    assert measure(tone(10, amp=0.1))["loudness"] == pytest.approx(-20.0, abs=0.05)
    assert measure(tone(10, channels=1))["loudness"] == pytest.approx(0.0, abs=0.05)  # dual mono
    assert measure(tone(10, freq=25))["loudness"] < -10  # bass is weighted down
    assert measure(tone(10, freq=8000))["loudness"] == pytest.approx(3.35, abs=0.05)  # +4.04 dB shelf, -0.691 offset


def test_gating_ignores_silence_and_quiet_passages():
    loud = tone(10)
    with_silence = np.concatenate([loud, np.zeros_like(loud), loud])
    assert measure(with_silence)["loudness"] == pytest.approx(0.0, abs=0.1)
    quiet = tone(10, amp=0.01)  # -40 LUFS: below the relative gate of a 0 LUFS programme
    assert measure(np.concatenate([loud, quiet]))["loudness"] == pytest.approx(0.0, abs=0.1)
    assert measure(np.zeros((48000, 2))) is None


def test_album_gain_measures_the_album_as_one():
    a = measure(tone(10, amp=1.0))
    b = measure(tone(10, amp=0.5))  # about -6 LU
    album = loudness.album_gain([a, b, None])
    assert b["gain"] > a["gain"] and a["gain"] < album < b["gain"]
    assert loudness.album_gain([None]) is None


def add(db, path, album="A", mtime=1.0, rg=None):
    db.upsert_track({
        "path": path, "mtime": mtime, "size": 10, "title": path, "artist": "X", "album_artist": "X", "aa_tag": 1,
        "album": album, "album_key": f"X|{album}", "track_no": 1, "disc_no": 0, "year": 2000, "genre": "",
        "duration": 10.0, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 44100,
        "rg_track": rg, "rg_album": rg, "rg_peak": None if rg is None else 0.9,
    })


def test_measurements_survive_rescans_but_tags_win(db):
    add(db, "/m/a")
    add(db, "/m/tagged", rg=-3.0)
    assert db.tracks_without_gain() == 1 and db.albums_needing_gain() == [("X|A", ["/m/a", "/m/tagged"])]
    db.store_loudness([{"path": "/m/a", "track_gain": -7.5, "album_gain": -6.0, "peak": 0.99},
                       {"path": "/m/tagged", "track_gain": -9.0, "album_gain": -6.0, "peak": 0.99}])

    def rg(path):
        return tuple(db.conn.execute("SELECT rg_track, rg_album, rg_measured FROM tracks WHERE path=?", (path,)).fetchone())

    assert rg("/m/a") == (-7.5, -6.0, 1) and rg("/m/tagged") == (-3.0, -3.0, 0)  # tags win
    add(db, "/m/a")  # a rescan of the unchanged, untagged file keeps the measurement
    assert rg("/m/a") == (-7.5, -6.0, 1)
    add(db, "/m/a", mtime=2.0)  # an edited file isn't trusted any more
    assert rg("/m/a") == (None, None, 0)
    assert any(c["id"] == "replaygain" and c["count"] == 1 for c in health.report(db)["checks"])


def _clip(path, amp):
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"aevalsrc='{amp}*sin(2*PI*997*t)|{amp}*sin(2*PI*997*t)':s=48000:d=4", str(path)], check=True)
    return str(path)


@needs_ffmpeg
def test_analyzer_measures_real_files(qapp, tmp_path, db):
    from hallucinate.replaygain import ReplayGainAnalyzer

    loud, soft = _clip(tmp_path / "loud.flac", 0.9), _clip(tmp_path / "soft.flac", 0.3)
    for p in (loud, soft):
        st = os.stat(p)
        db.upsert_track({
            "path": p, "mtime": st.st_mtime, "size": st.st_size, "title": p, "artist": "X", "album_artist": "X",
            "aa_tag": 1, "album": "A", "album_key": "X|A", "track_no": 1, "disc_no": 0, "year": 0, "genre": "",
            "duration": 4.0, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 48000,
        })
    db.commit()
    analyzer = ReplayGainAnalyzer(db.conn.execute("PRAGMA database_list").fetchone()["file"])
    finished = []
    analyzer.finished.connect(lambda: finished.append(1))
    try:
        assert analyzer.missingCount() == 2
        analyzer.analyseMissing()
        assert analyzer.busy and analyzer.total == 2
        assert wait_for(lambda: finished, 30)
        assert analyzer.done == 2 and analyzer.failed == 0 and not analyzer.busy
        rows = {r["path"]: r for r in db._rows("SELECT path, rg_track, rg_album, rg_peak, rg_measured FROM tracks")}
        # 0.9 amplitude -> about -0.9 LUFS -> gain about -17.1 dB; 0.3 is 9.5 dB quieter
        assert rows[loud]["rg_track"] == pytest.approx(-17.1, abs=0.3)
        assert rows[soft]["rg_track"] - rows[loud]["rg_track"] == pytest.approx(9.54, abs=0.2)
        assert rows[loud]["rg_album"] == rows[soft]["rg_album"] and rows[loud]["rg_measured"] == 1
        assert rows[loud]["rg_peak"] == pytest.approx(0.9, abs=0.02)
        assert analyzer.missingCount() == 0
    finally:
        analyzer.shutdown()
