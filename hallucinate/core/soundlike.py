"""How songs sound, measured from the audio itself, and finding songs that sound alike.

A minute or so from the middle of each song is decoded (in the analysis helper, at low priority) and boiled
down to a few numbers: its timbre (the shape of its spectrum, like MFCCs), how loud and how dynamic it is, how
busy and how steady its beat is, its tempo and its key. Nothing is sent anywhere; the numbers are kept in the
library (sound_features) and measured again only when the file changes.

"Sounds like this" then takes the songs closest to one song (or a few, for radio), with the choices from
Settings: keep the tempo close, keep keys that mix well (the Camelot wheel), leave out or limit the same
artist, and play them most alike first or as a smooth flow from one to the next."""
import math
import threading

import numpy as np

VERSION = 1  # measured again when this changes
RATE = 22050  # everything is measured at this rate, mono
N_FFT = 2048
HOP = 512
LENGTH_S = 60.0  # how much of a song is measured
START_S = 30.0  # from this far in (or the middle, for a short song)
MIN_S = 8.0  # less than this is too little to tell

# the parts of a song's numbers, and how much each counts when comparing (they add up to 1)
TIMBRE = slice(0, 28)
ENERGY = slice(28, 30)
RHYTHM = slice(30, 33)
DIMS = 33
WEIGHTS = np.concatenate([np.full(28, 0.5 / 28), np.full(2, 0.25 / 2), np.full(3, 0.25 / 3)]).astype(np.float32)

TEMPO_W = 0.5  # added to the distance for a tempo 10% away (half and double tempo count as the same)
KEY_W = 0.4  # added for keys that don't mix well
NO_KEY = -1

# Krumhansl–Kessler key profiles, from C
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NOTES = ("C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B")


# --- measuring ----------------------------------------------------------------------------------------------
def window(duration):
    """Where to start measuring a song `duration` seconds long (0 when not known: from the start)."""
    if not duration or duration <= 0:
        return 0.0
    return float(min(START_S, max(0.0, (duration - LENGTH_S) / 2)))


class Collector:
    """Gathers LENGTH_S of a song's audio from `start` seconds in, as it's decoded. add() says whether it
    wants more. A song shorter than expected still gives what it had: the last LENGTH_S before `start` is
    kept too, for that."""

    def __init__(self, start=0.0, length=LENGTH_S):
        self.start = max(0.0, float(start or 0.0))
        self.length = float(length)
        self.rate = 0
        self._seen = 0  # frames gone by
        self._before = []  # the stretch just before the start
        self._before_n = 0
        self._parts = []
        self._have = 0

    def add(self, samples, rate):
        if samples is None or not samples.size:
            return True
        mono = samples.mean(axis=1) if samples.ndim == 2 else samples
        mono = np.asarray(mono, dtype=np.float32)
        if not self.rate:
            self.rate = int(rate)
        elif int(rate) != self.rate:
            return False  # (the rate changed partway: what's here will do)
        want = int(self.length * self.rate)
        begin = int(self.start * self.rate)
        n = len(mono)
        if self._seen + n <= begin:
            self._before.append(mono)
            self._before_n += n
            while self._before and self._before_n - len(self._before[0]) >= want:
                self._before_n -= len(self._before.pop(0))
        else:
            cut = max(0, begin - self._seen)
            if cut:
                self._before.append(mono[:cut])
            self._parts.append(mono[cut:])
            self._have += n - cut
        self._seen += n
        return self._have < want

    def samples(self):
        """What was gathered, at RATE (or None when too little)."""
        if not self.rate:
            return None
        parts = self._parts if self._have >= MIN_S * self.rate else self._before + self._parts
        if not parts:
            return None
        x = np.concatenate(parts)[: int(self.length * self.rate)]
        if len(x) < MIN_S * self.rate:
            return None
        return resample(x, self.rate)

    def result(self):
        x = self.samples()
        return None if x is None else measure(x)


