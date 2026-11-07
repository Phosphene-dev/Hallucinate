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


def test_a_cover_written_late_still_turns_up(qapp, tmp_path):
    """A tester's songs stayed blank, at random, until scrolled away and back: a cover that wasn't there yet
    (a scan writing it) was tried six times in about 18 s, then given up for good. Now it keeps looking, more
    slowly, and shows up when the file does; a load that fails outright is tried again too."""
    import pathlib

    from conftest import wait_for
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    import hallucinate
    from hallucinate.thumbs import ArtProvider

    qml = pathlib.Path(hallucinate.__file__).parent / "qml"
    engine = QQmlEngine()
    engine.addImageProvider("art", ArtProvider(tmp_path / "cache"))
    late = tmp_path / "late.jpg"
    comp = QQmlComponent(engine)
    comp.setData(('import QtQuick\nimport "."\nCover { width: 64; height: 64; source: "%s" }'
                  % QUrl.fromLocalFile(str(late)).toString()).encode(), QUrl.fromLocalFile(str(qml / "CoverProbe.qml")))
    cover = comp.create()
    assert cover is not None, comp.errorString()
    assert wait_for(lambda: cover.property("missing"), timeout=5)
    cover.setProperty("attempt", 6)  # (the quick tries are spent, as they were when it gave up)
    cover.setProperty("tryTag", "6-1")
    assert wait_for(lambda: cover.property("missing"), timeout=5)
    make_cover(late)
    assert wait_for(lambda: not cover.property("missing") and cover.property("attempt") > 6, timeout=15)
    cover.deleteLater()


def test_covers_come_with_their_corners_round(qapp, tmp_path):
    """#115, the real cause: on a graphics card each cover was rounded on screen by a shader mask (a hidden layer
    fed through MultiEffect), which now and then drew nothing once the picture had loaded: a blank square, with
    no ♪, until the row was made again. The thumbnails come with their corners round now and a cover is a plain
    image; this checks the corners, and that nothing in a Cover renders through a layer or an effect again."""
    import pathlib

    from conftest import wait_for
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    import hallucinate
    from hallucinate.thumbs import ArtProvider, rounded

    # the picture: cut square from its middle, transparent outside the rounded corners (50: a circle)
    wide = QImage(120, 80, QImage.Format.Format_RGB32)
    wide.fill(QColor(200, 30, 30))
    square = rounded(wide, 25)
    assert (square.width(), square.height()) == (80, 80)
    assert square.pixelColor(0, 0).alpha() == 0 and square.pixelColor(79, 79).alpha() == 0
    assert square.pixelColor(40, 0).alpha() == 255 and square.pixelColor(40, 40).name() == "#c81e1e"
    assert rounded(wide, 50).pixelColor(6, 6).alpha() == 0
    assert ArtProvider.corner("128~3-9~r2~k50/x") == 50 and ArtProvider.corner("128/x") == 0
    assert ArtProvider.corner("64~k90/x") == 50

    # on screen: rows of covers in a list, each showing its own colour, with see-through corners
    qml = pathlib.Path(hallucinate.__file__).parent / "qml"
    colours = ["#d03030", "#30a040", "#3050d0", "#c0a020"]
    for i, c in enumerate(colours):
        img = QImage(600, 600, QImage.Format.Format_RGB32)
        img.fill(QColor(c))
        img.save(str(tmp_path / f"{i}.jpg"), "JPG", 95)
    (tmp_path / "Main.qml").write_text(
        'import QtQuick\nimport "%s"\nWindow { width: 200; height: 260; visible: true; color: "black"\n'
        '  ListView { objectName: "list"; anchors.fill: parent; model: %d\n'
        '    delegate: Item { width: 200; height: 64\n'
        '      Cover { objectName: "cover"; x: 8; y: 8; width: 48; height: 48; radius: 12\n'
        '              source: "%s/" + index + ".jpg" } } } }\n'
        % (QUrl.fromLocalFile(str(qml)).toString(), len(colours), QUrl.fromLocalFile(str(tmp_path)).toString()))
    engine = QQmlApplicationEngine()
    engine.addImageProvider("art", ArtProvider(tmp_path / "cache"))
    engine.load(QUrl.fromLocalFile(str(tmp_path / "Main.qml")))
    window = engine.rootObjects()[0]
    def items(item):
        for child in item.childItems():
            yield child
            yield from items(child)
    assert wait_for(lambda: len([o for o in items(window.contentItem()) if o.objectName() == "cover"]) == len(colours))
    covers = [o for o in items(window.contentItem()) if o.objectName() == "cover"]
    assert all("~k25/" in c.property("resolved") for c in covers)  # (12 of 48: the corners asked for)
    for c in covers:
        for item in items(c):
            assert not item.metaObject().className().startswith(("QQuickMultiEffect", "QQuickShaderEffect"))
    source = "\n".join(line.split("//")[0] for line in (qml / "Cover.qml").read_text().splitlines())
    assert "layer.enabled" not in source and "MultiEffect" not in source, "a Cover mustn't draw through a layer (#115)"

    def shown():
        img = window.grabWindow()
        dpr = img.devicePixelRatio()
        got = []
        for i in range(len(colours)):
            centre = img.pixelColor(int(32 * dpr), int((i * 64 + 32) * dpr))
            corner = img.pixelColor(int(9 * dpr), int((i * 64 + 9) * dpr))
            got.append((centre.name(), corner.name()))
        return got
    assert wait_for(lambda: all(abs(QColor(g[0]).red() - QColor(c).red()) < 30
                                and abs(QColor(g[0]).blue() - QColor(c).blue()) < 30
                                for g, c in zip(shown(), colours)), timeout=10), shown()
    assert all(QColor(corner).lightness() < 60 for _centre, corner in shown())  # (the black behind shows there)
    window.close()
