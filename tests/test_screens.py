"""Every page and overlay, in every theme: no QML warnings, and in dark themes no glaring unthemed white blocks.

This catches bugs like the Stats rows that fell back to white when their colour binding failed. Rendering uses
Qt's software renderer, so shader effects are left out, but every control, colour and layout is drawn."""
import numpy as np
import pytest
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QUrl
from PySide6.QtGui import QIcon, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from hallucinate.app import QML_STYLE
from hallucinate.core.db import Database

PAGES = ("home", "albums", "artists", "songs", "folders", "liked", "stats", "history", "recap", "health",
         "visualizer", "settings")
BLOCK = 24


def white_blocks(image, threshold=0.92, share=0.95):
    """(x, y) of BLOCK-pixel squares that are nearly all near-white."""
    img = image.convertToFormat(QImage.Format.Format_RGB32)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8, img.bytesPerLine() * h).reshape(h, img.bytesPerLine())
    px = arr[:, : w * 4].reshape(h, w, 4)[:, :, :3].astype(np.float32) / 255  # BGRA in memory
    lum = 0.0722 * px[:, :, 0] + 0.7152 * px[:, :, 1] + 0.2126 * px[:, :, 2]
    bright = lum > threshold
    hb, wb = h // BLOCK, w // BLOCK
    blocks = bright[: hb * BLOCK, : wb * BLOCK].reshape(hb, BLOCK, wb, BLOCK).mean(axis=(1, 3))
    ys, xs = np.nonzero(blocks >= share)
    return [(int(x) * BLOCK, int(y) * BLOCK) for y, x in zip(ys, xs)]


def seed(tmp_path):
    """A small library: two albums with plays, a like, a rating, a playlist and a smart playlist."""
    music = tmp_path / "Music"
    db = Database(tmp_path / "library.db")
    for n, (artist, album) in enumerate((("Aurora Vale", "Northern Lights"), ("Blue Harbor", "Tidal"))):
        for i in range(4):
            path = str(music / artist / album / f"{i + 1:02d}.flac")
            db.upsert_track({
                "path": path, "mtime": 0, "size": 1, "title": f"Song {n}{i}", "artist": artist, "album_artist": artist,
                "aa_tag": 1, "album": album, "album_key": f"k{n}", "track_no": i + 1, "disc_no": 0, "year": 2000 + n,
                "genre": "Dream Pop", "duration": 180.0 + i, "fmt": "FLAC", "codec": "FLAC", "bitrate": 900_000,
                "sample_rate": 44100,
            })
            for _ in range(i + 1):
                db.record_play(path)
    db.add_folder(str(music))
    db.set_liked(str(music / "Aurora Vale" / "Northern Lights" / "01.flac"), True)
    db.set_rating(str(music / "Blue Harbor" / "Tidal" / "02.flac"), 4)
    pid = db.create_playlist("Evening")
    db.playlist_add(pid, [str(music / "Aurora Vale" / "Northern Lights" / "02.flac")])
    db.commit()
    db.close()


