"""Bit-perfect playback: the decoded song goes out exactly as it came (its own format, nothing filtered), everything
in Hallucinate that would change it steps aside, and PipeWire is asked for each song's own rate."""
import numpy as np
import pytest
from audio import FFMPEG, encode
from conftest import wait_for

from hallucinate.bitperfect import RateRequest


def test_rates_are_asked_for_once_and_given_back():
    asked = []
    r = RateRequest(run=asked.append, which=lambda: "/usr/bin/pw-metadata")
    r.ask(96000, wait=True)
    r.ask(96000, wait=True)  # the same again: not asked twice
    r.ask(44100, wait=True)
    r.ask(12345, wait=True)  # not a usual rate: PipeWire chooses again
    r.release()
    assert asked == [96000, 44100, 0]
    r.release()  # nothing to give back
    assert asked == [96000, 44100, 0]


def test_a_failing_tool_is_remembered_not_fatal():
    def broken(rate):
        raise OSError("no PipeWire here")
    r = RateRequest(run=broken, which=lambda: "")
    r.ask(48000, wait=True)
    assert r.error == "no PipeWire here" and not r.available


def test_the_passthrough_output_writes_the_samples_as_they_are(qapp):
    from PySide6.QtMultimedia import QAudioBuffer, QAudioFormat

    from hallucinate import eq

    tap = eq.EqTap(eq.EqProcessor(), passthrough=True)
    opened = []
    tap.opened.connect(opened.append)
    fmt = QAudioFormat()
    fmt.setSampleRate(96000)
    fmt.setChannelCount(2)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int32)
    samples = (np.arange(4000, dtype=np.int64) * 2654435761 % (2 ** 32) - 2 ** 31).astype("<i4")  # (every bit used)
    buf = QAudioBuffer(samples.tobytes(), fmt)
    written = []
    tap._drain = lambda: written.append(bytes(tap._pending))  # (what would reach the sound output)
    try:
        tap._on_buffer(buf)
        failed = tap.failed
        if not failed:
            assert opened == [96000]
            assert tap._fmt == (96000, 2, QAudioFormat.SampleFormat.Int32)  # opened in the song's own format
            assert written[-1] == samples.tobytes()  # byte for byte
    finally:
        del tap._drain  # (the stand-in held the tap: let go)
        tap.close()
        tap.deleteLater()
    if failed:
        pytest.skip("no sound output here")


@pytest.fixture
def player(qapp, tmp_path):
    from hallucinate.player import Player

    p = Player(session_file=tmp_path / "s.json")
    p._rate_request = RateRequest(run=lambda rate: None, which=lambda: "/usr/bin/pw-metadata")
    yield p
    p.setBitPerfect(False)
    p.setEqEnabled(False)
    p.setReplayGainMode("off")
    p.setCrossfade(0)
    p.shutdown()


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_everything_that_changes_the_sound_steps_aside(player, tmp_path):
    song = encode(tmp_path / "s.flac", "flac", seconds=3.0)
    player.setEqEnabled(True)
    player.setReplayGainMode("track")
    player.setCrossfade(5)
    player.setVolume(0.4)
    player.setBitPerfect(True)
    assert player.bitPerfect and player.volume == 1.0
    player.setVolume(0.2)  # Hallucinate's volume stays out of it
    assert player.volume == 1.0 and player._volume == 0.4  # (kept for when it's switched off)
    player.playList([{"id": 1, "path": str(song), "title": "S", "artist": "A", "album": "B", "duration": 3.0,
                      "sample_rate": 44100, "rg_track": -9.0, "artUrl": ""}], 0)
    assert wait_for(lambda: player.state == "Playing", timeout=10)
    assert all(v.tap is None or v.tap.passthrough for v in player._voices)
    assert player._rate() == 1.0
    tap = player._voices[player._cur].tap
    assert tap is not None and tap.passthrough
    # the output opens in the song's own format and PipeWire is asked for its rate (where there's a sound device)
    assert wait_for(lambda: player._rate_request.rate == 44100 or tap.failed, timeout=10)
    path = player.signalPath
    if not tap.failed:
        assert path["untouched"] and path["summary"] == "Bit-perfect"
    stages = {s["key"]: s for s in path["stages"]}
    assert not stages["eq"]["active"] and not stages["replaygain"]["active"] and not stages["volume"]["active"]
    player.setBitPerfect(False)
    assert player.volume == 0.4 and player._rate_request.rate == 0  # given back
    player.play()
    assert wait_for(lambda: player.state == "Playing", timeout=10)
    said = []
    player.notice.connect(said.append)
    player.setBitPerfect(True)  # mid-song at 40%: it would jump to full level, so it pauses first
    assert not player.playing and said and "system's volume" in said[-1]
