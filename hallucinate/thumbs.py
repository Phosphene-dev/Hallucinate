"""Cached, size-bucketed cover thumbnails served to QML as ``image://art/<px>/<encoded file url>``.

QML requests run on Qt's image-loader threads (``Image.asynchronous``), so decoding and scaling
large embedded covers never touches the GUI thread. Scaled results are cached on disk."""
import hashlib
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtQuick import QQuickImageProvider

from .cachetrim import touch_if_stale

BUCKETS = (64, 128, 256, 512)


def bucket(px: int) -> int:
    return next((b for b in BUCKETS if px <= b), BUCKETS[-1])


class ArtProvider(QQuickImageProvider):
    def __init__(self, cache_dir):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._dir = Path(cache_dir)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    @staticmethod
    def parse(image_id: str):
        size_part, _, rest = image_id.partition("/")
        try:
            px = bucket(int(size_part.split("~")[0]))  # ("128~2": a Cover's second try at a picture that failed)
        except ValueError:
            return None, ""
        rest = unquote(rest)
        path = QUrl(rest).toLocalFile() if rest.startswith("file:") else rest
        return px, path

    def requestImage(self, image_id, size, requested_size):
        px, path = self.parse(image_id)
        image = QImage()
        if px and path:
            image = self.load(path, px)
        if image.isNull():
            # Undecodable/missing art: a transparent pixel keeps QML quiet and shows the placeholder.
            image = QImage(1, 1, QImage.Format.Format_ARGB32)
            image.fill(0)
        if not image.isNull():
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image

    def load(self, path: str, px: int) -> QImage:
        return load_thumbnail(self._dir, path, px)


def load_thumbnail(cache_dir, path: str, px: int) -> QImage:
    """`path`'s picture scaled to fit `px` (a bucket size), from the disk cache when it's there. Also used by the
    web interface (see webserver.py), which has no QML engine."""
    cache_dir = Path(cache_dir)
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return QImage()
    digest = hashlib.sha1(f"{path}|{mtime}|{px}".encode("utf-8", "surrogateescape"), usedforsecurity=False).hexdigest()
    cached = cache_dir / f"{digest}.jpg"
    if cached.exists():
        image = QImage(str(cached)) if complete(cached) else QImage()
        if not image.isNull():
            touch_if_stale(cached)  # recently used thumbnails survive cache trimming
            return image
        try:
            cached.unlink()  # cut short: made again below
        except OSError:
            pass
    image = _read_scaled(path, px)
    if image.isNull():
        # A file that's there but didn't read (written over by a scan just then, or a busy disk): once more
        time.sleep(0.05)
        image = _read_scaled(path, px)
    if image.isNull():
        return image
    if max(image.width(), image.height()) > px:
        image = image.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    # A temporary file of its own for each writer: two views asking for the same cover at once used to share one
    # name, and one would move the other's half-written file into the cache, where it stayed as a cover with a
    # garbled band or a blank square
    tmp = None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=cache_dir, prefix=digest + ".", suffix=".tmp")
        os.close(fd)
        if image.save(tmp, "JPG" if not image.hasAlphaChannel() else "PNG", 88):
            os.replace(tmp, cached)
            tmp = None
    except OSError:
        pass
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return image


def _read_scaled(path: str, px: int) -> QImage:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    native = reader.size()
    if native.isValid() and max(native.width(), native.height()) > px:
        reader.setScaledSize(native.scaled(QSize(px, px), Qt.AspectRatioMode.KeepAspectRatio))
    return reader.read()


def complete(path) -> bool:
    """Whether a cached thumbnail was written to the end: a JPEG ends with its end-of-image mark, a PNG with its
    IEND chunk. A file cut short still decodes, as a picture with a grey band or nothing at all."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
            fh.seek(-12, os.SEEK_END)
            tail = fh.read()
    except OSError:
        return False
    if head.startswith(b"\xff\xd8"):
        return tail.rstrip(b"\x00").endswith(b"\xff\xd9")
    if head.startswith(b"\x89PNG"):
        return b"IEND" in tail
    return True
