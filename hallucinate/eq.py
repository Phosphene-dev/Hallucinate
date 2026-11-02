"""10-band equalizer.

Qt Multimedia has no audio effects, so when the equalizer is on the decoder output is tapped with a
QAudioBufferOutput (the QMediaPlayer's own output is muted), filtered with a linear-phase FIR in numpy, and
played through a QAudioSink. The DSP part is pure numpy and independent of Qt."""
import logging

try:
    import numpy as np
except ImportError:  # the equalizer is optional
    np = None

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudioBufferOutput, QAudioFormat, QAudioSink, QMediaDevices

logger = logging.getLogger(__name__)

BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
PRESETS = {
    "Flat": [0] * 10,
    "Bass boost": [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
    "Treble boost": [0, 0, 0, 0, 0, 1, 2, 4, 5, 6],
    "Vocal": [-2, -2, -1, 1, 3, 3, 2, 1, 0, -1],
    "Rock": [5, 4, 2, 0, -1, -1, 1, 3, 4, 5],
    "Pop": [-1, 1, 3, 4, 3, 0, -1, -1, 1, 2],
    "Jazz": [3, 2, 1, 2, -2, -2, 0, 1, 2, 3],
    "Classical": [4, 3, 3, 2, -1, -1, 0, 2, 3, 4],
    "Electronic": [5, 4, 1, 0, -2, 2, 1, 1, 4, 5],
    "Loudness": [6, 4, 0, 0, -1, 0, -1, 0, 4, 2],
}
# The presets' names as people read them (the keys above stay English: they're saved in settings and sent by the
# web remote). Listed for the translation catalogues; player.eqPresetLabel looks them up.
from PySide6.QtCore import QT_TRANSLATE_NOOP  # noqa: E402

_LABELS = [QT_TRANSLATE_NOOP("Equalizer", "Flat"), QT_TRANSLATE_NOOP("Equalizer", "Bass boost"),
           QT_TRANSLATE_NOOP("Equalizer", "Treble boost"), QT_TRANSLATE_NOOP("Equalizer", "Vocal"),
           QT_TRANSLATE_NOOP("Equalizer", "Rock"), QT_TRANSLATE_NOOP("Equalizer", "Pop"),
           QT_TRANSLATE_NOOP("Equalizer", "Jazz"), QT_TRANSLATE_NOOP("Equalizer", "Classical"),
           QT_TRANSLATE_NOOP("Equalizer", "Electronic"), QT_TRANSLATE_NOOP("Equalizer", "Loudness")]
MAX_GAIN_DB = 12.0
TAPS = 4097


def available():
    return np is not None


FILTER_TAIL = 8192  # samples of a parametric filter's response kept (its ringing in the deep bass dies out sooner)


def biquad(kind, fc, gain, q, rate):
    """(b, a) of an Equalizer APO / RBJ cookbook filter: "PK" peaking, "LSC" low shelf, "HSC" high shelf."""
    a_ = 10 ** (gain / 40)
    w0 = 2 * np.pi * min(fc, rate * 0.499) / rate
    alpha = np.sin(w0) / (2 * q)
    cos = np.cos(w0)
    if kind == "PK":
        b = (1 + alpha * a_, -2 * cos, 1 - alpha * a_)
        a = (1 + alpha / a_, -2 * cos, 1 - alpha / a_)
    elif kind == "LSC":
        s = 2 * np.sqrt(a_) * alpha
        b = (a_ * ((a_ + 1) - (a_ - 1) * cos + s), 2 * a_ * ((a_ - 1) - (a_ + 1) * cos),
             a_ * ((a_ + 1) - (a_ - 1) * cos - s))
        a = ((a_ + 1) + (a_ - 1) * cos + s, -2 * ((a_ - 1) + (a_ + 1) * cos), (a_ + 1) + (a_ - 1) * cos - s)
    elif kind == "HSC":
        s = 2 * np.sqrt(a_) * alpha
        b = (a_ * ((a_ + 1) + (a_ - 1) * cos + s), -2 * a_ * ((a_ - 1) + (a_ + 1) * cos),
             a_ * ((a_ + 1) + (a_ - 1) * cos - s))
        a = ((a_ + 1) - (a_ - 1) * cos + s, 2 * ((a_ - 1) - (a_ + 1) * cos), (a_ + 1) - (a_ - 1) * cos - s)
    else:
        return (1.0, 0.0, 0.0), (1.0, 0.0, 0.0)
    return tuple(x / a[0] for x in b), tuple(x / a[0] for x in a)


def parametric_response(filters, rate, n):
    """The exact complex response, at the n-point FFT's frequencies, of a chain of parametric filters (the ones
    switched on): what an IIR filter bank like Equalizer APO does, magnitude and phase."""
    w = 2 * np.pi * np.fft.rfftfreq(n, 1.0 / rate) / rate
    z1, z2 = np.exp(-1j * w), np.exp(-2j * w)
    h = np.ones_like(w, dtype=complex)
    for f in filters or []:
        if not f.get("on", True):
            continue
        b, a = biquad(f["type"], f["fc"], f["gain"], f["q"], rate)
        h *= (b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2)
    return h


def filters_curve(filters, points=160, rate=48000):
    """The filters' response as [[freq, dB], …], log-spaced 20 Hz – 20 kHz (for drawing)."""
    n = 1 << 15
    freqs = 20 * (1000 ** (np.arange(points) / (points - 1)))
    grid = np.fft.rfftfreq(n, 1.0 / rate)
    mag = 20 * np.log10(np.maximum(np.abs(parametric_response(filters, rate, n)), 1e-9))
    return [[round(float(f), 2), round(float(g), 3)] for f, g in zip(freqs, np.interp(freqs, grid, mag))]


def design_fir(gains_db, rate, taps=TAPS, curve=None, filters=None):
    """The equalizer's FIR: the band gains as a linear-phase filter (log-frequency interpolation), with a headphone
    correction under them.

    `curve` is a correction as [[freq, dB], ...] (a GraphicEQ profile), added to the bands' magnitude. `filters`
    is a parametric profile's filters ({"type", "fc", "gain", "q", "on"}): their exact response, phase and all,
    is applied as the causal filters they are, convolved onto the bands' filter, so the correction is the one
    its makers measured rather than an approximation of it.
    The whole response is lowered by its largest boost, so a boosted band (or the correction) can't push a
    loud recording past full scale and clip: boosting the bass turns everything else down instead."""
    n = 16384
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    logf = np.log10(np.maximum(freqs, 1.0))
    centers = np.log10(np.array(BANDS, dtype=float))
    gains = np.clip(np.array(gains_db, dtype=float), -MAX_GAIN_DB, MAX_GAIN_DB)
    mag_db = np.interp(logf, centers, gains)
    if curve:
        pts = np.array(curve, dtype=float)
        mag_db = mag_db + np.interp(logf, np.log10(pts[:, 0]), pts[:, 1])
    audible = (freqs >= 20) & (freqs <= 20000)
    active = [f for f in (filters or []) if f.get("on", True)]
    if active:
        # headroom from the combined response (the bands and the filters together)
        both = mag_db + 20 * np.log10(np.maximum(np.abs(parametric_response(active, rate, n)), 1e-9))
        mag_db -= max(0.0, float(both[audible].max()))
    else:
        mag_db -= max(0.0, float(mag_db[audible].max()))
    mag = 10 ** (mag_db / 20)
    impulse = np.fft.fftshift(np.fft.irfft(mag, n))
    mid = n // 2
    h = impulse[mid - taps // 2: mid + taps // 2 + 1] * np.hanning(taps)
    if active:
        # the filters' own impulse response (causal, as an IIR filter's is), its far tail faded out
        big = 1 << 17
        tail = np.fft.irfft(parametric_response(active, rate, big), big)[:FILTER_TAIL]
        fade = FILTER_TAIL // 8
        tail[-fade:] *= np.hanning(2 * fade)[fade:]
        h = np.convolve(h, tail)
    return h.astype(np.float32)


# Crossfeed for headphones: each ear also hears the other channel, a little later and with its highs rolled off,
# as it would from speakers. (cut-off Hz, feed level dB), after Linkwitz and Meier's designs.
CROSSFEED = {"light": (650, -9.5), "medium": (700, -6.0), "strong": (700, -4.5)}
CROSSFEED_DELAY_S = 0.0003  # about the extra path to the far ear


class Crossfeed:
    """Streaming crossfeed for stereo float frames: out = (direct + level * lowpass(delay(other))) / (1 + level)."""

    def __init__(self, preset="medium", rate=44100):
        self.preset = preset
        self.rate = rate
        self._kernel = None
        self._tail = None

    def configure(self, preset, rate):
        if (preset, rate) != (self.preset, self.rate):
            self.preset, self.rate = preset, rate
            self._kernel = None
            self._tail = None

    def reset(self):
        self._tail = None

    @property
    def level(self):
        return 10 ** (CROSSFEED.get(self.preset, CROSSFEED["medium"])[1] / 20)

    def _build(self):
        cutoff = CROSSFEED.get(self.preset, CROSSFEED["medium"])[0]
        a = float(np.exp(-2 * np.pi * cutoff / self.rate))  # one-pole low-pass as a decaying impulse
        delay = int(round(CROSSFEED_DELAY_S * self.rate))
        length = delay + max(8, int(np.ceil(np.log(1e-4) / np.log(a))))
        k = np.zeros(length, dtype=np.float32)
        n = np.arange(length - delay)
        k[delay:] = (1 - a) * a ** n
        self._kernel = k

    def process(self, samples):
        """samples: float32 (frames, 2) -> crossfed (frames, 2)."""
        if samples.ndim != 2 or samples.shape[1] != 2 or samples.shape[0] == 0:
            return samples
        if self._kernel is None:
            self._build()
        k = self._kernel
        if self._tail is None:
            self._tail = np.zeros((len(k) - 1, 2), dtype=np.float32)
        x = np.concatenate([self._tail, samples], axis=0)
        self._tail = x[-(len(k) - 1):].copy()
        frames = samples.shape[0]
        left = np.convolve(x[:, 1], k, mode="valid")[-frames:]   # right channel, heard on the left
        right = np.convolve(x[:, 0], k, mode="valid")[-frames:]
        g = self.level
        out = np.empty_like(samples)
        out[:, 0] = (samples[:, 0] + g * left) / (1 + g)
        out[:, 1] = (samples[:, 1] + g * right) / (1 + g)
        return out


class EqProcessor:
    """Streaming overlap-save FIR filter for interleaved PCM, then optional crossfeed."""

    def __init__(self):
        self.gains = [0.0] * 10
        self.eq_on = True
        self.crossfeed = None  # a Crossfeed, or None
        self.curve = None
        self.filters = None
        self.rate = 44100
        self.channels = 2
        self._h = None
        self._tail = None
        self._cache = {}

    @property
    def eq_flat(self):
        return not self.eq_on or (not self.curve and not any(f.get("on", True) for f in self.filters or [])
                                   and not any(abs(g) > 0.01 for g in self.gains))

    @property
    def flat(self):
        return self.eq_flat and self.crossfeed is None

    def set_crossfeed(self, preset):
        """"" or "off" turns it off; otherwise one of CROSSFEED."""
        if preset in CROSSFEED:
            if self.crossfeed is None:
                self.crossfeed = Crossfeed(preset, self.rate)
            else:
                self.crossfeed.configure(preset, self.rate)
        else:
            self.crossfeed = None

    def configure(self, rate, channels):
        if (rate, channels) != (self.rate, self.channels):
            self.rate, self.channels = rate, channels
            self._h = None
        if self.crossfeed is not None:
            self.crossfeed.configure(self.crossfeed.preset, rate)
        self.reset()

    def set_gains(self, gains):
        self.gains = [float(g) for g in gains]
        self._h = None

    def set_curve(self, curve):
        self.curve = curve or None
        self._h = None

    def set_filters(self, filters):
        """A parametric headphone profile's filters (see design_fir), or None."""
        self.filters = [dict(f) for f in filters] if filters else None
        self._h = None

    def reset(self):
        self._tail = None
        if self.crossfeed is not None:
            self.crossfeed.reset()

    def _kernel(self, nfft):
        if self._h is None:
            self._h = design_fir(self.gains, self.rate, curve=self.curve, filters=self.filters)
            self._cache = {}
        spec = self._cache.get(nfft)
        if spec is None:
            spec = np.fft.rfft(self._h, nfft)
            self._cache[nfft] = spec
        return spec

    def process(self, samples):
        """samples: float32 array (frames, channels) in [-1, 1] -> filtered array of the same shape."""
        out = samples if self.eq_flat else self._equalize(samples)
        return self.crossfeed.process(out) if self.crossfeed is not None else out

    def _equalize(self, samples):
        frames = samples.shape[0]
        if frames == 0:
            return samples
        if self._h is None:
            self._kernel(1 << int(np.ceil(np.log2(TAPS))))  # (designs it: its length sets the overlap)
        taps = len(self._h)
        overlap = taps - 1
        if self._tail is None or self._tail.shape[0] != overlap or self._tail.shape[1] != samples.shape[1]:
            self._tail = np.zeros((overlap, samples.shape[1]), dtype=np.float32)
        x = np.concatenate([self._tail, samples], axis=0)
        self._tail = x[-overlap:].copy()
        nfft = 1 << int(np.ceil(np.log2(x.shape[0] + taps)))
        spec = self._kernel(nfft)
        y = np.fft.irfft(np.fft.rfft(x, nfft, axis=0) * spec[:, None], nfft, axis=0)
        # Output is delayed by the filter's group delay (TAPS // 2 samples), a constant ~46 ms.
        return y[overlap: overlap + frames].astype(np.float32)


_FORMATS = {
    QAudioFormat.SampleFormat.UInt8: ("u1", lambda a: (a.astype(np.float32) - 128) / 128),
    QAudioFormat.SampleFormat.Int16: ("<i2", lambda a: a.astype(np.float32) / 32768),
    QAudioFormat.SampleFormat.Int32: ("<i4", lambda a: a.astype(np.float32) / 2147483648),
    QAudioFormat.SampleFormat.Float: ("<f4", lambda a: a.astype(np.float32)),
}


class EqTap(QObject):
    """Per-voice tap: receives decoded buffers, filters them and plays them on its own QAudioSink.

    If its sink can't be opened (or the filtering fails) it gives up until the next reset (a seek or a new
    source) and says so with `failedChanged`, so the player can play the sound directly meanwhile instead of
    keeping its own output muted for a tap that plays nothing."""

    failedChanged = Signal(str)  # why it gave up; "" when it's trying again

    def __init__(self, processor, parent=None):
        super().__init__(parent)
        self.output = QAudioBufferOutput(self)
        self.output.audioBufferReceived.connect(self._on_buffer)
        self.processor = processor
        self.volume = 1.0
        self.failed = False
        self.device = None  # QAudioDevice; None plays on the system default
        self._sink = None
        self._io = None
        self._fmt = None
        self._pending = bytearray()
        self._suspended = True
        self._timer = QTimer(self)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._drain)

    def _open(self, rate, channels):
        fmt = QAudioFormat()
        fmt.setSampleRate(rate)
        fmt.setChannelCount(channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        device = self.device
        if device is None or device.isNull():
            device = QMediaDevices.defaultAudioOutput()
        if device.isNull() or not device.isFormatSupported(fmt):
            raise RuntimeError("no usable audio output device")
        self._close()
        self._sink = QAudioSink(device, fmt, self)
        self._sink.setBufferSize(rate * channels * 2 // 4)  # ~250 ms
        self._sink.setVolume(self.volume)
        self._io = self._sink.start()
        self._fmt = (rate, channels)
        self.processor.configure(rate, channels)
        if self._suspended:
            self._sink.suspend()
        self._timer.start()

    def _close(self):
        self._timer.stop()
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        self._sink = self._io = None
        self._pending.clear()

    def _on_buffer(self, buf):
        fmt = buf.format()
        if not buf.isValid() or fmt.channelCount() <= 0 or self.failed:
            return
        spec = _FORMATS.get(fmt.sampleFormat())
        if spec is None:
            return
        try:
            if self._fmt != (fmt.sampleRate(), fmt.channelCount()) or self._sink is None:
                self._open(fmt.sampleRate(), fmt.channelCount())
            raw = np.frombuffer(buf.constData(), dtype=spec[0], count=buf.sampleCount())
            data = spec[1](raw).reshape(-1, fmt.channelCount())
            if not self.processor.flat:
                data = self.processor.process(data)
            out = (np.clip(data, -1.0, 1.0) * 32767).astype("<i2")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Equalizer disabled: %s", exc)
            self.failed = True
            self._close()
            self._fmt = None  # opened afresh when it tries again
            self.failedChanged.emit(str(exc) or type(exc).__name__)
            return
        self._pending += out.tobytes()
        self._drain()

    def _drain(self):
        if self._io is None or not self._pending:
            return
        free = self._sink.bytesFree()
        if free > 0:
            n = self._io.write(bytes(self._pending[:free]))
            if n > 0:
                del self._pending[:n]

    def setDevice(self, device, force=False):
        """Switch output device; the sink is reopened on the next decoded buffer."""
        if not force and self.device is not None and device is not None and self.device == device:
            return
        self.device = device
        if self._sink is not None:
            self._close()
            self._fmt = None

    def setVolume(self, v):
        self.volume = v
        if self._sink is not None:
            self._sink.setVolume(v)

    def setRunning(self, running):
        self._suspended = not running
        if self._sink is None:
            return
        if running:
            self._sink.resume()
        else:
            self._sink.suspend()

    def reset(self):
        """Drop buffered audio (seek, new source). A tap that gave up tries again from here."""
        self._pending.clear()
        if self.failed:
            self.failed = False
            self.failedChanged.emit("")
        self.processor.reset()
        if self._sink is not None:
            self._sink.reset()
            self._io = self._sink.start()
            if self._suspended:
                self._sink.suspend()

    def close(self):
        self._close()
        self._fmt = None
