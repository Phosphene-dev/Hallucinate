"""DSD (SACD rips: .dsf and .dff files) played as high-resolution PCM.

FFmpeg decodes DSD to PCM at an eighth of its bit rate (DSD64's 2.8224 MHz becomes 352.8 kHz), but leaves in the
noise DSD pushes above the music: from about 25 kHz up it rises to well above the music's own level. Played like
that, it reaches the amplifier and the tweeters (inaudible, but not harmless), and an output that can't take
352.8 kHz resamples it with whatever filter it has. So it's converted here, in the player's own output: a steep
linear-phase low-pass (flat to 30 kHz, at least 120 dB down by 44.1 kHz, so nothing of the noise folds back into
the music) and decimation to the rate chosen in Settings → Sound (88.2, 176.4 or 352.8 kHz; 96/192/384 kHz for
the rarer DSD recorded on 48 kHz clocks). The music itself is left as it is: no gain, nothing else."""
import numpy as np

EXTS = (".dsf", ".dff")
RATES = (88200, 176400, 352800)  # what can be chosen (for the 44.1 kHz family; 48 kHz DSD scales to 96/192/384)
DEFAULT_RATE = 88200
PASS_HZ = 30000.0  # flat up to here: above any music, below where DSD's noise climbs
STOP_HZ = 44100.0
ATTENUATION_DB = 120.0
MIN_RATE = 176400  # what FFmpeg makes of DSD is at least this (DSD64 at 352.8 kHz); lower has been resampled already


def is_dsd(track):
    """Whether a queue entry is a DSD file (from its scanned codec, or its name)."""
    if not track:
        return False
    if str(track.get("codec") or "").upper() == "DSD":
        return True
    path = str(track.get("file") or track.get("path") or "").lower()
    return path.endswith(EXTS)


def output_rate(in_rate, chosen):
    """The PCM rate a DSD stream decoded at `in_rate` is converted to: the chosen one in its own family (44.1 or
    48 kHz multiples), never above what it came at, and always a whole fraction of it."""
    chosen = chosen if chosen in RATES else DEFAULT_RATE
    base = 44100 if in_rate % 44100 == 0 else 48000 if in_rate % 48000 == 0 else 0
    if not base:
        return in_rate  # (not a rate DSD comes at: filtered, not decimated)
    out = base * (chosen // 44100)
    while out > in_rate:
        out //= 2
    return out if in_rate % out == 0 else in_rate


def lowpass(rate, pass_hz=PASS_HZ, stop_hz=STOP_HZ, attenuation=ATTENUATION_DB):
    """A linear-phase (Kaiser-windowed) low-pass with unity gain where it passes."""
    width = 2 * np.pi * (stop_hz - pass_hz) / rate
    taps = int(np.ceil((attenuation - 8) / (2.285 * width))) | 1  # (odd: a whole-sample delay)
    beta = 0.1102 * (attenuation - 8.7)
    n = np.arange(taps) - (taps - 1) / 2
    cutoff = (pass_hz + stop_hz) / 2 / rate
    h = 2 * cutoff * np.sinc(2 * cutoff * n) * np.kaiser(taps, beta)
    return (h / h.sum()).astype(np.float32)


class Converter:
    """Streaming low-pass and decimation of the PCM FFmpeg makes of DSD: float32 (frames, channels) in, at
    `in_rate`; float32 at `out_rate` out. Only the output samples are computed (each one a dot product of the
    filter with the input around it), so it costs little even for DSD256."""

    def __init__(self, in_rate, channels, out_rate):
        if in_rate < MIN_RATE or out_rate <= 0 or in_rate % out_rate:  # (already brought down: nothing to do)
            raise ValueError(f"can't convert {in_rate} Hz to {out_rate} Hz")
        self.in_rate, self.channels, self.out_rate = in_rate, channels, out_rate
        self.factor = in_rate // out_rate
        self._h = lowpass(in_rate)[::-1].copy()
        self.reset()

    @property
    def delay(self):
        """Its delay, in input samples (half the filter)."""
        return (len(self._h) - 1) // 2

    def reset(self):
        """A seek or a new song: nothing carried over (starting from silence, as the song's own start would)."""
        self._buf = np.zeros((len(self._h) - 1 - self.delay, self.channels), dtype=np.float32)

    def process(self, samples):
        x = np.concatenate([self._buf, np.asarray(samples, dtype=np.float32).reshape(-1, self.channels)])
        taps = len(self._h)
        if len(x) < taps:
            self._buf = x
            return np.zeros((0, self.channels), dtype=np.float32)
        count = (len(x) - taps) // self.factor + 1
        windows = np.lib.stride_tricks.sliding_window_view(x, taps, axis=0)[::self.factor][:count]
        out = windows @ self._h  # (count, channels)
        self._buf = x[count * self.factor:]
        return np.ascontiguousarray(out, dtype=np.float32)
