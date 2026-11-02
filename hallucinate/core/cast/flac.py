"""A small FLAC encoder for Hallucinate's sound on cast devices: lossless like the WAV it replaces where the device
takes FLAC, at about half the size, and 24 bits deep, so what the equalizer and ReplayGain made isn't cut down to
16 bits on the way (no dither needed).

Plain numpy, written to be simple and correct rather than squeeze out the last few percent: FLAC's fixed
predictors (orders 0 to 4, the best one per channel and block), partitioned Rice coding of what's left with the
partition count and Rice parameters chosen per block, and for stereo the cheaper of left/right or mid/side. Every
frame carries its CRCs; the STREAMINFO block (rate, channels, length, frame sizes) is written once the length is
known, as the WAV header was. No MD5 of the audio (FLAC allows leaving it out)."""
import struct

import numpy as np

BLOCK = 4096
MAX_PARTITION_ORDER = 6


def _crc_table(poly, width):
    top = 1 << (width - 1)
    mask = (1 << width) - 1
    table = []
    for byte in range(256):
        crc = byte << (width - 8)
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & mask if crc & top else (crc << 1) & mask
        table.append(crc)
    return table


_CRC8 = _crc_table(0x07, 8)
_CRC16 = _crc_table(0x8005, 16)


def crc8(data):
    crc = 0
    for b in data:
        crc = _CRC8[crc ^ b]
    return crc


def _crc16_words():
    """CRC-16 of every two-byte word from a zero register: with a 16-bit register, two bytes at a time is
    just crc = table[crc ^ word]. The same table moves a CRC on past two zero bytes."""
    table = np.array(_CRC16, dtype=np.uint16)
    word = np.arange(1 << 16, dtype=np.uint32)
    after_hi = table[word >> 8].astype(np.uint32)
    return (((after_hi << 8) & 0xFFFF) ^ table[(after_hi >> 8) ^ (word & 0xFF)]).astype(np.uint16)


_SHIFTS = []  # _SHIFTS[k][crc]: crc moved on past 2 * 2**k zero bytes


def crc16(data):
    """CRC-16 of a whole frame, all at once: each two-byte word's own CRC, then neighbours combined in pairs
    (CRC(a + b) = CRC(a) moved on past len(b) zero bytes, XOR CRC(b)). Zero bytes in front change nothing, so
    the frame is padded to a power of two first."""
    if not _SHIFTS:
        _SHIFTS.append(_crc16_words())
        for _ in range(20):
            _SHIFTS.append(_SHIFTS[-1][_SHIFTS[-1]])
    data = bytes(data)
    size = 2
    while size < len(data):
        size *= 2
    crc = _SHIFTS[0][np.frombuffer(b"\0" * (size - len(data)) + data, dtype=">u2")]
    level = 0
    while crc.size > 1:
        crc = _SHIFTS[level][crc[0::2]] ^ crc[1::2]
        level += 1
    return int(crc[0])


class Bits:
    """Big-endian bit writer: fields go in as arrays of 0/1 and are packed once per frame."""

    def __init__(self):
        self.parts = []
        self.length = 0

    def put(self, value, n):
        if n:
            self.parts.append(((int(value) >> np.arange(n - 1, -1, -1, dtype=np.int64)) & 1).astype(np.uint8))
            self.length += n

    def put_signed(self, value, n):
        self.put(int(value) & ((1 << n) - 1), n)

    def put_array(self, bits):
        self.parts.append(bits)
        self.length += bits.size

    def align(self):
        self.put(0, (-self.length) % 8)

    def tobytes(self):
        return np.packbits(np.concatenate(self.parts) if self.parts else np.zeros(0, np.uint8)).tobytes()


def _zigzag(r):
    return (r << 1) ^ (r >> 63)


def _rice_bits(u, k):
    """The Rice codes (parameter k) of non-negative ints u, as an array of bits."""
    q = u >> k
    lengths = q + 1 + k
    starts = np.concatenate([[0], np.cumsum(lengths)[:-1]])
    bits = np.zeros(int(lengths.sum()), dtype=np.uint8)
    bits[starts + q] = 1
    for j in range(k):
        bits[starts + q + 1 + j] = (u >> (k - 1 - j)) & 1
    return bits


_KS = np.arange(31, dtype=np.int64)


def _residual(bits, residual, order, block):
    """Partitioned Rice coding of a subframe's residual: every partition order and Rice parameter is costed at
    once (the finest partitions' costs for each parameter, summed up into the coarser ones), the cheapest kept."""
    u = _zigzag(residual.astype(np.int64))
    finest = 0
    while finest < MAX_PARTITION_ORDER and block % (2 << finest) == 0 and (block >> (finest + 1)) > order:
        finest += 1
    padded = np.concatenate([np.zeros(order, np.int64), u])  # (the warm-up's place: costs nothing below)
    shifted = (padded[None, :] >> _KS[:, None]).reshape(_KS.size, 1 << finest, -1).sum(axis=2)  # (k, partition)
    best = None
    for p in range(finest + 1):
        sums = shifted.reshape(_KS.size, 1 << p, -1).sum(axis=2)
        counts = np.full(1 << p, block >> p, dtype=np.int64)
        counts[0] -= order
        costs = sums + counts[None, :] * (_KS[:, None] + 1)
        params = costs.argmin(axis=0)
        total = int(costs[params, np.arange(1 << p)].sum()) + 5 * (1 << p)
        if best is None or total < best[0]:
            best = (total, p, params, counts)
    _total, p, params, counts = best
    wide = int(params.max()) > 14
    bits.put(1 if wide else 0, 2)  # Rice parameters in 4 bits, or 5
    bits.put(p, 4)
    start = 0
    for k, count in zip(params.tolist(), counts.tolist()):
        bits.put(k, 5 if wide else 4)
        if count:
            bits.put_array(_rice_bits(u[start:start + count], k))
        start += count


