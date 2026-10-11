"""Headphone correction from AutoEQ (https://github.com/jaakkopasanen/AutoEq).

AutoEQ publishes, for thousands of headphones, the EQ that brings them to a neutral target. Its files come in
two forms, both supported: "ParametricEQ.txt" (Equalizer APO filters: peaking and shelving biquads plus a
preamp) and "GraphicEQ.txt" (a frequency/gain curve). Either becomes a smooth gain curve that the equalizer
adds under the 10-band settings.

The search downloads AutoEQ's index once (cached for a month) and each chosen profile when picked; nothing is
sent but the requests for those files."""
import json
import logging
import math
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

logger = logging.getLogger(__name__)

RAW = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/results/"
INDEX_URL = RAW + "INDEX.md"
INDEX_MAX_AGE = 30 * 86_400
CURVE_POINTS = 160  # log-spaced 20 Hz – 20 kHz


def curve_freqs(points=CURVE_POINTS):
    return [20 * (1000 ** (i / (points - 1))) for i in range(points)]


def _biquad_db(kind, fc, gain, q, freqs, rate=48000):
    """Magnitude (dB) of an Equalizer APO / RBJ cookbook filter at `freqs`."""
    a_ = 10 ** (gain / 40)
    w0 = 2 * math.pi * fc / rate
    alpha = math.sin(w0) / (2 * q)
    cos = math.cos(w0)
    if kind == "PK":
        b = (1 + alpha * a_, -2 * cos, 1 - alpha * a_)
        a = (1 + alpha / a_, -2 * cos, 1 - alpha / a_)
    elif kind == "LSC":
        s = 2 * math.sqrt(a_) * alpha
        b = (a_ * ((a_ + 1) - (a_ - 1) * cos + s), 2 * a_ * ((a_ - 1) - (a_ + 1) * cos), a_ * ((a_ + 1) - (a_ - 1) * cos - s))
        a = ((a_ + 1) + (a_ - 1) * cos + s, -2 * ((a_ - 1) + (a_ + 1) * cos), (a_ + 1) + (a_ - 1) * cos - s)
    elif kind == "HSC":
        s = 2 * math.sqrt(a_) * alpha
        b = (a_ * ((a_ + 1) + (a_ - 1) * cos + s), -2 * a_ * ((a_ - 1) + (a_ + 1) * cos), a_ * ((a_ + 1) + (a_ - 1) * cos - s))
        a = ((a_ + 1) - (a_ - 1) * cos + s, 2 * ((a_ - 1) - (a_ + 1) * cos), (a_ + 1) - (a_ - 1) * cos - s)
    else:
        return [0.0] * len(freqs)
    out = []
    for f in freqs:
        w = 2 * math.pi * f / rate
        z1, z2 = complex(math.cos(-w), math.sin(-w)), complex(math.cos(-2 * w), math.sin(-2 * w))
        h = (b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2)
        out.append(20 * math.log10(max(abs(h), 1e-9)))
    return out


_FILTER = re.compile(r"Filter\s*\d*:\s*ON\s+(PK|LSC|HSC|LS|HS)\s+Fc\s+([\d.]+)\s*Hz\s+Gain\s+(-?[\d.]+)\s*dB"
                     r"(?:\s+Q\s+([\d.]+))?", re.I)


def parse(text):
    """A curve [[freq, dB], ...] from a ParametricEQ.txt or GraphicEQ.txt; ValueError if it is neither."""
    graphic = re.search(r"GraphicEQ:\s*(.+)", text)
    if graphic:
        points = []
        for pair in graphic.group(1).split(";"):
            parts = pair.split()
            if len(parts) == 2:
                points.append([float(parts[0]), float(parts[1])])
        if len(points) < 2:
            raise ValueError("This GraphicEQ file has no curve")
        return sorted(points)
    filters = _FILTER.findall(text)
    if not filters:
        raise ValueError("Not an AutoEQ / Equalizer APO file (no filters found)")
    freqs = curve_freqs()
    total = [0.0] * len(freqs)
    for kind, fc, gain, q in filters:
        kind = {"LS": "LSC", "HS": "HSC"}.get(kind.upper(), kind.upper())
        for i, db in enumerate(_biquad_db(kind, float(fc), float(gain), float(q or 0.71), freqs)):
            total[i] += db
    return [[round(f, 2), round(g, 3)] for f, g in zip(freqs, total)]


