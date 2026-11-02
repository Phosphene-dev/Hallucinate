"""DSD files (.dsf, .dff) play as high-resolution PCM: FFmpeg's decode, low-passed (the ultrasonic noise DSD
carries filtered out) and brought down to the rate chosen in Settings, with the music's level left as it is."""
import subprocess

import numpy as np
import pytest
from audio import FFMPEG, encode, make_dff, make_dsf
from conftest import wait_for

from hallucinate import dsd

needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")


def decoded(path):
    """What FFmpeg (as the player uses it) makes of a DSD file: float PCM at an eighth of its bit rate."""
    out = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-f", "f32le", "-"], capture_output=True,
                         check=True).stdout
    return np.frombuffer(out, "<f4").reshape(-1, 2)


def band_db(x, rate, lo, hi):
    s = x[rate // 4:, 0]
    power = np.abs(np.fft.rfft(s * np.hanning(len(s)))) ** 2
    f = np.fft.rfftfreq(len(s), 1 / rate)
    return 10 * np.log10(power[(f > lo) & (f < hi)].sum() + 1e-30)


def test_rates_follow_the_dsd_family():
    assert [dsd.output_rate(352800, r) for r in dsd.RATES] == [88200, 176400, 352800]  # DSD64
    assert [dsd.output_rate(1411200, r) for r in dsd.RATES] == [88200, 176400, 352800]  # DSD256
    assert [dsd.output_rate(384000, r) for r in dsd.RATES] == [96000, 192000, 384000]  # 48 kHz DSD
    assert dsd.output_rate(352800, 12345) == dsd.output_rate(352800, dsd.DEFAULT_RATE)
    assert dsd.is_dsd({"codec": "DSD"}) and dsd.is_dsd({"path": "/m/a.DFF"}) and not dsd.is_dsd({"path": "a.flac"})


@needs_ffmpeg
@pytest.mark.parametrize("out_rate", dsd.RATES)
def test_the_noise_goes_and_the_music_stays(tmp_path, out_rate):
    x = decoded(make_dsf(tmp_path / "s.dsf", seconds=1.0))
    raw_noise = band_db(x, 352800, 45000, 170000) - band_db(x, 352800, 900, 1100)
    assert raw_noise > -60  # (what FFmpeg leaves: plenty of ultrasonic noise)
    conv = dsd.Converter(352800, 2, out_rate)
    y = np.concatenate([conv.process(b) for b in np.array_split(x, 37)])  # in uneven pieces, as buffers come
    assert abs(len(y) - len(x) // conv.factor) <= conv.delay // conv.factor + 1
    music = band_db(y, out_rate, 900, 1100)
    assert abs(np.sqrt(2) * y[out_rate // 4:, 0].std() / (np.sqrt(2) * x[88200:, 0].std()) - 1) < 0.02  # same level
    if out_rate > 90000:
        assert band_db(y, out_rate, 45000, out_rate / 2) - music < -110  # the noise is gone
    whole = dsd.Converter(352800, 2, out_rate).process(x)
    assert np.allclose(whole[:len(y)], y[:len(whole)], atol=1e-6)  # pieces or all at once: the same


@needs_ffmpeg
@pytest.mark.parametrize("maker,ext", [(make_dsf, "dsf"), (make_dff, "dff")])
def test_both_kinds_of_file_are_read_as_dsd(tmp_path, maker, ext):
    from hallucinate.core.tags import read_track

    t = read_track(str(maker(tmp_path / f"s.{ext}", seconds=0.5)))
    assert t["codec"] == "DSD" and t["sample_rate"] == 2822400 and t["bit_depth"] == 1
    assert dsd.is_dsd(t)


def test_the_tap_converts_before_anything_else(qapp):
    from PySide6.QtMultimedia import QAudioBuffer, QAudioFormat

    from hallucinate import eq

    tap = eq.EqTap(eq.EqProcessor())
    tap.setDsd(True, 88200)
    opened = []
    tap.opened.connect(opened.append)
    fmt = QAudioFormat()
    fmt.setSampleRate(352800)
    fmt.setChannelCount(2)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
    t = np.arange(35280) / 352800
    samples = np.repeat((0.5 * np.sin(2 * np.pi * 1000 * t)).astype("<f4")[:, None], 2, axis=1)
    written = []
    tap._drain = lambda: written.append(bytes(tap._pending))
    try:
        tap._on_buffer(QAudioBuffer(samples.tobytes(), fmt))
        failed = tap.failed
        if not failed:
            assert opened == [88200] and tap._fmt[0] == 88200
            kind = "<f4" if tap._fmt[2] == QAudioFormat.SampleFormat.Float else "<i2"
            out = np.frombuffer(written[-1], kind).reshape(-1, 2)
            assert abs(len(out) - 35280 // 4) < 100  # a quarter as many samples, at 88.2 kHz
    finally:
        del tap._drain
        tap.close()
        tap.deleteLater()
    if failed:
        pytest.skip("no sound output here")


def test_the_signal_path_says_what_happens():
    from hallucinate.signalpath import describe

    track = {"codec": "DSD", "sample_rate": 2822400, "path": "a.dsf"}
    path = describe(track, dsd_rate=176400)
    stages = {s["key"]: s for s in path["stages"]}
    assert stages["source"]["detail"].startswith("DSD64") and "2.82 MHz" in stages["source"]["detail"]
    assert stages["dsd"]["active"] and "176.4 kHz" in stages["dsd"]["detail"]
    assert not path["untouched"] and "DSD to PCM" in path["summary"]
    bp = describe(track, dsd_rate=176400, bit_perfect=True, device_rate=176400)
    assert bp["summary"] == "Bit-perfect after DSD conversion"


@pytest.fixture
def player(qapp, tmp_path):
    from hallucinate.player import Player

    p = Player(session_file=tmp_path / "s.json")
    yield p
    p.setDsdRate(dsd.DEFAULT_RATE)
    p.shutdown()


@needs_ffmpeg
def test_a_dsd_song_plays_through_the_conversion_and_a_flac_after_it_doesnt(player, tmp_path):
    from hallucinate.core.tags import read_track

    song = read_track(str(make_dsf(tmp_path / "s.dsf", seconds=2.0)))
    flac = read_track(str(encode(tmp_path / "f.flac", "flac", seconds=2.0)))
    for i, t in enumerate((song, flac)):
        t.update(id=i + 1, artUrl="", title=f"T{i}")
    assert not player._tap_on()  # nothing to process: no taps
    player.playList([song, flac], 0)
    assert wait_for(lambda: player.state == "Playing", timeout=10)
    tap = player._voices[player._cur].tap
    assert tap is not None and tap.dsd and tap.dsd_rate == dsd.DEFAULT_RATE
    assert {s["key"] for s in player.signalPath["stages"]} >= {"dsd"}
    player.setDsdRate(176400)
    assert tap.dsd_rate == 176400 and "176.4 kHz" in {s["key"]: s for s in player.signalPath["stages"]}["dsd"]["detail"]
    player.playIndex(1)
    assert wait_for(lambda: player.state == "Playing" and player.currentIndex == 1, timeout=10)
    assert wait_for(lambda: all(v.tap is None for v in player._voices), timeout=5)  # the FLAC plays as before
    assert "dsd" not in {s["key"] for s in player.signalPath["stages"]}


@needs_ffmpeg
def test_measured_and_drawn_as_heard(qapp, tmp_path):
    """ReplayGain and the waveform come from the converted sound, not the noise riding on it."""
    from hallucinate.analysis import Analyser

    song = str(make_dsf(tmp_path / "s.dsf", seconds=2.0, amp=0.5))
    analyser, got = Analyser(), {}
    try:
        analyser.submit(song, "waveform", lambda r: got.__setitem__("wave", r), envelope=True)
        analyser.submit(song, "loudness", lambda r: got.__setitem__("loud", r))
        assert wait_for(lambda: len(got) == 2, 60), got
    finally:
        analyser.shutdown()
    assert got["loud"] and abs(got["loud"]["peak"] - 0.5) < 0.03  # the sine's own peak, no noise spikes
    ms, peak, rate = got["wave"]["envelope"]
    assert rate == 88200 and max(peak) < 0.53


def test_dff_songs_scanned_before_become_dsd(tmp_path):
    from hallucinate.core.db import Database

    db = Database(tmp_path / "old.db")
    for path, codec in (("/m/a.dff", "DFF"), ("/m/b.flac", "FLAC")):
        db.upsert_track({"path": path, "mtime": 5, "size": 1, "title": path, "artist": "A", "album_artist": "A",
                         "aa_tag": 1, "album": "B", "album_key": "k", "track_no": 1, "disc_no": 0, "year": 0,
                         "genre": "", "duration": 1.0, "fmt": codec, "codec": codec, "bitrate": 0, "sample_rate": 0})
    db.conn.execute("PRAGMA user_version = 1")
    db.commit()
    db.close()
    db = Database(tmp_path / "old.db")
    got = {r[0]: (r[1], r[2]) for r in db.conn.execute("SELECT path, codec, bit_depth FROM tracks")}
    assert got == {"/m/a.dff": ("DSD", 1), "/m/b.flac": ("FLAC", 0)}
    db.close()


def test_after_a_24_bit_song_the_output_is_opened_afresh(qapp):
    """Bit-perfect: a 24-bit song at 88.2 kHz, then a DSD one converted to 88.2 kHz. The output opened for the
    first (32-bit integers) isn't fed the conversion's samples: it's opened again for them."""
    from PySide6.QtMultimedia import QAudioBuffer, QAudioFormat

    from hallucinate import eq

    tap = eq.EqTap(eq.EqProcessor(), passthrough=True)
    tap._drain = lambda: None

    def buffer(rate, kind, sample_format):
        fmt = QAudioFormat()
        fmt.setSampleRate(rate)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(sample_format)
        return QAudioBuffer(np.zeros(8820, kind).tobytes(), fmt)

    try:
        tap._on_buffer(buffer(88200, "<i4", QAudioFormat.SampleFormat.Int32))
        failed = tap.failed
        if not failed:
            assert tap._fmt[2] == QAudioFormat.SampleFormat.Int32
            tap.setDsd(True, 88200)
            tap._on_buffer(buffer(352800, "<f4", QAudioFormat.SampleFormat.Float))
            assert tap._fmt[0] == 88200 and tap._fmt[2] in (QAudioFormat.SampleFormat.Float,
                                                           QAudioFormat.SampleFormat.Int16)
    finally:
        del tap._drain
        tap.close()
        tap.deleteLater()
    if failed:
        pytest.skip("no sound output here")


@needs_ffmpeg
def test_a_dsd_song_cast_as_hallucinates_sound(qapp, tmp_path):
    """Rendered for a cast device, the decoder brings DSD down to the device's rate itself (its own filter takes
    the noise out): it's left as it comes, not filtered for a rate it no longer has."""
    from hallucinate.analysis import Analyser, render_options

    song = str(make_dsf(tmp_path / "s.dsf", seconds=2.0, amp=0.5))
    out = tmp_path / "out.flac"
    got = []
    analyser = Analyser()
    try:
        analyser.submit(song, "render", got.append,
                        extra={"out": str(out), "options": render_options(rate=44100, kind="flac")})
        assert wait_for(lambda: got, timeout=60)
    finally:
        analyser.shutdown()
    assert got[0] and got[0]["rate"] == 44100 and abs(got[0]["seconds"] - 2.0) < 0.05
    y = decoded(out)
    assert abs(np.sqrt(2) * y[11025:, 0].std() - 0.5) < 0.02  # the music at its own level
    with pytest.raises(ValueError):
        dsd.Converter(44100, 2, 44100)
