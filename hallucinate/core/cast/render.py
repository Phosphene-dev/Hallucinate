"""Hallucinate's own sound for a cast device: a song decoded, put through ReplayGain, the equalizer and
crossfeed as it would be here, and written as a WAV file the device fetches like any other.

The decoding happens in the helper process (analysis.py, kind "render"); this is the part that turns decoded
blocks into the file, so it's plain numpy and tested on its own. A WAV file is lossless and every Chromecast and
DLNA device plays it; it's 16-bit with triangular dither (the processing itself is in 32-bit float), at the
song's own sample rate up to `max_rate` (the decoder converts higher rates before they get here).

A CUE sheet song is cut from its album's file: only frames in [start, end) are written."""
import struct

import numpy as np

HEADER = 44


def wav_header(rate, channels, frames, bits=16):
    data = frames * channels * bits // 8
    return (b"RIFF" + struct.pack("<I", 36 + data) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * channels * bits // 8,
                                    channels * bits // 8, bits)
            + b"data" + struct.pack("<I", data))


class Renderer:
    """Takes decoded float blocks (frames, channels) with add(), writes the WAV file, finish() completes it.

    `processor` is an eq.EqProcessor (or None for none) and `delay` how many frames it holds back (the
    equalizer's filter delays everything by half its length; they're dropped from the front and flushed at the
    end, so the file lines up with the song); `gain` a linear ReplayGain factor; `start`/`end` the song's window
    in seconds (end 0: to the end of the file)."""

    def __init__(self, out, processor=None, delay=0, gain=1.0, start=0.0, end=0.0, seed=0):
        self._out = open(out, "wb")
        self._out.write(b"\0" * HEADER)  # the real header goes in at the end, once the length is known
        self.processor = processor
        self.gain = float(gain)
        self.start, self.end = float(start), float(end)
        self.rate = 0
        self.channels = 0
        self.frames = 0  # written
        self._read = 0  # frames of the source seen so far
        self._delay = int(delay) if processor is not None else 0
        self._skip = self._delay  # the equalizer's delay, dropped from the front
        self._rng = np.random.default_rng(seed)
        self.done = False

    def _begin(self, rate, channels):
        self.rate, self.channels = rate, channels
        if self.processor is not None and not self.processor.flat:
            self.processor.configure(rate, channels)
        else:
            self.processor = None
            self._delay = self._skip = 0

    def add(self, samples, rate):
        """samples: float32 (frames, channels) in [-1, 1]. Returns False once the window has been passed (the
        decoding can stop)."""
        if self.done:
            return False
        if not self.rate:
            self._begin(rate, samples.shape[1])
        if samples.shape[1] != self.channels or rate != self.rate:
            return True  # a change in mid-file (rare, broken files): skip what doesn't fit
        first = self._read
        self._read += samples.shape[0]
        lo = max(0, int(round(self.start * rate)) - first)
        hi = samples.shape[0] if not self.end else min(samples.shape[0], int(round(self.end * rate)) - first)
        if hi <= 0:
            if self.end and self._read >= int(round(self.end * rate)):
                return False
            return True
        if lo < hi:
            self._write(samples[lo:hi])
        return not (self.end and self._read >= int(round(self.end * rate)))

    def _write(self, block):
        block = np.asarray(block, dtype=np.float32)
        if self.gain != 1.0:
            block = block * np.float32(self.gain)
        if self.processor is not None:
            block = self.processor.process(block)
        if self._skip:
            drop = min(self._skip, block.shape[0])
            block = block[drop:]
            self._skip -= drop
        if not block.shape[0]:
            return
        # 16-bit with triangular dither: the quiet end stays smooth rather than gritty
        noise = (self._rng.random(block.shape, dtype=np.float32) - self._rng.random(block.shape, dtype=np.float32))
        pcm = np.clip(np.round(block * 32767.0 + noise), -32768, 32767).astype("<i2")
        self._out.write(pcm.tobytes())
        self.frames += block.shape[0]

    def finish(self):
        """Completes the file (what the equalizer still holds flushed, the header written). Returns its
        details."""
        if self.done:
            return self.result()
        if self.processor is not None and self._delay and self.rate:
            self.gain, gain = 1.0, self.gain
            self._write(np.zeros((self._delay, self.channels), np.float32))
            self.gain = gain
        self.done = True
        self._out.seek(0)
        self._out.write(wav_header(self.rate or 44100, self.channels or 2, self.frames))
        self._out.close()
        return self.result()

    def abandon(self):
        if not self._out.closed:
            self._out.close()
        self.done = True

    def result(self):
        return {"rate": self.rate, "channels": self.channels, "frames": self.frames,
                "seconds": self.frames / self.rate if self.rate else 0.0}
