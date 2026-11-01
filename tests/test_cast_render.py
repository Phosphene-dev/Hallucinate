"""Hallucinate's sound for cast devices: songs written as WAV with ReplayGain, the equalizer and crossfeed, a CUE
song cut from its album's file, and the whole thing done by the decoding helper."""
import wave

import numpy as np
import pytest
from audio import FFMPEG, encode
from conftest import wait_for

from hallucinate.core.cast.render import Renderer, wav_header


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        frames = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, w.getnchannels())
        return w.getframerate(), frames.astype(np.float32) / 32768


def sine(rate=44100, seconds=1.0, freq=440, amp=0.5, channels=2):
    t = np.arange(int(rate * seconds)) / rate
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


def test_a_plain_song_is_written_as_it_is(tmp_path):
    out = tmp_path / "a.wav"
    r = Renderer(out)
    x = sine()
    for block in np.array_split(x, 7):
        assert r.add(block, 44100)
    info = r.finish()
    assert info == {"rate": 44100, "channels": 2, "frames": 44100, "seconds": 1.0}
    rate, y = read_wav(out)
    assert rate == 44100 and y.shape == x.shape
    assert np.max(np.abs(y - x)) < 3 / 32768  # 16-bit with a little dither, nothing more


def test_replaygain_is_applied(tmp_path):
    out = tmp_path / "g.wav"
    r = Renderer(out, gain=0.5)
    r.add(sine(amp=0.8), 44100)
    r.finish()
    _rate, y = read_wav(out)
    assert abs(np.max(np.abs(y)) - 0.4) < 0.01


def test_a_cue_song_is_cut_from_its_album(tmp_path):
    out = tmp_path / "cue.wav"
    album = np.arange(44100 * 3, dtype=np.float32)[:, None].repeat(2, axis=1) / (44100 * 3 * 2)
    r = Renderer(out, start=1.0, end=2.0)
    going = True
    blocks = np.array_split(album, 30)
    used = 0
    for block in blocks:
        if not going:
            break
        going = r.add(block, 44100)
        used += 1
    assert used < len(blocks)  # it said when it had all it needed
    assert r.finish()["frames"] == 44100
    _rate, y = read_wav(out)
    assert abs(y[0, 0] - album[44100, 0]) < 1e-3 and abs(y[-1, 0] - album[2 * 44100 - 1, 0]) < 1e-3


def test_the_equalizer_lines_up_with_the_song(tmp_path, qapp):
    from hallucinate import eq

    p = eq.EqProcessor()
    p.set_gains([3, 2, 0, 0, 0, 0, 0, 0, 1, 2])
    x = np.zeros((44100, 2), np.float32)
    x[20000] = 0.9  # a click
    out = tmp_path / "eq.wav"
    r = Renderer(out, processor=p, delay=eq.TAPS // 2)
    for block in np.array_split(x, 9):
        r.add(block, 44100)
    assert r.finish()["frames"] == 44100  # as long as the song: the filter's delay is taken back out
    _rate, y = read_wav(out)
    assert abs(int(np.argmax(np.abs(y[:, 0]))) - 20000) <= 1


def test_the_header_is_right():
    h = wav_header(48000, 2, 1000)
    assert h[:4] == b"RIFF" and h[8:16] == b"WAVEfmt " and len(h) == 44
    assert int.from_bytes(h[40:44], "little") == 4000


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_the_helper_renders_a_song_a_device_cant_play(qapp, tmp_path):
    from hallucinate.analysis import Analyser, render_options

    src = encode(tmp_path / "x.wv", "wv", seconds=2.0)
    out = tmp_path / "out.wav"
    got = []
    analyser = Analyser()
    try:
        analyser.submit(str(src), "render", got.append,
                        extra={"out": str(out), "options": render_options(gain=0.5, rate=44100, crossfeed="medium")})
        assert wait_for(lambda: got, timeout=60)
    finally:
        analyser.shutdown()
    assert got[0] and got[0]["rate"] == 44100 and abs(got[0]["seconds"] - 2.0) < 0.05
    rate, y = read_wav(out)
    assert rate == 44100 and y.shape[1] == 2 and 0.02 < np.max(np.abs(y)) < 0.07  # (ffmpeg's tone is 0.125: halved, then crossfed)


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_a_file_that_wont_decode_gives_nothing(qapp, tmp_path):
    from hallucinate.analysis import Analyser, render_options

    bad = tmp_path / "bad.flac"
    bad.write_bytes(b"fLaC" + b"\0" * 300)
    got = []
    analyser = Analyser()
    try:
        analyser.submit(str(bad), "render", got.append,
                        extra={"out": str(tmp_path / "o.wav"), "options": render_options()})
        assert wait_for(lambda: got, timeout=60)
    finally:
        analyser.shutdown()
    assert got == [None]
