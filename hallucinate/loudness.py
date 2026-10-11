"""Loudness for ReplayGain: ITU-R BS.1770 / EBU R128 integrated loudness and sample peak, with numpy.

The K-weighting filter is applied in the frequency domain to each 100 ms chunk (Parseval: a chunk's filtered
mean square is its spectrum weighted by |H|^2), which avoids a per-sample IIR loop in Python and stays within a
few tenths of a dB of a time-domain filter. Gating follows BS.1770-4: 400 ms blocks with 75 % overlap, an
absolute gate at -70 LUFS and a relative gate 10 LU below the ungated loudness. ReplayGain 2.0 aims at -18 LUFS.

Mono files count as dual mono (they play from both speakers), as most ReplayGain scanners do."""
import math

import numpy as np

REFERENCE_LUFS = -18.0
ABSOLUTE_GATE = -70.0
CHUNK_SECONDS = 0.1  # four chunks make one 400 ms gating block


def _biquad_power(b, a, w):
    """|H(e^jw)|^2 of a biquad at angular frequencies w (radians per sample)."""
    z1, z2 = np.exp(-1j * w), np.exp(-2j * w)
    h = (b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2)
    return np.abs(h) ** 2


def k_weighting(freqs, rate):
    """Power response of the BS.1770 K-weighting filter (high shelf, then high pass) at `freqs` Hz.

    Coefficients follow libebur128's derivation, which reproduces the standard's 48 kHz values exactly and
    adapts to other sample rates."""
    w = 2 * np.pi * np.asarray(freqs, dtype=np.float64) / rate
    # Stage 1: high shelf, about +4 dB above 2 kHz (the head's acoustic effect)
    f0, gain, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / rate)
    vh = 10 ** (gain / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf_b = ((vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0)
    shelf_a = (1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)
    # Stage 2: high pass at about 38 Hz (RLB weighting)
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / rate)
    a0 = 1 + k / q + k * k
    hp_b = (1.0, -2.0, 1.0)
    hp_a = (1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)
    return _biquad_power(shelf_b, shelf_a, w) * _biquad_power(hp_b, hp_a, w)


class Meter:
    """Feed it audio as it decodes; it keeps only per-chunk powers and the peak."""

    def __init__(self):
        self.rate = 0
        self.channels = 0
        self._pending = None
        self._weights = None
        self.powers = []  # K-weighted power (sum over channels) per 100 ms chunk
        self.peak = 0.0

    def add(self, samples, rate):
        """`samples` is float (frames, channels) in -1..1."""
        samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim == 1:
            samples = samples[:, None]
        if samples.size == 0:
            return
        if rate != self.rate or samples.shape[1] != self.channels:
            self.rate, self.channels = rate, samples.shape[1]
            self._pending = None
            n = int(round(rate * CHUNK_SECONDS))
            self._weights = k_weighting(np.fft.rfftfreq(n, 1 / rate), rate)
        self.peak = max(self.peak, float(np.abs(samples).max()))
        data = samples if self._pending is None else np.concatenate([self._pending, samples])
        n = int(round(self.rate * CHUNK_SECONDS))
        full = len(data) // n
        if full:
            chunks = data[: full * n].reshape(full, n, self.channels)
            spectrum = np.abs(np.fft.rfft(chunks, axis=1)) ** 2  # (chunks, bins, channels)
            weights = self._weights[None, :, None]
            # Parseval for a real signal through rfft: double every bin but DC (and Nyquist when n is even)
            scale = np.full(spectrum.shape[1], 2.0)
            scale[0] = 1.0
            if n % 2 == 0:
                scale[-1] = 1.0
            mean_square = (spectrum * weights * scale[None, :, None]).sum(axis=1) / (n * n)  # (chunks, channels)
            power = mean_square.sum(axis=1) * (2.0 if self.channels == 1 else 1.0)
            self.powers.extend(power.tolist())
        self._pending = data[full * n:]


def _blocks(powers):
    """Mean power of each 400 ms block (four chunks, stepping one chunk)."""
    p = np.asarray(powers, dtype=np.float64)
    if len(p) < 4:
        return p[:1] if len(p) else p
    return np.convolve(p, np.ones(4) / 4, mode="valid")


def _lufs(power):
    return -0.691 + 10 * math.log10(power) if power > 0 else float("-inf")


def integrated(blocks):
    """Gated integrated loudness (LUFS) of 400 ms block powers, or None when everything is below the gate."""
    blocks = np.asarray(blocks, dtype=np.float64)
    if blocks.size == 0:
        return None
    loud = -0.691 + 10 * np.log10(np.maximum(blocks, 1e-20))
    kept = blocks[loud > ABSOLUTE_GATE]
    if kept.size == 0:
        return None
    relative = _lufs(float(kept.mean())) - 10
    kept = blocks[(loud > ABSOLUTE_GATE) & (loud > relative)]
    return _lufs(float(kept.mean())) if kept.size else None


def track_result(meter):
    """{"loudness", "gain", "peak", "blocks"} for one track (blocks are kept for the album), or None if silent."""
    blocks = _blocks(meter.powers)
    loudness = integrated(blocks)
    if loudness is None:
        return None
    return {"loudness": loudness, "gain": REFERENCE_LUFS - loudness, "peak": meter.peak, "blocks": blocks}


def album_gain(results):
    """Album gain from the tracks' blocks taken together (BS.1770 over the whole album), or None."""
    blocks = [r["blocks"] for r in results if r is not None and len(r["blocks"])]
    if not blocks:
        return None
    loudness = integrated(np.concatenate(blocks))
    return None if loudness is None else REFERENCE_LUFS - loudness
