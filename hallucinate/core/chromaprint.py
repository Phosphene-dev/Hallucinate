"""Audio fingerprints as Chromaprint makes them (its default algorithm, the one AcoustID looks songs up by), in
numpy: no fpcalc to bundle. A song's first two minutes, mono at 11025 Hz, become a sequence of 32-bit
sub-fingerprints: the spectrum of each 4096-sample frame (a third apart) folded into 12 pitch classes, smoothed
over five frames, normalised, then 16 filters over the last 16 frames, each giving 2 bits.

Chromaprint is by Lukáš Lalinský (LGPL 2.1); this follows its published algorithm. Resampling differs from its
own, so a few bits can differ from fpcalc's; AcoustID matches on similarity, so that's fine (see the tests)."""
import base64

import numpy as np

SAMPLE_RATE = 11025
FRAME = 4096
HOP = FRAME - (FRAME - FRAME // 3)  # (an overlap of FRAME - FRAME / 3)
MIN_FREQ, MAX_FREQ = 28, 3520
LENGTH_S = 120  # how much of a song is fingerprinted, as fpcalc does by default
ALGORITHM = 1  # Chromaprint's "test2", its default
FILTER = (0.25, 0.75, 1.0, 0.75, 0.25)
# (filter type, first band, bands, frames), (quantizer thresholds)
CLASSIFIERS = (
    ((0, 4, 3, 15), (1.98215, 2.35817, 2.63523)),
    ((4, 4, 6, 15), (-1.03809, -0.651211, -0.282167)),
    ((1, 0, 4, 16), (-0.298702, 0.119262, 0.558497)),
    ((3, 8, 2, 12), (-0.105439, 0.0153946, 0.135898)),
    ((3, 4, 4, 8), (-0.142891, 0.0258736, 0.200632)),
    ((4, 0, 3, 5), (-0.826319, -0.590612, -0.368214)),
    ((1, 2, 2, 9), (-0.557409, -0.233035, 0.0534525)),
    ((2, 7, 3, 4), (-0.0646826, 0.00620476, 0.0784847)),
    ((2, 6, 2, 16), (-0.192387, -0.029699, 0.215855)),
    ((2, 1, 3, 2), (-0.0397818, -0.00568076, 0.0292026)),
    ((5, 10, 1, 15), (-0.53823, -0.369934, -0.190235)),
    ((3, 6, 2, 10), (-0.124877, 0.0296483, 0.139239)),
    ((2, 1, 1, 14), (-0.101475, 0.0225617, 0.231971)),
    ((3, 5, 6, 4), (-0.0799915, -0.00729616, 0.063262)),
    ((1, 9, 2, 12), (-0.272556, 0.019424, 0.302559)),
    ((3, 4, 2, 14), (-0.164292, -0.0321188, 0.0846339)),
)
WIDTH = max(c[0][3] for c in CLASSIFIERS)
GRAY = (0, 1, 3, 2)


def resample(mono, rate):
    """Mono float samples at `rate` → SAMPLE_RATE: a windowed-sinc low-pass below the new Nyquist, then
    linear interpolation."""
    mono = np.asarray(mono, dtype=np.float64)
    if rate == SAMPLE_RATE or not mono.size:
        return mono
    if rate > SAMPLE_RATE:
        cutoff = 0.9 * (SAMPLE_RATE / 2) / rate  # (cycles per input sample)
        taps = 129
        n = np.arange(taps) - (taps - 1) / 2
        kernel = 2 * cutoff * np.sinc(2 * cutoff * n) * np.blackman(taps)
        kernel /= kernel.sum()
        mono = np.convolve(mono, kernel, mode="same")
    count = int(len(mono) * SAMPLE_RATE / rate)
    return np.interp(np.arange(count) * (rate / SAMPLE_RATE), np.arange(len(mono)), mono)


def _notes():
    lo = max(1, int(round(FRAME * MIN_FREQ / SAMPLE_RATE)))
    hi = min(FRAME // 2, int(round(FRAME * MAX_FREQ / SAMPLE_RATE)))
    idx = np.arange(lo, hi)
    freq = idx * SAMPLE_RATE / FRAME
    octave = np.log2(freq / (440.0 / 16.0))
    notes = (12 * (octave - np.floor(octave))).astype(int)
    return lo, hi, notes


_LO, _HI, _NOTES = _notes()
_WINDOW = (0.54 - 0.46 * np.cos(2 * np.pi * np.arange(FRAME) / (FRAME - 1))) / 32767.0


def chroma(samples):
    """The normalised, smoothed 12-band chroma of mono samples at SAMPLE_RATE (in the range of 16-bit audio):
    (frames, 12)."""
    samples = np.asarray(samples, dtype=np.float64)
    if len(samples) < FRAME:
        return np.zeros((0, 12))
    starts = np.arange(0, len(samples) - FRAME + 1, HOP)
    frames = np.lib.stride_tricks.sliding_window_view(samples, FRAME)[starts] * _WINDOW
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    bands = np.zeros((len(frames), 12))
    for b in range(12):
        bands[:, b] = power[:, _LO:_HI][:, _NOTES == b].sum(axis=1)
    # smoothed over five frames
    k = len(FILTER)
    if len(bands) < k:
        return np.zeros((0, 12))
    smooth = sum(FILTER[j] * bands[j:len(bands) - k + 1 + j] for j in range(k))
    norm = np.sqrt((smooth ** 2).sum(axis=1))
    out = np.zeros_like(smooth)
    ok = norm >= 0.01
    out[ok] = smooth[ok] / norm[ok, None]
    return out


def _area(ii, x1, y1, x2, y2):
    """Sums of image[x1:x2, y1:y2] for every row offset at once (ii: integral image, padded)."""
    return ii[x2, y2] - ii[x1, y2] - ii[x2, y1] + ii[x1, y1]


def sub_fingerprints(features):
    """The 32-bit sub-fingerprints of chroma features (frames, 12)."""
    rows = len(features) - WIDTH + 1
    if rows <= 0:
        return np.zeros(0, dtype=np.uint32)
    ii = np.zeros((len(features) + 1, 13))
    ii[1:, 1:] = features.cumsum(axis=0).cumsum(axis=1)
    x = np.arange(rows)
    bits = np.zeros(rows, dtype=np.uint64)

    def area(dx1, y1, dx2, y2):
        return _area(ii, x + dx1, y1, x + dx2, y2)

    for (kind, y, h, w), (t0, t1, t2) in CLASSIFIERS:
        if kind == 0:
            a, b = area(0, y, w, y + h), 0.0
        elif kind == 1:
            h2 = h // 2
            a, b = area(0, y + h2, w, y + h), area(0, y, w, y + h2)
        elif kind == 2:
            w2 = w // 2
            a, b = area(w2, y, w, y + h), area(0, y, w2, y + h)
        elif kind == 3:
            w2, h2 = w // 2, h // 2
            a = area(0, y + h2, w2, y + h) + area(w2, y, w, y + h2)
            b = area(0, y, w2, y + h2) + area(w2, y + h2, w, y + h)
        elif kind == 4:
            h3 = h // 3
            a = area(0, y + h3, w, y + 2 * h3)
            b = area(0, y, w, y + h3) + area(0, y + 2 * h3, w, y + h)
        else:
            w3 = w // 3
            a = area(w3, y, 2 * w3, y + h)
            b = area(0, y, w3, y + h) + area(2 * w3, y, w, y + h)
        value = np.log1p(a) - np.log1p(b)
        q = np.where(value < t1, np.where(value < t0, 0, 1), np.where(value < t2, 2, 3))
        bits = (bits << np.uint64(2)) | np.array(GRAY, dtype=np.uint64)[q]
    return bits.astype(np.uint32)


def fingerprint(mono, rate):
    """A song's sub-fingerprints from mono float samples (-1..1) at `rate`: its first LENGTH_S seconds."""
    mono = np.asarray(mono, dtype=np.float64)[:int(rate * LENGTH_S)]
    return sub_fingerprints(chroma(resample(mono, rate) * 32767.0))


def _pack(values, width):
    """Little-endian bit packing of small ints, `width` bits each (Chromaprint's PackInt3/5Array)."""
    out, acc, nbits = bytearray(), 0, 0
    for v in values:
        acc |= (int(v) & ((1 << width) - 1)) << nbits
        nbits += width
        while nbits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            nbits -= 8
    if nbits:
        out.append(acc & 0xFF)
    return bytes(out)


def encode(fp, algorithm=ALGORITHM):
    """A fingerprint as AcoustID takes it: Chromaprint's compressed form, in URL-safe base64 without padding."""
    bits, prev = [], 0
    for x in (int(v) for v in fp):
        diff, prev = x ^ prev, x
        bit, last = 1, 0
        while diff:
            if diff & 1:
                bits.append(bit - last)
                last = bit
            diff >>= 1
            bit += 1
        bits.append(0)
    n = len(fp)
    head = bytes([algorithm & 0xFF, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])
    normal = _pack((min(b, 7) for b in bits), 3)
    extra = _pack((b - 7 for b in bits if b >= 7), 5)
    return base64.urlsafe_b64encode(head + normal + extra).decode("ascii").rstrip("=")


def decode(text):
    """The sub-fingerprints of an encoded fingerprint (for tests and comparing): (algorithm, [uint32])."""
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    algorithm, n = raw[0], int.from_bytes(raw[1:4], "big")
    data, pos = raw[4:], 0

    def unpack(width, count, start):
        vals, acc, nbits, i = [], 0, 0, start
        while len(vals) < count:
            while nbits < width:
                acc |= data[i] << nbits
                nbits += 8
                i += 1
            vals.append(acc & ((1 << width) - 1))
            acc >>= width
            nbits -= width
        return vals, i

    # the 3-bit stream holds one 0 per sub-fingerprint; read until n of them
    normal, acc, nbits, zeros = [], 0, 0, 0
    while zeros < n:
        while nbits < 3:
            acc |= data[pos] << nbits
            nbits += 8
            pos += 1
        v = acc & 7
        acc >>= 3
        nbits -= 3
        normal.append(v)
        zeros += v == 0
    extra, _ = unpack(5, sum(1 for v in normal if v == 7), pos)
    it = iter(extra)
    bits = [v + next(it) if v == 7 else v for v in normal]
    out, prev, x, last = [], 0, 0, 0
    for b in bits:
        if b == 0:
            prev ^= x
            out.append(prev)
            x, last = 0, 0
        else:
            last += b
            x |= 1 << (last - 1)
    return algorithm, out


def similarity(a, b):
    """The share of bits two fingerprints have in common over their common length (1.0: the same)."""
    n = min(len(a), len(b))
    if not n:
        return 0.0
    x = np.bitwise_xor(np.asarray(a[:n], dtype=np.uint32), np.asarray(b[:n], dtype=np.uint32))
    differing = np.unpackbits(x.view(np.uint8)).sum()
    return 1.0 - differing / (32.0 * n)


class Collector:
    """Gathers a song's first LENGTH_S seconds as it's decoded (see analysis.py): add() says False when it has
    enough; result() gives {"fingerprint", "duration"} (or None for silence or a too-short song)."""

    def __init__(self):
        self.parts, self.rate, self.frames = [], 0, 0

    def add(self, samples, rate):
        if self.rate and rate != self.rate:
            return False  # (a change of rate mid-song: what came before is enough)
        self.rate = rate
        mono = samples.mean(axis=1) if samples.ndim > 1 else samples
        self.parts.append(np.asarray(mono, dtype=np.float32))
        self.frames += len(mono)
        return self.frames < rate * LENGTH_S

    def result(self):
        if not self.parts or not self.rate:
            return None
        fp = fingerprint(np.concatenate(self.parts), self.rate)
        if not len(fp) or not np.any(fp):
            return None
        return {"fingerprint": encode(fp), "subs": len(fp)}
