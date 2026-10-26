"""The spectrum analyzer: a song's spectrogram, as Spek draws it (#96). Time runs left to right, frequency bottom to
top (to half the file's sample rate), loudness in colour from black (silence) through blue, purple, red and
orange to white (full scale). It shows what a file really holds: a lossy file's cut-off (often 16 or 19 kHz), an
"upsampled" one with nothing above 22 kHz, clipping, a CD transfer's band limit.

The song is decoded in the analysis helper (see analysis.py), which turns it into columns of loudness by frequency
as it goes (Accumulator), so the window never waits on FFmpeg and a whole song is never held in memory. The image
is drawn here, on a worker thread, saved to the cache, and shown in the Spectrum analyzer window; "Save image"
copies it to Pictures/Hallucinate."""
import hashlib
import logging
import os
import shutil
import threading

import numpy as np
from PySide6.QtCore import Property, QObject, QRectF, Qt, QUrl, Signal, Slot

logger = logging.getLogger(__name__)

FFT = 4096  # samples per column: 10.8 Hz bins at 44.1 kHz
ROWS = 512  # frequency rows kept (FFT // 2 bins, the loudest of each four)
FLOOR_DB = -120.0
WIDTH, HEIGHT = 1400, 640  # the plot, in pixels, in the saved image
LEFT, RIGHT, TOP, BOTTOM = 76, 110, 74, 52