def resample(x, rate):
    """`x` (mono) at RATE: averaged over the step first, so the highs fold back less."""
    if rate == RATE:
        return x.astype(np.float32, copy=False)
    ratio = rate / RATE
    if ratio >= 1.5:
        k = int(round(ratio))
        x = np.convolve(x, np.full(k, 1.0 / k, dtype=np.float32), mode="same")
    n = int(len(x) / ratio)
    return np.interp(np.arange(n, dtype=np.float64) * ratio, np.arange(len(x)), x).astype(np.float32)


_banks = {}


def _filters():
    """(mel filter bank (bins, 40), pitch-class map (bins, 12), DCT matrix (40, 13), bin frequencies)."""
    if "f" in _banks:
        return _banks["f"]
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / RATE)

    def mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    edges = 700.0 * (10 ** (np.linspace(mel(40.0), mel(10_000.0), 42) / 2595.0) - 1.0)
    bank = np.zeros((len(freqs), 40), dtype=np.float32)
    for b in range(40):
        lo, mid, hi = edges[b], edges[b + 1], edges[b + 2]
        up = (freqs - lo) / (mid - lo)
        down = (hi - freqs) / (hi - mid)
        bank[:, b] = np.clip(np.minimum(up, down), 0.0, None)
    bank /= np.maximum(bank.sum(axis=0, keepdims=True), 1e-9)
    pitch = np.zeros((len(freqs), 12), dtype=np.float32)
    ok = (freqs >= 55.0) & (freqs <= 1760.0)
    classes = (np.round(12 * np.log2(freqs[ok] / 440.0)).astype(int) + 9) % 12
    pitch[np.nonzero(ok)[0], classes] = 1.0
    k = np.arange(40)
    dct = np.cos(np.pi / 40 * (k[:, None] + 0.5) * np.arange(13)[None, :]).astype(np.float32) * math.sqrt(2 / 40)
    _banks["f"] = (bank, pitch, dct, freqs.astype(np.float32))
    return _banks["f"]


def measure(x):
    """{"vec": float32[DIMS], "bpm", "key" (0–11 major from C, 12–23 minor, or NO_KEY), "keyStrength"} for
    mono audio at RATE, or None when it's silent or too short."""
    x = np.asarray(x, dtype=np.float32)
    if len(x) < MIN_S * RATE:
        return None
    level = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    if level < 1e-4:
        return None  # (silence)
    bank, pitch, dct, freqs = _filters()
    frames = np.lib.stride_tricks.sliding_window_view(x, N_FFT)[::HOP] * np.hanning(N_FFT).astype(np.float32)
    mag = np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32)
    power = mag ** 2
    loud = power.sum(axis=1) > 1e-8 * N_FFT  # (frames that aren't silent)
    if loud.sum() < 20:
        return None
    logmel = np.log10(power @ bank + 1e-10)
    mfcc = logmel @ dct
    spec = mag[loud]
    total = spec.sum(axis=1) + 1e-9
    centroid = (spec @ freqs) / total
    rolloff = freqs[np.argmax(np.cumsum(spec, axis=1) >= 0.85 * total[:, None], axis=1)]
    flatness = np.exp(np.mean(np.log(spec + 1e-9), axis=1)) / (spec.mean(axis=1) + 1e-9)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    db = db[db > db.max() - 60]  # (leave out near-silence: it says nothing of how dynamic the music is)

    flux = np.maximum(np.diff(logmel, axis=0), 0.0).sum(axis=1)
    bpm, pulse = _tempo(flux)
    key, strength = _key(np.log1p(100 * mag) @ pitch)
    vec = np.concatenate([
        mfcc[loud][:, 1:].mean(axis=0), mfcc[loud][:, 1:].std(axis=0),
        [np.log(centroid.mean() + 1), centroid.std() / (centroid.mean() + 1), np.log(rolloff.mean() + 1),
         flatness.mean()],
        [db.mean(), db.std()],
        [np.log1p(flux.mean()), pulse, math.log2(bpm) if bpm else 7.0],
    ]).astype(np.float32)
    return {"vec": vec, "bpm": round(float(bpm), 1), "key": int(key), "keyStrength": round(float(strength), 3)}


