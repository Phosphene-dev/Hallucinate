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


# --- macOS: the output device's own rate ---------------------------------------------------------------------
class FakeCoreAudio:
    def __init__(self, rates=((44100, 44100), (48000, 48000), (96000, 96000)), rate=48000.0, device=7):
        self.rates, self.rate, self.device, self.calls = list(rates), rate, device, []

    def default_device(self):
        return self.device

    def nominal_rate(self, device):
        return self.rate

    def available_rates(self, device):
        return self.rates

    def set_nominal_rate(self, device, rate):
        self.calls.append((device, rate))
        self.rate = rate


def test_a_mac_output_follows_each_song_and_gets_its_rate_back():
    from hallucinate.coreaudio import DeviceRate

    ca = FakeCoreAudio()
    r = RateRequest(run=DeviceRate(ca), which=lambda: "coreaudio")
    r.ask(96000, wait=True)
    r.ask(44100, wait=True)
    assert ca.calls == [(7, 96000), (7, 44100)] and not r.error
    r.ask(88200, wait=True)  # a rate the device hasn't got: left as it is (and said)
    assert ca.calls[-1] == (7, 44100) and "88200" in r.error
    r.release()
    assert ca.calls[-1] == (7, 48000.0)  # the rate it had before
    ca.device = 0
    assert not DeviceRate(ca).available()


def test_asked_on_a_mac_through_core_audio(monkeypatch):
    import sys

    from hallucinate import coreaudio

    monkeypatch.setattr(sys, "platform", "darwin")
    ca = FakeCoreAudio()
    monkeypatch.setattr(coreaudio, "DeviceRate", lambda ops=None, _real=coreaudio.DeviceRate: _real(ca))
    r = RateRequest()
    assert r.available
    r.ask(44100, wait=True)
    assert ca.calls == [(7, 44100)]


