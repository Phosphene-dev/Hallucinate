"""The cover thumbnail cache: whole files only, however many views ask for the same cover at once."""
import threading

from PySide6.QtGui import QColor, QImage

from hallucinate.thumbs import complete, load_thumbnail


def make_cover(path, size=900):
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor("#3a7bd5"))
    assert img.save(str(path), "JPG", 92)
    return path


def test_a_cover_cut_short_in_the_cache_is_made_again(qapp, tmp_path):
    cover = make_cover(tmp_path / "cover.jpg")
    cache = tmp_path / "cache"
    first = load_thumbnail(cache, str(cover), 256)
    assert not first.isNull() and max(first.width(), first.height()) == 256
    (cached,) = list(cache.glob("*.jpg"))
    assert complete(cached)
    data = cached.read_bytes()
    cached.write_bytes(data[: len(data) // 2])  # as a half-written file would leave it
    assert not complete(cached)
    again = load_thumbnail(cache, str(cover), 256)
    assert not again.isNull() and again.pixelColor(128, 250).name() == first.pixelColor(128, 250).name()
    assert complete(cached)


def test_many_views_asking_at_once_leave_a_whole_file(qapp, tmp_path):
    """Two views asking for the same cover at once used to share one temporary file, and could move the other's
    half-written one into the cache: a cover with a grey band, or blank."""
    cover = make_cover(tmp_path / "cover.jpg", 1600)
    cache = tmp_path / "cache"
    errors = []

    def ask():
        try:
            img = load_thumbnail(cache, str(cover), 512)
            assert not img.isNull()
        except Exception as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=ask) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    files = list(cache.iterdir())
    assert [f.suffix for f in files] == [".jpg"]  # no temporary files left behind
    assert complete(files[0])