@pytest.fixture
def app_window(qapp, tmp_path, monkeypatch):
    """The whole window over the seeded library, with page transitions off."""
    from conftest import wait_for

    from hallucinate import scrobbling
    from hallucinate.discord import DiscordPresence
    from hallucinate.headphones import HeadphoneFinder
    from hallucinate.library import Library
    from hallucinate.listenbrainz import ListenBrainzScrobbler
    from hallucinate.lyricsctl import LyricsController
    from hallucinate.metaedit import MetadataEditor
    from hallucinate.player import Player
    from hallucinate.replaygain import ReplayGainAnalyzer
    from hallucinate.scrobbling import LastFmScrobbler
    from hallucinate.shell import DesktopShell
    from hallucinate.themes import ThemeManager
    from hallucinate.userlib import UserLibrary

    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(scrobbling.keyring, name, lambda *_: None)
    QQuickStyle.setStyle(QML_STYLE)
    seed(tmp_path)
    db_path = tmp_path / "library.db"
    library = Library(db_path, tmp_path / "art")
    player = Player(session_file=tmp_path / "session.json")
    user_lib = UserLibrary(db_path, player)
    objects = {
        "library": library, "player": player, "userLib": user_lib,
        "scrobbler": LastFmScrobbler(player, tmp_path / "data"),
        "listenbrainz": ListenBrainzScrobbler(player, tmp_path / "data", user_lib),
        "metaEditor": MetadataEditor(db_path, tmp_path / "art"),
        "lyricsCtl": LyricsController(db_path, player),
        "replayGain": ReplayGainAnalyzer(db_path),
        "headphones": HeadphoneFinder(tmp_path / "cache", player),
        "shell": DesktopShell(qapp, player, QIcon()),
        "discord": DiscordPresence(player),
        "themeManager": ThemeManager(tmp_path / "config", player),
    }
    engine = QQmlApplicationEngine()
    for key, value in objects.items():
        engine.rootContext().setContextProperty(key, value)
    from pathlib import Path

    qml_dir = Path(__file__).parents[1] / "hallucinate" / "qml"
    engine.addImportPath(str(qml_dir))
    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(str(w) for w in ws))
    engine.load(QUrl.fromLocalFile(str(qml_dir / "main.qml")))
    window = engine.rootObjects()[0]
    window.resize(1100, 1600)  # tall, so long pages are drawn further down
    stack = window.findChild(QObject, "pageStack")
    for transition in ("pushEnter", "pushExit", "popEnter", "popExit", "replaceEnter", "replaceExit"):
        stack.setProperty(transition, None)  # pages appear at once, so each is drawn settled
    assert wait_for(lambda: library.trackCount == 8 and user_lib.topArtists.count > 0)
    player.playList(library.allTracks()[:3], 0)
    player.pause()

    yield window, objects, warnings
    window.close()
    del stack
    qapp.processEvents()
    for obj in objects.values():
        if hasattr(obj, "shutdown"):
            obj.shutdown()


def test_every_page_in_every_theme(qapp, app_window):
    window, objects, warnings = app_window
    manager = objects["themeManager"]

    def invoke(method, *args):
        assert QMetaObject.invokeMethod(window, method, Qt.ConnectionType.DirectConnection,
                                        *[Q_ARG("QVariant", a) for a in args]), method

    def settle():
        for _ in range(3):
            qapp.processEvents()

    def screens():
        for page in PAGES:
            invoke("go", page)
            settle()
            yield page
        invoke("go", "albums")
        invoke("openAlbum", "k0")
        settle()
        yield "album"
        invoke("openArtist", "Aurora Vale")
        settle()
        yield "artist"
        invoke("go", "home")
        window.setProperty("queueOpen", True)
        settle()
        yield "queue"
        window.setProperty("queueOpen", False)
        now_playing = window.findChild(QObject, "nowPlayingView")
        now_playing.setProperty("open", True)
        now_playing.setProperty("lyricsMode", True)
        settle()
        yield "now playing"
        now_playing.setProperty("open", False)
        now_playing.setProperty("lyricsMode", False)
        welcome = window.findChild(QObject, "welcome")
        for step in (0, 1, 2):
            welcome.setProperty("open", True)
            welcome.setProperty("step", step)
            settle()
            yield f"welcome {step + 1}"
        welcome.setProperty("open", False)
        settle()
        dialog = window.findChild(QObject, "updateDialog")
        QMetaObject.invokeMethod(dialog, "open")
        settle()
        yield "update dialog"
        QMetaObject.invokeMethod(dialog, "close")
        settle()
        dialog = window.findChild(QObject, "closeDialog")
        QMetaObject.invokeMethod(dialog, "open")
        settle()
        yield "close dialog"
        QMetaObject.invokeMethod(dialog, "close")
        settle()
        # a menu with a row under the pointer: that row was drawn white on white in dark themes
        menu = window.findChild(QObject, "albumMenu")
        QMetaObject.invokeMethod(menu, "show", Q_ARG("QVariant", ["k0"]), Q_ARG("QVariant", "Northern Lights"),
                                 Q_ARG("QVariant", "Aurora Vale"))
        menu.setProperty("x", 300)
        menu.setProperty("y", 120)
        menu.setProperty("currentIndex", 1)
        settle()
        yield "album menu"
        QMetaObject.invokeMethod(menu, "close")
        settle()
        editor = window.findChild(QObject, "tagEditor")
        QMetaObject.invokeMethod(editor, "editAlbum", Q_ARG("QVariant", "k0"))
        settle()
        yield "edit album"
        QMetaObject.invokeMethod(editor, "reject")
        settle()
        dialog = window.findChild(QObject, "trashAlbumsDialog")
        dialog.setProperty("what", "“Northern Lights”")
        QMetaObject.invokeMethod(dialog, "open")
        settle()
        yield "trash dialog"
        QMetaObject.invokeMethod(dialog, "close")
        settle()

    problems = []
    for theme in manager.availableThemes:
        assert manager.selectTheme(theme)
        from PySide6.QtTest import QTest

        QTest.qWait(260)  # theme colours fade over ~220 ms
        dark = manager.bg.lightnessF() < 0.5
        for screen in screens():
            QTest.qWait(40 if screen.startswith(("now", "welcome")) else 0)
            if dark and screen != "welcome 2":  # the theme picker shows light themes' tiles on purpose
                blocks = white_blocks(window.grabWindow())
                if blocks:
                    problems.append(f"{theme} / {screen}: {len(blocks)} white blocks, first at {blocks[0]}")
            if warnings:
                problems.append(f"{theme} / {screen}: {warnings[:2]}")
                warnings.clear()
    assert not problems, "\n".join(problems[:20])