def _tempo(flux):
    """(beats per minute, how clear the beat is 0–1) from the onset strength, frame by frame."""
    fps = RATE / HOP
    if len(flux) < fps * 4:
        return 0.0, 0.0
    k = int(fps)
    e = flux - np.convolve(flux, np.full(k, 1.0 / k), mode="same")
    e = np.maximum(e, 0.0)
    e -= e.mean()
    n = len(e)
    spec = np.fft.rfft(e, 2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    if ac[0] <= 0:
        return 0.0, 0.0
    ac /= ac[0]
    lo, hi = int(fps * 60 / 210), int(fps * 60 / 50) + 1
    lags = np.arange(lo, min(hi, n - 1))
    if not len(lags):
        return 0.0, 0.0
    bpms = 60 * fps / lags
    prior = np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.9) ** 2)
    i = int(np.argmax(ac[lags] * prior))
    lag = float(lags[i])
    if 0 < i < len(lags) - 1:  # (between frames: a closer tempo)
        a, b, c = ac[lags[i] - 1], ac[lags[i]], ac[lags[i] + 1]
        d = a - 2 * b + c
        if d < 0:
            lag += 0.5 * (a - c) / d
    pulse = float(np.clip(ac[lags[i]], 0.0, 1.0))
    return 60 * fps / lag, pulse


def _key(chroma_frames):
    """(key 0–23, how sure 0–1) from pitch-class strength over time; NO_KEY when there's no telling."""
    c = chroma_frames.sum(axis=0)
    if c.sum() <= 0 or c.std() == 0:
        return NO_KEY, 0.0
    best, key = -2.0, NO_KEY
    for mode, profile in ((0, _MAJOR), (12, _MINOR)):
        for tonic in range(12):
            r = float(np.corrcoef(c, np.roll(profile, tonic))[0, 1])
            if r > best:
                best, key = r, mode + tonic
    return (key, best) if best >= 0.3 else (NO_KEY, max(best, 0.0))


def key_name(key):
    """"A minor", "E♭ major" (or "" when not known)."""
    if key is None or key < 0 or key > 23:
        return ""
    from .i18n import fill, translate

    text = translate("SoundsLike", "%1 minor") if key >= 12 else translate("SoundsLike", "%1 major")
    return fill(text, _NOTES[key % 12])


def camelot(key):
    """(number 1–12, "A" minor or "B" major) on the Camelot wheel, or None."""
    if key is None or key < 0 or key > 23:
        return None
    if key >= 12:
        return (7 * ((key - 12 + 3) % 12) + 7) % 12 + 1, "A"
    return (7 * key + 7) % 12 + 1, "B"


def keys_mix(a, b):
    """Whether keys `a` and `b` go well one after the other: the same, its relative major or minor, or a
    fifth up or down. Unknown keys go with anything."""
    ca, cb = camelot(a), camelot(b)
    if ca is None or cb is None:
        return True
    if ca[0] == cb[0]:
        return True
    return ca[1] == cb[1] and (ca[0] - cb[0]) % 12 in (1, 11)


def tempo_gap(a, b):
    """How far apart two tempos are, in octaves, with half and double tempo counting as the same (0 when
    either isn't known)."""
    if not a or not b or a <= 0 or b <= 0:
        return 0.0
    r = abs(math.log2(a / b))
    return min(r % 1.0, 1.0 - r % 1.0)


def pack(vec):
    return np.asarray(vec, dtype=np.float32).tobytes()


def unpack(blob):
    v = np.frombuffer(blob, dtype=np.float32) if blob else None
    return v if v is not None and v.size == DIMS else None