def _fixed_residuals(x):
    """Residuals of FLAC's fixed predictors of order 0 to 4 (each order's own warm-up left out)."""
    out = [x]
    for _ in range(4):
        out.append(np.diff(out[-1]))
    return out


def _subframe(bits, x, bps):
    """One channel's samples (int64) as a subframe: constant, or the best fixed predictor."""
    n = x.size
    bits.put(0, 1)
    if n and (x == x[0]).all():
        bits.put(0b000000, 6)
        bits.put(0, 1)
        bits.put_signed(x[0], bps)
        return
    residuals = _fixed_residuals(x)
    orders = [o for o in range(5) if n > o]
    order = min(orders, key=lambda o: int(np.abs(residuals[o]).sum()))
    bits.put(0b001000 | order, 6)
    bits.put(0, 1)  # no wasted bits
    for s in x[:order]:
        bits.put_signed(s, bps)
    _residual(bits, residuals[order], order, n)


def _utf8_number(n):
    if n < 0x80:
        return bytes([n])
    out = []
    while True:
        out.insert(0, 0x80 | (n & 0x3F))
        n >>= 6
        limit = 0x3F >> len(out)
        if n <= limit:
            out.insert(0, ((0xFF << (7 - len(out))) & 0xFF) | n)  # (110xxxxx for two bytes, 1110xxxx for three…)
            return bytes(out)


class Writer:
    """Writes int samples (frames, channels) as FLAC: add() any number of frames, finish() completes the file."""

    def __init__(self, out, rate, channels, bits_per_sample=24):
        if not 1 <= channels <= 8 or bits_per_sample not in (16, 24) or not 1 <= rate < 1 << 20:
            raise ValueError("unsupported FLAC format")
        self.rate, self.channels, self.bps = int(rate), int(channels), bits_per_sample
        self._out = open(out, "wb") if isinstance(out, (str, bytes)) or hasattr(out, "__fspath__") else out
        self._out.write(b"fLaC" + self._streaminfo(0, 0, 0))
        self._pending = np.zeros((0, self.channels), dtype=np.int64)
        self.frames = 0
        self._number = 0
        self._min_frame = self._max_frame = 0

    def _streaminfo(self, total, min_frame, max_frame):
        info = (struct.pack(">HH", BLOCK, BLOCK) + min_frame.to_bytes(3, "big") + max_frame.to_bytes(3, "big")
                + ((self.rate << 44) | ((self.channels - 1) << 41) | ((self.bps - 1) << 36) | total).to_bytes(8, "big")
                + b"\0" * 16)
        return bytes([0x80, 0, 0, 34]) + info  # the last metadata block, STREAMINFO, 34 bytes

    def add(self, samples):
        samples = np.asarray(samples, dtype=np.int64).reshape(-1, self.channels)
        self._pending = np.concatenate([self._pending, samples]) if self._pending.size else samples
        while self._pending.shape[0] >= BLOCK:
            self._frame(self._pending[:BLOCK])
            self._pending = self._pending[BLOCK:]

    def _frame(self, block):
        n = block.shape[0]
        head = Bits()
        head.put(0b11111111111110, 14)
        head.put(0, 1)
        head.put(0, 1)  # fixed block size
        head.put(0b1100 if n == BLOCK else 0b0111, 4)  # 4096, or (the last one) given below
        head.put(0b0000, 4)  # the rate: STREAMINFO's
        assignment = self.channels - 1
        chans = [block[:, c] for c in range(self.channels)]
        widths = [self.bps] * self.channels
        if self.channels == 2:  # mid/side when it's cheaper (most music: the channels are much alike)
            left, right = chans
            side = left - right
            mid = (left + right) >> 1
            cost = [int(np.abs(np.diff(c)).sum()) for c in (left, right, mid, side)]
            if cost[2] + cost[3] < cost[0] + cost[1]:
                assignment, chans, widths = 0b1010, [mid, side], [self.bps, self.bps + 1]
        head.put(assignment, 4)
        head.put(0b100 if self.bps == 16 else 0b110, 3)
        head.put(0, 1)
        header = head.tobytes() + _utf8_number(self._number)
        if n != BLOCK:
            header += struct.pack(">H", n - 1)
        header += bytes([crc8(header)])
        body = Bits()
        for c, w in zip(chans, widths):
            _subframe(body, c, w)
        body.align()
        frame = header + body.tobytes()
        frame += struct.pack(">H", crc16(frame))
        self._out.write(frame)
        self._number += 1
        self.frames += n
        size = len(frame)
        self._min_frame = size if not self._min_frame else min(self._min_frame, size)
        self._max_frame = max(self._max_frame, size)

    def finish(self):
        if self._pending.shape[0]:
            self._frame(self._pending)
            self._pending = self._pending[:0]
        self._out.seek(4)
        self._out.write(self._streaminfo(self.frames, self._min_frame, self._max_frame))
        self._out.close()
