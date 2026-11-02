"""The FLAC encoder behind Hallucinate's sound on cast devices: whatever goes in comes out of FFmpeg's decoder
(with every CRC and the bitstream checked) exactly as it was, and it's smaller than the WAV it replaces."""
import os
import subprocess

import numpy as np
import pytest
from audio import FFMPEG

from hallucinate.core.cast import flac

pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")


def decode(path, bps, channels):
    r = subprocess.run([FFMPEG, "-v", "error", "-err_detect", "crccheck+bitstream+buffer+explode", "-i", str(path),
                        "-f", "s32le" if bps == 24 else "s16le", "-"], capture_output=True)
    assert r.returncode == 0 and not r.stderr, r.stderr
    got = np.frombuffer(r.stdout, "<i4" if bps == 24 else "<i2").astype(np.int64).reshape(-1, channels)
    return got >> 8 if bps == 24 else got


def music(seconds, channels, rate=48000, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(rate * seconds)) / rate
    x = 0.4 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 3300 * t + 1) + 0.003 * rng.standard_normal(t.size)
    return np.stack([x, np.roll(x, 41) * 0.8][:channels], axis=1)


@pytest.mark.parametrize("bps,channels", [(24, 2), (16, 2), (24, 1), (16, 1)])
def test_what_goes_in_comes_out(tmp_path, bps, channels):
    full = (1 << (bps - 1)) - 1
    pcm = np.round(music(3.0, channels) * full).astype(np.int64)
    pcm = np.concatenate([pcm, np.zeros((5000, channels), np.int64), pcm[:777]])  # silence, then a short last block
    pcm[100] = full  # the very top and bottom of the range
    pcm[101] = -full - 1
    out = tmp_path / "x.flac"
    w = flac.Writer(str(out), 48000, channels, bps)
    for part in np.array_split(pcm, 97):  # (in uneven pieces, as decoded blocks come)
        w.add(part)
    w.finish()
    assert np.array_equal(decode(out, bps, channels), pcm)
    assert os.path.getsize(out) < 0.85 * pcm.size * bps // 8  # (smaller than the WAV would be)


def test_the_stream_info_says_what_it_holds(tmp_path):
    from mutagen.flac import FLAC

    out = tmp_path / "x.flac"
    w = flac.Writer(str(out), 44100, 2, 24)
    w.add(np.zeros((44100 * 2 + 5, 2), np.int64))
    w.finish()
    info = FLAC(str(out)).info
    assert (info.sample_rate, info.channels, info.bits_per_sample, info.total_samples) == (44100, 2, 24, 88205)


def test_checks_against_their_known_values():
    assert flac.crc16(b"123456789") == 0xFEE8  # CRC-16 (polynomial 0x8005), as FLAC uses
    assert flac.crc8(b"123456789") == 0xF4
    for n in (0, 0x7F, 0x80, 0x7FF, 0x800, 0xFFFF, 0x10000):
        assert flac._utf8_number(n) == chr(n).encode("utf-8", "surrogatepass")


def test_the_renderer_writes_24_bit_flac(tmp_path):
    from hallucinate.core.cast.render import Renderer

    out = tmp_path / "r.flac"
    r = Renderer(str(out), gain=0.5, kind="flac")
    x = music(2.0, 2, rate=44100).astype(np.float32)
    for part in np.array_split(x, 9):
        r.add(part, 44100)
    result = r.finish()
    assert result["frames"] == x.shape[0] and result["rate"] == 44100
    got = decode(out, 24, 2) / 8388607.0
    assert np.max(np.abs(got - x * 0.5)) < 2 / 8388607.0  # within a 24-bit step: nothing cut to 16 bits