# --- the library's measurements -----------------------------------------------------------------------------
LOCAL = "t.path NOT GLOB '[a-z]*://*'"  # (music on this computer: not a server's or a stream)
SQL_TODO = f"""FROM tracks t LEFT JOIN sound_features f ON f.path = t.path
  WHERE (f.path IS NULL OR f.mtime != t.mtime OR f.version != ?) AND {LOCAL} AND t.duration >= ?"""


def counts(db):
    """(songs measured, songs that can be measured): music on this computer, long enough to tell."""
    total = db.conn.execute(f"SELECT COUNT(*) FROM tracks t WHERE {LOCAL} AND t.duration >= ?", (MIN_S,)).fetchone()[0]
    todo = db.conn.execute("SELECT COUNT(*) " + SQL_TODO, (VERSION, MIN_S)).fetchone()[0]
    return total - todo, total


def to_measure(db, limit=50, skip=()):
    """The next songs to measure: [{path, file, start, duration, mtime}], liked and most played first (so
    what you listen to most can be matched soonest), then newest."""
    rows = db.conn.execute(
        "SELECT t.path, t.file, t.cue_start, t.cue_end, t.duration, t.mtime, "
        "COALESCE((SELECT p.count FROM plays p WHERE p.path = t.path), 0) AS n, "
        "EXISTS(SELECT 1 FROM likes l WHERE l.path = t.path) AS liked "
        + SQL_TODO + " ORDER BY liked DESC, n DESC, t.added DESC LIMIT ?",
        (VERSION, MIN_S, limit + len(skip))).fetchall()
    out = []
    for r in rows:
        if r["path"] in skip:
            continue
        out.append({"path": r["path"], "file": r["file"] or r["path"], "offset": float(r["cue_start"] or 0.0),
                    "duration": float(r["duration"] or 0.0), "mtime": r["mtime"]})
    return out[:limit]


def store(db, rows):
    """Save measurements: [{path, mtime, result (from measure() or None when it couldn't be measured)}]."""
    db.conn.executemany(
        "INSERT OR REPLACE INTO sound_features(path, mtime, version, bpm, music_key, vec) VALUES (?,?,?,?,?,?)",
        [(r["path"], r["mtime"], VERSION, (r["result"] or {}).get("bpm", 0.0),
          (r["result"] or {}).get("key", NO_KEY), pack(r["result"]["vec"]) if r["result"] else None)
         for r in rows])
    db.conn.commit()


def forget(db):
    db.conn.execute("DELETE FROM sound_features")
    db.conn.commit()


def prune(db):
    """Leave out measurements of songs no longer in the library."""
    db.conn.execute("DELETE FROM sound_features WHERE path NOT IN (SELECT path FROM tracks)")
    db.conn.commit()