def test_search_results_draw_without_per_row_python_reads(qapp, app_window, monkeypatch):
    """Each read from Python while drawing waits for any worker thread busy in Python, so search results (rebuilt
    on every keystroke) must come over as one plain list, with likes and the playing song looked up once."""
    from conftest import wait_for

    from hallucinate.models import DictModel

    window, objects, warnings = app_window
    library = objects["library"]
    reads = []
    original = DictModel.data
    monkeypatch.setattr(DictModel, "data", lambda self, index, role=0: reads.append(role) or original(self, index, role))

    def items():  # every item in the window, walked without a recursive closure (cycles hold QObjects)
        stack = [window.contentItem()]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.childItems())

    def visible_rows():
        return [i for i in items() if i.objectName() == "trackRow" and i.isVisible()]

    field = next(i for i in items() if "Search" in str(i.property("placeholderText") or ""))
    field.setProperty("text", "song")
    assert wait_for(lambda: len(library.searchResults["tracks"]) == 8 and len(visible_rows()) == 8)
    for _ in range(5):
        qapp.processEvents()
    assert reads == []  # nothing per row from the Python models
    liked = {r.property("title"): r.property("liked") for r in visible_rows()}
    assert liked["Song 00"] and not liked["Song 01"]  # likes still shown (seed() likes Song 00)
    player = objects["player"]
    playing = player.current.get("path") if player.hasTrack else None
    assert [r.property("path") for r in visible_rows() if r.property("current")] == ([playing] if playing else [])
    assert not warnings, warnings[:3]
    del field