# --- Windows: exclusive mode ---------------------------------------------------------------------------------
def test_samples_reach_the_device_as_they_are_or_converted_exactly():
    from hallucinate import wasapi

    i32 = (np.arange(-50, 50, dtype=np.int64) * 9876543 << 8).astype("<i4")  # 24-bit samples, as decoded
    raw = i32.tobytes()
    assert wasapi.convert(raw, "int32", (32, 24, False)) == raw  # through as they are
    assert wasapi.convert(raw, "int32", (32, 32, False)) == raw
    packed = np.frombuffer(wasapi.convert(raw, "int32", (24, 24, False)), np.uint8).reshape(-1, 3)
    back = (packed[:, 0].astype(np.int32) | packed[:, 1].astype(np.int32) << 8 | packed[:, 2].astype(np.int32) << 16)
    back = np.where(back >= 1 << 23, back - (1 << 24), back)
    assert np.array_equal(back, i32 >> 8)  # packed 24-bit: every bit kept
    i16 = np.arange(-300, 300, dtype="<i2") * 101
    assert wasapi.convert(i16.tobytes(), "int16", (16, 16, False)) == i16.tobytes()
    widened = np.frombuffer(wasapi.convert(i16.tobytes(), "int16", (32, 24, False)), "<i4")
    assert np.array_equal(widened >> 16, i16)
    half = np.frombuffer(wasapi.convert(i16.tobytes(), "int16", (16, 16, False), volume=0.5), "<i2")
    assert np.abs(half.astype(int) - i16 // 2).max() <= 1


def test_the_format_described_to_windows():
    import ctypes

    from hallucinate import wasapi

    assert ctypes.sizeof(wasapi.WAVEFORMATEXTENSIBLE) == 40  # (as in mmreg.h)
    f = wasapi.wave_format(96000, 2, 32, 24)
    assert (f.tag, f.block_align, f.bytes_per_second, f.valid_bits, f.channel_mask, f.extra_size) == (
        0xFFFE, 8, 768000, 24, 0x3, 22)
    assert f.subformat.data1 == 1 and bytes(f.subformat.data4) == bytes.fromhex("800000aa00389b71")


def test_where_exclusive_mode_cant_be_had_the_shared_output_plays(qapp):
    from PySide6.QtMultimedia import QAudioBuffer, QAudioFormat

    from hallucinate import eq

    tap = eq.EqTap(eq.EqProcessor(), passthrough=True)
    tap.exclusive = True  # (not Windows here: it can't be had, so the usual output is used)
    tap._drain = lambda: None
    fmt = QAudioFormat()
    fmt.setSampleRate(48000)
    fmt.setChannelCount(2)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    try:
        tap._on_buffer(QAudioBuffer(b"\0" * 4800, fmt))
        assert tap.exclusive_error and not tap.exclusive_open
        failed = tap.failed
    finally:
        del tap._drain
        tap.close()
        tap.deleteLater()
    if failed:
        pytest.skip("no sound output here")


def test_the_signal_path_says_why_exclusive_mode_wasnt_had():
    from hallucinate.signalpath import describe

    path = describe({"codec": "FLAC", "sample_rate": 96000}, bit_perfect=True, device_rate=48000,
                    bit_perfect_issue="Exclusive mode couldn't be had (another app is using this output by itself)")
    assert path["advice"][0].startswith("Exclusive mode couldn't be had")


class FakeSink:
    error = ""
    format = None
    volume = 1.0

    def wake(self):
        pass


def test_one_song_plays_out_and_the_next_goes_straight_on():
    """Exclusive mode holds one output for both of the player's voices: the song ending plays to its last
    sample, then the next one starts, never mixed in between (whatever order their sound arrives in)."""
    from hallucinate.wasapi import Sequencer

    seq = Sequencer()
    old, new = seq.add(100, FakeSink()), seq.add(100, FakeSink())
    old.resume()
    old.write(b"A" * 30)
    new.resume()
    new.write(b"B" * 40)
    old.write(b"a" * 10)  # (the old song's very last sound, arriving after the next song's first)
    assert seq.take(25) == b"A" * 25
    assert seq.take(25) == b"A" * 5 + b"a" * 10 + b"B" * 10  # its tail, then straight on
    assert old.closed and seq.writers == [new]
    old.write(b"x" * 10)  # late: let go
    assert seq.take(100) == b"B" * 30


def test_a_paused_song_gives_way_and_an_underrun_waits():
    from hallucinate.wasapi import Sequencer

    seq = Sequencer()
    cur = seq.add(100, FakeSink())
    cur.resume()
    cur.write(b"A" * 10)
    assert seq.take(20) == b"A" * 10  # (nothing more yet: the rest is silence, and it carries on after)
    assert seq.writers == [cur] and not seq.busy()
    cur.write(b"A" * 10)
    assert seq.busy()
    nxt = seq.add(100, FakeSink())
    cur.suspend()  # paused (or finished) while the next one plays: its sound is let go
    nxt.resume()
    nxt.write(b"B" * 10)
    assert seq.take(20) == b"B" * 10 and seq.writers == [nxt]
    nxt.stop()
    assert not seq.running()


def test_a_held_output_at_another_rate_waits_for_the_song_before(monkeypatch):
    from hallucinate import wasapi

    made = []

    class Sink:
        def __init__(self, endpoint, rate, channels, kind):
            self.endpoint, self.rate, self.channels, self.kind = endpoint, rate, channels, kind
            self.sequencer, self.alive, self.error, self.format, self.volume = wasapi.Sequencer(), True, "", None, 1.0
            made.append(self)

        def matches(self, endpoint, rate, channels, kind):
            return (endpoint, rate, channels, kind) == (self.endpoint, self.rate, self.channels, self.kind)

        def add_writer(self, buffer_ms=250):
            return self.sequencer.add(1000, self)

        def wake(self):
            pass

        def stop(self):
            self.alive = False

    monkeypatch.setattr(wasapi, "ExclusiveSink", Sink)
    try:
        a = wasapi.open_writer("", 44100, 2, "int32")
        a.resume()
        a.write(b"\0" * 16)
        b = wasapi.open_writer("", 44100, 2, "int32")  # the same format: the same held output
        assert b._sink is a._sink and len(made) == 1
        with pytest.raises(wasapi.Busy):
            wasapi.open_writer("", 96000, 2, "int32")  # another rate while the first still plays
        a._seq.take(16)
        c = wasapi.open_writer("", 96000, 2, "int32")  # played out: opened afresh at the new rate
        assert len(made) == 2 and not made[0].alive and c._sink is made[1]
    finally:
        wasapi.release()
