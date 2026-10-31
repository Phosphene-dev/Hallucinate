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


def test_a_cover_that_fails_to_read_once_is_read_again(qapp, tmp_path, monkeypatch):
    """A scan writing over a cover just as a row asks for it: one failed read isn't a missing cover."""
    import hallucinate.thumbs as thumbs

    cover = make_cover(tmp_path / "cover.jpg")
    real, calls = thumbs._read_scaled, []

    def flaky(path, px):
        calls.append(path)
        return QImage() if len(calls) == 1 else real(path, px)

    monkeypatch.setattr(thumbs, "_read_scaled", flaky)
    img = load_thumbnail(tmp_path / "cache", str(cover), 128)
    assert not img.isNull() and len(calls) == 2


def test_a_cover_tries_again_at_a_new_address(qapp):
    """Qt's image cache kept the blank placeholder of a failed try under its address; a row made again (while
    scrolling) got that blank back. Each try now has an address of its own."""
    import pathlib

    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    import hallucinate

    qml = pathlib.Path(hallucinate.__file__).parent / "qml"
    engine = QQmlEngine()
    comp = QQmlComponent(engine)
    comp.setData(b'import QtQuick\nimport "."\nCover { width: 64; height: 64; source: "file:///nowhere/cover.jpg" }',
                 QUrl.fromLocalFile(str(qml / "CoverProbe.qml")))
    cover = comp.create()
    assert cover is not None, comp.errorString()
    first = cover.property("resolved")
    cover.setProperty("tryTag", "1-111")
    cover.setProperty("attempt", 1)
    second = cover.property("resolved")
    cover.setProperty("tryTag", "2-222")
    cover.setProperty("attempt", 2)
    third = cover.property("resolved")
    assert len({first, second, third}) == 3
    assert "~1-111" in second and "~2-222" in third
    from hallucinate.thumbs import ArtProvider
    assert ArtProvider.parse(third.split("image://art/")[1])[0] == 64
