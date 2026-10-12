"""Every page and overlay, in every theme: no QML warnings, and in dark themes no glaring unthemed white blocks.

This catches bugs like the Stats rows that fell back to white when their colour binding failed. Rendering uses
Qt's software renderer, so shader effects are left out, but every control, colour and layout is drawn."""
import numpy as np
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QUrl
from PySide6.QtGui import QIcon, QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

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


def test_every_page_in_every_theme(qapp, tmp_path, monkeypatch):
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
    QQuickStyle.setStyle("Basic")
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
    manager = objects["themeManager"]
    assert wait_for(lambda: library.trackCount == 8 and user_lib.topArtists.count > 0)
    player.playList(library.allTracks()[:3], 0)
    player.pause()

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

    window.close()
    del stack
    qapp.processEvents()
    for obj in objects.values():
        if hasattr(obj, "shutdown"):
            obj.shutdown()
