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


def test_the_appimage_starts_the_python_inside_it(monkeypatch, tmp_path):
    """In the AppImage, sys.executable is the AppImage file (which starts the app, not Python)."""
    import os

    from hallucinate import analysis

    monkeypatch.setattr(sys, "executable", "/home/me/Apps/hallucinate-0.9.9.5-x86_64.AppImage")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    program, args = analysis.command()
    assert program == sys.executable and args == ["--analysis-worker"]  # no Python inside: the app's own flag
    inside = tmp_path / "bin" / f"python{sys.version_info[0]}.{sys.version_info[1]}"
    inside.parent.mkdir()
    inside.write_text("")
    program, args = analysis.command()
    assert program == str(inside) and args[0] == "-s" and "-c" in args
    if sys.version_info >= (3, 11):  # not the current folder first: a folder named hallucinate there isn't the app
        assert "-P" in args
    assert os.path.basename(program).startswith("python")


def test_helper_finds_the_modules_this_process_was_given(monkeypatch, tmp_path):
    """Nix adds PySide6 and numpy to the module path inside its launcher, not through PYTHONPATH: the helper,
    started as a plain Python, gets the same path. The user's own site-packages stay out (the helper runs -s)."""
    import os
    import site
    from pathlib import Path

    from hallucinate import analysis

    store = tmp_path / "pyside6" / "site-packages"
    store.mkdir(parents=True)
    user = tmp_path / "user-site"
    user.mkdir()
    monkeypatch.setattr(sys, "path", [str(store), str(user), str(tmp_path / "gone")])
    monkeypatch.setattr(site, "getusersitepackages", lambda: str(user))
    monkeypatch.setattr(site, "ENABLE_USER_SITE", True)
    paths = analysis._helper_path("/extra" + os.pathsep + "/extra")
    assert paths[0] == str(Path(analysis.__file__).resolve().parent.parent)  # this copy of the app first
    assert paths[1:] == ["/extra", str(store)]