_ENTRY = re.compile(r"^- \[(.+?)\]\(\./(.+?)\) by (.+?)(?: on (.+))?$")


def parse_index(markdown):
    """AutoEQ's INDEX.md as [{"name", "path", "source"}]."""
    out = []
    for line in markdown.splitlines():
        m = _ENTRY.match(line.strip())
        if m:
            source = m.group(3) + (f" on {m.group(4)}" if m.group(4) else "")
            out.append({"name": m.group(1), "path": urllib.parse.unquote(m.group(2)), "source": source})
    return out


def search(entries, query, limit=40):
    """Entries whose name holds every word of the query, names starting with it first."""
    words = query.casefold().split()
    if not words:
        return []
    hits = [e for e in entries if all(w in e["name"].casefold() for w in words)]
    q = query.casefold().strip()
    hits.sort(key=lambda e: (not e["name"].casefold().startswith(q), len(e["name"]), e["name"].casefold()))
    return hits[:limit]


def profile_url(entry, kind="ParametricEQ"):
    name = entry["path"].rstrip("/").rsplit("/", 1)[-1]
    return RAW + urllib.parse.quote(f"{entry['path']}/{name} {kind}.txt")


def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Hallucinate music player"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        return resp.read().decode("utf-8", "replace")


class HeadphoneFinder(QObject):
    """Searches AutoEQ and hands a chosen profile to the player."""

    changed = Signal()
    _done = Signal(object)

    def __init__(self, cache_dir, player, parent=None):
        super().__init__(parent)
        self._cache = Path(cache_dir) / "autoeq-index.md"
        self._player = player
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autoeq")
        self._entries = None
        self._results = []
        self._status = ""
        self._busy = False
        self._done.connect(self._apply)

    @Property("QVariantList", notify=changed)
    def results(self):
        return self._results

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    def _set(self, status, busy):
        self._status, self._busy = status, busy
        self.changed.emit()

    def _load_index(self):
        if self._entries is not None:
            return self._entries
        fresh = self._cache.exists() and time.time() - self._cache.stat().st_mtime < INDEX_MAX_AGE
        if fresh:
            text = self._cache.read_text(encoding="utf-8")
        else:
            try:
                text = _fetch(INDEX_URL)
                self._cache.parent.mkdir(parents=True, exist_ok=True)
                self._cache.write_text(text, encoding="utf-8")
            except OSError:
                if not self._cache.exists():
                    raise
                text = self._cache.read_text(encoding="utf-8")  # stale beats nothing
        self._entries = parse_index(text)
        return self._entries

    @Slot(str)
    def find(self, query):
        if not query.strip():
            self._results = []
            self._set("", False)
            return
        self._set("Searching AutoEQ…", True)

        def work():
            try:
                return ("results", query, search(self._load_index(), query))
            except Exception as exc:  # noqa: BLE001
                logger.warning("AutoEQ index unavailable: %s", exc)
                return ("error", query, "Couldn't reach AutoEQ. Check your connection, or import a file instead.")

        self._pool.submit(lambda: self._done.emit(work()))

    @Slot(int)
    def choose(self, index):
        if not 0 <= index < len(self._results):
            return
        entry = self._results[index]
        self._set(f"Downloading {entry['name']}…", True)

        def work():
            try:
                text = _fetch(profile_url(entry))
                return ("profile", entry, text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AutoEQ profile download failed: %s", exc)
                return ("error", entry, "Couldn't download that profile.")

        self._pool.submit(lambda: self._done.emit(work()))

    @Slot(str, result=str)
    def importFile(self, url):
        """Load a ParametricEQ/GraphicEQ file; returns an error message or ""."""
        path = QUrl(url).toLocalFile() if url.startswith("file:") else url
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            name = re.sub(r"\s*(ParametricEQ|GraphicEQ|FixedBandEQ)$", "", Path(path).stem).strip() or "Imported"
            self._player.setHeadphoneProfile(name, json.dumps(parse(text)))
        except (OSError, ValueError) as exc:
            return str(exc)
        return ""

    @Slot(object)
    def _apply(self, result):
        kind, what, value = result
        if kind == "results":
            self._results = value
            self._set("" if value else f"No headphones match “{what}”", False)
        elif kind == "profile":
            try:
                self._player.setHeadphoneProfile(what["name"], json.dumps(parse(value)))
                self._set(f"Correcting for {what['name']}", False)
            except ValueError as exc:
                self._set(str(exc), False)
        else:
            self._set(value, False)

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