class Accumulator:
    """Mono samples in, columns of loudness out: each FFT samples become ROWS levels, 0 (FLOOR_DB or quieter)
    to 255 (full scale), lowest frequency first."""

    def __init__(self):
        self.rest = np.zeros(0, np.float32)
        self.columns = []
        self.rate = 0
        self.channels = 0
        self.window = np.hanning(FFT).astype(np.float32)
        self.reference = float(self.window.sum()) / 2  # a full-scale sine's peak bin

    def add(self, samples, rate, channels=1):
        """`samples`: float frames x channels (or mono). The channels are mixed: what you hear."""
        samples = np.asarray(samples, np.float32)
        if samples.ndim == 2:
            self.channels = self.channels or samples.shape[1]
            samples = samples.mean(axis=1)
        else:
            self.channels = self.channels or channels
        self.rate = self.rate or int(rate)
        data = np.concatenate([self.rest, samples]) if self.rest.size else samples
        count = data.size // FFT
        if count:
            frames = data[:count * FFT].reshape(count, FFT) * self.window
            spectrum = np.abs(np.fft.rfft(frames, axis=1))[:, :FFT // 2]
            db = 20.0 * np.log10(np.maximum(spectrum / self.reference, 1e-12))
            level = np.clip((db - FLOOR_DB) / -FLOOR_DB * 255.0, 0, 255)
            self.columns.append(level.reshape(count, ROWS, -1).max(axis=2).astype(np.uint8))
        self.rest = data[count * FFT:].copy()

    def result(self):
        cols = np.concatenate(self.columns) if self.columns else np.zeros((0, ROWS), np.uint8)
        return {"columns": cols, "rate": self.rate, "channels": self.channels}


# Spek's colours: black, deep blue, purple, red, orange, yellow, white
STOPS = [(0.0, (0, 0, 0)), (0.18, (0, 0, 90)), (0.36, (110, 0, 160)), (0.54, (200, 0, 60)),
         (0.72, (255, 120, 0)), (0.88, (255, 230, 0)), (1.0, (255, 255, 255))]


def palette():
    """256 colours as 0xAARRGGBB."""
    xs = np.linspace(0.0, 1.0, 256)
    at = [p for p, _ in STOPS]
    rgb = [np.interp(xs, at, [c[i] for _, c in STOPS]) for i in range(3)]
    return (0xFF000000 | (rgb[0].astype(np.uint32) << 16) | (rgb[1].astype(np.uint32) << 8)
            | rgb[2].astype(np.uint32)).astype(np.uint32)


def fit_columns(columns, width):
    """`columns` (n x ROWS) as exactly `width` columns: the loudest of each group when there are more, repeated
    when there are fewer."""
    n = columns.shape[0]
    if n == 0:
        return np.zeros((width, ROWS), np.uint8)
    if n <= width:
        return columns[np.minimum((np.arange(width) * n) // width, n - 1)]
    edges = np.linspace(0, n, width + 1).astype(np.int64)
    return np.maximum.reduceat(columns, edges[:-1], axis=0)


def _step(span, steps, most=12):
    for s in steps:
        if span / s <= most:
            return s
    return steps[-1]


def _clock(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 3600}:{seconds // 60 % 60:02}:{seconds % 60:02}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02}"


def render(columns, rate, title, details, width=WIDTH, height=HEIGHT):
    """The spectrogram as a QImage, with its axes, colour scale and what the file is."""
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

    plot = fit_columns(columns, width)  # width x ROWS
    lut = palette()
    pixels = np.ascontiguousarray(lut[plot.T[::-1]])  # ROWS x width, highest frequency at the top
    strip = QImage(pixels.data, width, ROWS, width * 4, QImage.Format.Format_RGB32).copy()
    strip = strip.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)

    image = QImage(LEFT + width + RIGHT, TOP + height + BOTTOM, QImage.Format.Format_RGB32)
    image.fill(QColor("#0b0b10"))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.drawImage(LEFT, TOP, strip)
    ink, dim = QColor("#e8e6f0"), QColor("#9a97a8")
    font = QFont()
    font.setPixelSize(13)
    p.setFont(font)

    # what it is
    bold = QFont(font)
    bold.setPixelSize(17)
    bold.setWeight(QFont.Weight.DemiBold)
    p.setFont(bold)
    p.setPen(ink)
    p.drawText(QRectF(LEFT, 12, width, 26), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
    p.setFont(font)
    p.setPen(dim)
    p.drawText(QRectF(LEFT, 40, width, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, details)

    # the frame and the scales
    p.setPen(QPen(dim, 1))
    p.drawRect(QRectF(LEFT - 0.5, TOP - 0.5, width + 1, height + 1))
    nyquist = (rate or 44100) / 2
    khz = nyquist / 1000
    step = _step(khz, [1, 2, 4, 5, 10, 20, 50])
    k = 0.0
    while k <= khz + 1e-6:
        y = TOP + height - k / khz * height
        p.drawLine(LEFT - 6, int(y), LEFT, int(y))
        p.drawText(QRectF(0, y - 9, LEFT - 10, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{k:g} kHz")
        k += step
    seconds = columns.shape[0] * FFT / (rate or 44100)
    if seconds > 0:
        step = _step(seconds, [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800])
        t = 0.0
        while t <= seconds + 1e-6:
            x = LEFT + t / seconds * width
            p.drawLine(int(x), TOP + height, int(x), TOP + height + 6)
            p.drawText(QRectF(x - 40, TOP + height + 8, 80, 18), Qt.AlignmentFlag.AlignHCenter, _clock(t))
            t += step

    # the colour scale, in dB
    bar = QImage(1, 256, QImage.Format.Format_RGB32)
    for i, colour in enumerate(lut[::-1]):
        bar.setPixel(0, i, int(colour))
    x0 = LEFT + width + 24
    p.drawImage(QRectF(x0, TOP, 16, height), bar)
    p.drawRect(QRectF(x0 - 0.5, TOP - 0.5, 17, height + 1))
    for db in range(0, int(FLOOR_DB) - 1, -20):
        y = TOP + (db / FLOOR_DB) * height
        p.drawLine(int(x0 + 16), int(y), int(x0 + 21), int(y))
        p.drawText(QRectF(x0 + 24, y - 9, RIGHT - 48, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{db} dB")
    p.end()
    return image


def describe(row, rate, channels):
    """The line under the title: codec, sample rate, bit depth, bitrate, channels, length."""
    parts = []
    codec = (row.get("codec") or row.get("fmt") or "").upper()
    if codec:
        parts.append(codec)
    if rate:
        parts.append(f"{rate / 1000:g} kHz")
    depth = int(row.get("bit_depth") or 0)
    if depth == 1:
        parts.append("DSD")
    elif depth:
        parts.append(f"{depth}-bit")
    bitrate = int(row.get("bitrate") or 0)  # stored in bits per second
    if bitrate:
        parts.append(f"{round(bitrate / 1000) if bitrate >= 10_000 else bitrate} kbps")
    if channels:
        parts.append({1: "mono", 2: "stereo"}.get(channels, f"{channels} channels"))
    return "  ·  ".join(parts)


class Spectrograms(QObject):
    """open(path) analyses a song and shows its spectrogram (imageUrl once ready); save() keeps a copy in
    Pictures/Hallucinate."""

    changed = Signal()
    _rendered = Signal(object)

    def __init__(self, db_path, cache_dir, parent=None):
        super().__init__(parent)
        from .analysis import Analyser
        from .core.db import Database

        self._db = Database(db_path)
        self._cache = os.path.join(str(cache_dir), "spectrograms")
        self._analyser = Analyser(self)
        self._state = {"path": "", "title": "", "busy": False, "error": "", "image": "", "saved": "", "details": ""}
        self._job = 0
        self._rendered.connect(self._on_rendered)

    def _set(self, **values):
        self._state.update(values)
        self.changed.emit()

    @Property(bool, notify=changed)
    def busy(self):
        return self._state["busy"]

    @Property(str, notify=changed)
    def title(self):
        return self._state["title"]

    @Property(str, notify=changed)
    def details(self):
        return self._state["details"]

    @Property(str, notify=changed)
    def error(self):
        return self._state["error"]

    @Property(str, notify=changed)
    def imageUrl(self):
        image = self._state["image"]
        return QUrl.fromLocalFile(image).toString() if image else ""

    @Property(str, notify=changed)
    def saved(self):
        return self._state["saved"]

    def _row(self, path):
        try:
            rows = self._db._rows("SELECT * FROM tracks WHERE path=?", (path,))
        except Exception:  # noqa: BLE001
            rows = []
        return rows[0] if rows else {"path": path, "title": os.path.basename(path),
                                     "fmt": os.path.splitext(path)[1].lstrip(".")}

    @Slot(str)
    def open(self, path):
        """Analyse `path` (a library song, CUE sheet songs included) and show it."""
        from .core import remote

        if not path or remote.is_remote(path):
            self._set(path=path, busy=False, error="Only songs on this computer can be analysed", image="")
            return
        row = self._row(path)
        file = self._db.file_of(path)
        title = " – ".join(x for x in (row.get("artist"), row.get("title")) if x) or os.path.basename(path)
        self._job += 1
        job = self._job
        self._set(path=path, title=title, busy=True, error="", image="", saved="", details="")
        cached = self._cache_file(path, file)
        if cached and os.path.exists(cached):
            self._set(busy=False, image=cached, details=describe(row, row.get("sample_rate") or 0, 0))
            return
        self._analyser.cancel()
        self._analyser.submit(file, "spectrogram", lambda result, j=job, r=row, c=cached: self._analysed(j, r, c, result),
                              first=True)

    def _cache_file(self, path, file):
        try:
            st = os.stat(file)
        except OSError:
            return ""
        key = f"{path}|{st.st_size}|{st.st_mtime_ns}|{FFT}|{WIDTH}".encode("utf-8", "surrogatepass")
        return os.path.join(self._cache, hashlib.sha1(key, usedforsecurity=False).hexdigest() + ".png")

    def _analysed(self, job, row, cached, result):
        if job != self._job:
            return
        if not result or result.get("columns") is None or not len(result["columns"]):
            self._set(busy=False, error="This file couldn't be decoded")
            return
        columns, rate = result["columns"], int(result.get("rate") or 0)
        start, end = float(row.get("cue_start") or 0), float(row.get("cue_end") or 0)
        if (start or end) and rate:  # a CUE sheet song: its stretch of the file
            a = int(start * rate / FFT)
            b = int(end * rate / FFT) if end else columns.shape[0]
            columns = columns[a:max(a + 1, b)]
        details = describe(row, rate, int(result.get("channels") or 0))
        title = self._state["title"]

        def work():
            try:
                image = render(columns, rate, title, details)
                os.makedirs(self._cache, exist_ok=True)
                ok = image.save(cached or os.path.join(self._cache, "last.png"))
                self._rendered.emit((job, cached if ok else "", details))
            except Exception:  # noqa: BLE001
                logger.exception("Spectrogram failed")
                self._rendered.emit((job, "", details))

        threading.Thread(target=work, daemon=True, name="spectrogram").start()

    @Slot(object)
    def _on_rendered(self, payload):
        job, image, details = payload
        if job != self._job:
            return
        self._set(busy=False, image=image, details=details, error="" if image else "The image couldn't be drawn")

    @Slot(result=str)
    def save(self):
        """Copy the spectrogram shown to Pictures/Hallucinate; returns where, or "" when it couldn't be."""
        import re

        from .core import paths

        image = self._state["image"]
        if not image or not os.path.exists(image):
            return ""
        folder = paths.pictures_dir()
        name = re.sub(r'[\\/:*?"<>|]', "-", self._state["title"] or "Song")[:120]
        target = os.path.join(str(folder), f"{name} (spectrogram).png")
        try:
            os.makedirs(folder, exist_ok=True)
            shutil.copyfile(image, target)
        except OSError:
            return ""
        self._set(saved=target)
        return target

    @Slot()
    def cancel(self):
        self._job += 1
        self._analyser.cancel()
        if self._state["busy"]:
            self._set(busy=False)

    def shutdown(self):
        self._analyser.shutdown()
        self._db.close()