def test_albums_select_menu_and_remove(qapp, app_window):
    """Ctrl+click selects albums, the bar counts them, right-click opens the album menu, and removing goes
    through its confirmation."""
    from conftest import wait_for
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    window, objects, warnings = app_window
    library = objects["library"]
    QMetaObject.invokeMethod(window, "go", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", "albums"))

    def items():
        stack = [window.contentItem()]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.childItems())

    def named(name):
        return [i for i in items() if i.objectName() == name and i.isVisible()]

    assert wait_for(lambda: len(named("albumCard")) == 2)
    cards = sorted(named("albumCard"), key=lambda c: c.mapToScene(c.position()).x())

    def click(card, button=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
        p = card.mapToScene(card.position())
        QTest.mouseClick(window, button, mods, QPoint(int(p.x() + 40), int(p.y() + 40)))

    for card in cards:
        click(card, mods=Qt.KeyboardModifier.ControlModifier)
    bar = named("albumBar")
    assert wait_for(lambda b=bar[0]: b.property("shown"))
    assert next(i for i in items() if i.objectName() == "albumSelectionCount").property("text") == "2 albums selected"

    click(cards[0], Qt.MouseButton.RightButton)
    menu = window.findChild(QObject, "albumMenu")
    assert wait_for(lambda m=menu: m.property("visible"))
    keys = menu.property("keys").toVariant()
    assert len(keys) == 2  # right-clicking a selected album acts on the whole selection
    QMetaObject.invokeMethod(menu, "close")

    dialog = window.findChild(QObject, "removeAlbumsDialog")
    dialog.setProperty("keys", keys)
    QMetaObject.invokeMethod(dialog, "accept")
    assert wait_for(lambda: library.trackCount == 0 and library.hiddenCount == 8, timeout=5)
    for _ in range(5):
        qapp.processEvents()
    assert not warnings, warnings[:3]
    del bar, cards, menu, dialog


def test_timeline_year_shows_two_lines_until_asked(qapp, app_window, tmp_path):
    """A year with many albums shows two lines of covers and a "Show all" button for the rest."""
    from conftest import wait_for
    from PySide6.QtCore import QPointF
    from PySide6.QtTest import QTest

    window, objects, warnings = app_window
    library = objects["library"]
    db = Database(tmp_path / "library.db")
    for i in range(40):
        db.upsert_track({
            "path": str(tmp_path / "Music" / "Busy" / f"{i}.flac"), "mtime": 0, "size": 1, "title": f"B{i}",
            "artist": "Busy", "album_artist": "Busy", "aa_tag": 1, "album": f"Busy {i:02d}", "album_key": f"busy{i}",
            "track_no": 1, "disc_no": 0, "year": 2001, "genre": "", "duration": 100.0, "fmt": "FLAC",
            "codec": "FLAC", "bitrate": 900_000, "sample_rate": 44100,
        })
    db.commit()
    db.close()
    library.reload()
    assert wait_for(lambda: library.albumCount == 42)

    def visible(name):
        stack, found = [window.contentItem()], []
        while stack:
            item = stack.pop()
            if item.objectName() == name and item.isVisible():
                found.append(item)
            stack.extend(item.childItems())
        return found

    QMetaObject.invokeMethod(window, "go", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", "albums"))
    assert wait_for(lambda: len(visible("albumCard")) > 2)  # the grid has finished building before switching
    window.findChild(QObject, "pageStack").property("currentItem").setProperty("view", "timeline")
    assert wait_for(lambda: len(visible("timelineMore")) == 1)  # 2001 (41 albums) is busy; 2000 (one) isn't
    button = visible("timelineMore")[0]
    assert button.property("text") == "Show all 41"
    p = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p.toPoint())
    assert wait_for(lambda: not visible("timelineMore"))
    assert not warnings, warnings[:3]
    del button


def test_track_info_badges_never_draw_empty(qapp, app_window):
    """With "Show track info" on, a list that doesn't know a song's format (the artist page's Most played did
    not) must not draw an empty pill after the title."""
    from conftest import wait_for

    window, objects, warnings = app_window
    player = objects["player"]
    player.setShowTrackInfo(True)
    try:
        QMetaObject.invokeMethod(window, "openArtist", Qt.ConnectionType.DirectConnection,
                                 Q_ARG("QVariant", "Aurora Vale"))

        def badges():
            stack, found = [window.contentItem()], []
            while stack:
                item = stack.pop()
                if item.property("formatName") is not None and item.property("spokenLabel") is not None \
                        and item.isVisible():
                    found.append(item)
                stack.extend(item.childItems())
            return found

        assert wait_for(lambda: len(badges()) >= 4)
        assert all(b.property("label") for b in badges()), [b.property("label") for b in badges()]
        assert any("FLAC" in b.property("label") for b in badges())
        assert not warnings, warnings[:3]
    finally:
        player.setShowTrackInfo(False)
