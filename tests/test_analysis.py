"""The helper process that decodes songs for waveforms and ReplayGain: a song it gets stuck on, or dies on,
can't hold up the window, and the next song is done by a fresh helper."""
import sys
import time

import pytest
from audio import FFMPEG, encode
from conftest import wait_for

# A stand-in helper: answers a job by its path ("hang" never answers, "die" exits, anything else succeeds).
FAKE = r"""
import json, sys, time
for line in sys.stdin:
    job = json.loads(line)
    if "hang" in job["path"]:
        time.sleep(3600)
    if "die" in job["path"]:
        sys.exit(3)
    print(json.dumps({"id": job["id"], "result": {"peaks": [0.5], "who": job["path"]}}), flush=True)
"""


@pytest.fixture
def fake(qapp, monkeypatch):
    from hallucinate import analysis

    monkeypatch.setattr(analysis, "STALL_S", 0.5)
    made = []

    def make():
        a = analysis.Analyser(program=(sys.executable, ["-c", FAKE]))
        made.append(a)
        return a

    yield make
    for a in made:
        a.shutdown()


def test_a_song_the_helper_gets_stuck_on_is_given_up_and_the_next_one_done(fake):
    analyser, got = fake(), []
    started = time.monotonic()
    analyser.submit("a/hang.flac", "waveform", lambda r: got.append(("hang", r)))
    analyser.submit("a/fine.flac", "waveform", lambda r: got.append(("fine", r)))
    assert time.monotonic() - started < 0.5  # asking never waits
    assert wait_for(lambda: len(got) == 2, 15), got
    assert got[0] == ("hang", None)
    assert got[1][0] == "fine" and got[1][1]["who"] == "a/fine.flac"


def test_a_helper_that_dies_on_a_song_counts_it_as_failed(fake):
    analyser, got = fake(), []
    analyser.submit("a/die.flac", "waveform", got.append)
    analyser.submit("a/fine.flac", "waveform", got.append)
    assert wait_for(lambda: len(got) == 2, 15), got
    assert got[0] is None and got[1]["who"] == "a/fine.flac"


def test_cancel_abandons_the_song_in_progress(fake):
    analyser, got = fake(), []
    analyser.submit("a/hang.flac", "waveform", got.append)
    analyser.submit("a/fine.flac", "waveform", got.append)
    time.sleep(0.2)
    analyser.cancel()
    assert not analyser.busy
    analyser.submit("b/fine.flac", "waveform", got.append)
    assert wait_for(lambda: got, 15)
    time.sleep(0.3)
    assert len(got) == 1 and got[0]["who"] == "b/fine.flac"


def test_a_helper_that_cant_start_fails_its_songs(qapp):
    from hallucinate.analysis import Analyser

    analyser, got = Analyser(program=("/nonexistent/hallucinate", [])), []
    analyser.submit("a.flac", "waveform", got.append)
    assert wait_for(lambda: got, 10) and got == [None]
    analyser.shutdown()


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_the_real_helper_measures_and_draws(qapp, tmp_path):
    from hallucinate.analysis import Analyser

    song = encode(tmp_path / "a.flac", "flac", seconds=2)
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio" * 300)
    analyser, got = Analyser(), {}
    analyser.submit(song, "waveform", lambda r: got.__setitem__("wave", r), envelope=True)
    analyser.submit(song, "loudness", lambda r: got.__setitem__("loud", r))
    analyser.submit(bad, "loudness", lambda r: got.__setitem__("bad", r))
    assert wait_for(lambda: len(got) == 3, 30), got
    assert len(got["wave"]["peaks"]) == 600 and max(got["wave"]["peaks"]) == 1.0
    ms, peak, rate = got["wave"]["envelope"]
    assert rate > 0 and len(ms) == len(peak) > 0
    assert -30 < got["loud"]["loudness"] < 0 and len(got["loud"]["blocks"]) > 0
    assert got["bad"] is None
    analyser.shutdown()