class Index:
    """Every measured song's numbers in memory, scaled alike, for finding the closest quickly. load() reads
    them (on a worker); it's read again when marked stale."""

    def __init__(self):
        self._lock = threading.Lock()
        self.stale = True
        self.paths = []
        self.where = {}
        self.z = np.zeros((0, DIMS), dtype=np.float32)
        self.bpm = np.zeros(0, dtype=np.float32)
        self.key = np.zeros(0, dtype=np.int16)
        self.artist = []
        self.title = []

    def __len__(self):
        return len(self.paths)

    def load(self, db, force=False):
        with self._lock:
            if not (self.stale or force):
                return self
            rows = db.conn.execute(
                "SELECT f.path, f.bpm, f.music_key, f.vec, t.s_artist, t.artist, t.s_title, t.title, t.bpm AS tag_bpm "
                "FROM sound_features f JOIN tracks t ON t.path = f.path WHERE f.vec IS NOT NULL AND f.version = ?",
                (VERSION,)).fetchall()
            from .db import fold

            vecs, paths, bpm, key, artist, title = [], [], [], [], [], []
            for r in rows:
                v = unpack(r["vec"])
                if v is None or not np.all(np.isfinite(v)):
                    continue
                vecs.append(v)
                paths.append(r["path"])
                bpm.append(float(r["tag_bpm"] or 0) or float(r["bpm"] or 0))  # (a tempo from the tags comes first)
                key.append(int(r["music_key"]) if r["music_key"] is not None else NO_KEY)
                artist.append(r["s_artist"] or fold(r["artist"] or ""))
                title.append(r["s_title"] or fold(r["title"] or ""))
            m = np.array(vecs, dtype=np.float32).reshape(-1, DIMS)
            if len(m):
                mean, std = m.mean(axis=0), m.std(axis=0)
                m = np.clip((m - mean) / np.where(std > 1e-6, std, 1.0), -4.0, 4.0)
            self.z, self.paths = m.astype(np.float32), paths
            self.where = {p: i for i, p in enumerate(paths)}
            self.bpm, self.key = np.array(bpm, dtype=np.float32), np.array(key, dtype=np.int16)
            self.artist, self.title = artist, title
            self.stale = False
            return self

    def has(self, path):
        return path in self.where

    def pick(self, seeds, size=40, order="alike", tempo=True, keys=False, same_artist=True, per_artist=3,
             exclude=(), left_out_artists=()):
        """Paths of up to `size` songs that sound like `seeds` (paths, the last counting most), not
        including the seeds or `exclude`. `order` "alike" puts the closest first; "flow" goes from one song to
        the one most like it next, starting from the seed."""
        with self._lock:
            idx = [self.where[p] for p in seeds if p in self.where]
            if not idx or len(self.paths) < 2:
                return []
            weights = np.arange(1, len(idx) + 1, dtype=np.float32)
            target = (self.z[idx] * weights[:, None]).sum(axis=0) / weights.sum()
            last = idx[-1]
            d = self._distance(target, last, tempo, keys)
            skip = set(exclude) | set(seeds)
            dupes = {(self.artist[i], self.title[i]) for i in idx}
            seed_artists = {self.artist[i] for i in idx}
            left_out = set(left_out_artists)
            pool = np.argsort(d)[: max(size * 8, 200)]
            chosen, per = [], {}
            cap = per_artist if per_artist and per_artist > 0 else size
            for i in pool:
                i = int(i)
                p, a = self.paths[i], self.artist[i]
                if p in skip or a in left_out or (not same_artist and a in seed_artists):
                    continue
                if (a, self.title[i]) in dupes or per.get(a, 0) >= cap:
                    continue
                dupes.add((a, self.title[i]))
                per[a] = per.get(a, 0) + 1
                chosen.append(i)
                if len(chosen) >= size:
                    break
            if order == "flow" and len(chosen) > 2:
                chosen = self._flow(last, chosen, target, tempo, keys)
            return [self.paths[i] for i in chosen]

    def _distance(self, target, at, tempo, keys, among=None):
        z = self.z if among is None else self.z[among]
        d = ((z - target) ** 2) @ WEIGHTS
        if tempo and self.bpm[at] > 0:
            bpm = self.bpm if among is None else self.bpm[among]
            r = np.abs(np.log2(np.where(bpm > 0, bpm, self.bpm[at]) / self.bpm[at]))
            gap = np.minimum(r % 1.0, 1.0 - r % 1.0)
            d = d + TEMPO_W * (gap / math.log2(1.1)) ** 2
        if keys and self.key[at] >= 0:
            ks = self.key if among is None else self.key[among]
            here = int(self.key[at])
            mix = np.fromiter((keys_mix(here, int(k)) for k in ks), dtype=bool, count=len(ks))
            d = d + KEY_W * (~mix)
        return d

    def _flow(self, start, chosen, target, tempo, keys):
        """`chosen` reordered so each song leads into the one most like it, staying near the seed."""
        left = list(chosen)
        out, at = [], start
        while left:
            arr = np.array(left)
            d = self._distance(self.z[at], at, tempo, keys, among=arr) + 0.5 * (((self.z[arr] - target) ** 2) @ WEIGHTS)
            j = int(np.argmin(d))
            at = left.pop(j)
            out.append(at)
        return out
