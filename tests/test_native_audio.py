"""The parts of bit-perfect playback that talk to the system itself: Core Audio on macOS, WASAPI on Windows. They
run on CI's own Mac and Windows machines (which may have no sound device: then each says so plainly rather than
failing in some other way)."""
import sys

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_core_audio_reads_and_keeps_the_outputs_rate():
    from hallucinate import coreaudio

    try:
        device = coreaudio.default_device()
    except OSError as e:
        pytest.skip(f"no sound output here ({e})")
    if not device:
        pytest.skip("no sound output here")
    rate = coreaudio.nominal_rate(device)
    ranges = coreaudio.available_rates(device)
    assert rate > 0 and ranges and coreaudio.supports(ranges, rate)
    switch = coreaudio.DeviceRate()
    switch(int(rate))  # its own rate: nothing changes
    switch(0)  # and put back
    assert coreaudio.nominal_rate(device) == rate


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_exclusive_mode_opens_or_says_why():
    from hallucinate import wasapi

    try:
        writer = wasapi.open_writer("", 48000, 2, "int16")
    except RuntimeError as e:
        assert str(e)  # a plain reason (no output, in use, not allowed, format)
        return
    try:
        assert writer.format is not None
        io = writer.start()
        assert io.write(b"\0" * 19200) == 19200
        writer.resume()
        same = wasapi.open_writer("", 48000, 2, "int16")  # the next song at the same format: the same output
        assert same._sink is writer._sink
        same.stop()
        writer.suspend()
        assert not writer.error
    finally:
        writer.stop()
        wasapi.release()
