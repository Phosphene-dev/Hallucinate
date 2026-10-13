import argparse
import json
import logging
import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from . import __version__
from .control import ControlServer, send_control
from .core import paths
from .discord import DiscordPresence
from .headphones import HeadphoneFinder
from .library import Library
from .listenbrainz import ListenBrainzScrobbler
from .lyricsctl import LyricsController
from .metaedit import MetadataEditor
from .player import Player
from .replaygain import ReplayGainAnalyzer
from .scrobbling import LastFmScrobbler
from .shell import DesktopShell
from .themes import ThemeManager
from .thumbs import ArtProvider
from .userlib import UserLibrary
from .waveform import WaveformService

HERE = Path(__file__).resolve().parent
# Our Qt Quick Controls style (qml/HallucinateStyle): the app's look for menus, dialogs, tooltips and text fields,
# with Qt's Basic style for everything else. Found through the qml/ import path.
QML_STYLE = "HallucinateStyle"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hallucinate", description="Modern desktop music player")
    ap.add_argument("folders", nargs="*", help="music folders to add to the library")
    controls = ap.add_mutually_exclusive_group()
    controls.add_argument("--next", dest="control", action="store_const", const="next", help="skip to the next track")
    controls.add_argument("--prev", dest="control", action="store_const", const="prev", help="play the previous track")
    controls.add_argument("--play-pause", dest="control", action="store_const", const="play-pause", help="toggle playback")
    controls.add_argument("--status", dest="control", action="store_const", const="status", help="print current playback status as JSON")
    ap.add_argument("--quit-after", type=int, metavar="MS", help=argparse.SUPPRESS)
    ap.add_argument("--decode-check", nargs="+", metavar="FILE", help=argparse.SUPPRESS)  # packaging CI
    ap.add_argument("--version", action="version", version=__version__)
    args, qt_args = ap.parse_known_args(argv if argv is not None else sys.argv[1:])

    if args.decode_check:
        from . import decodecheck

        return decodecheck.main(args.decode_check)
    if args.control:
        response = send_control(args.control)
        if response is None:
            print("Hallucinate is not running; start it before using playback controls.", file=sys.stderr)
            return 1
        if not response.get("ok"):
            print(response.get("error", "Playback control failed."), file=sys.stderr)
            return 1
        if args.control == "status":
            print(json.dumps(response["status"], ensure_ascii=False))
        return 0

    existing = (
        send_control("add-folders", folders=args.folders)
        if args.folders
        else send_control("raise")
    )
    if existing is not None and existing.get("ok"):
        return 0

    QQuickStyle.setStyle(QML_STYLE)
    app = QApplication([sys.argv[0], *qt_args])
    from . import diagnostics

    diagnostics.install()
    app.setApplicationName("Hallucinate")
    app.setOrganizationName("hallucinate")
    app.setApplicationDisplayName("Hallucinate")
    app.setDesktopFileName(os.environ.get("FLATPAK_ID", "hallucinate"))  # must match the installed .desktop
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("io.github.phosphene_dev.Hallucinate")
    icon = HERE / "assets" / ("hallucinate.ico" if sys.platform == "win32" else "hallucinate.png")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    control = ControlServer()
    if not control.listen():
        return 0
    from . import crashlog

    crash_dir = paths.data_dir() / "crash"
    last_crash, last_crashed = crashlog.take_previous(crash_dir)
    crashlog.install(crash_dir)

    from PySide6.QtCore import QSettings

    from .migrate import migrate_legacy
    try:
        migrate_legacy(
            paths.data_dir(), paths.config_dir(), paths.legacy_locations(),
            QSettings("hallucinate", "hallucinate"), paths.cache_dir(),
        )
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("Legacy data migration failed")

    from .core import net
    net.set_offline(QSettings("hallucinate", "hallucinate").value("privacy/offline", False, bool))

    # A short GIL switch interval keeps the GUI thread responsive while worker threads parse tags.
    sys.setswitchinterval(0.001)
    from . import dbguard
    backup_dir = paths.data_dir() / "backups"
    db_notice = dbguard.check(paths.db_path(), backup_dir)  # a damaged database is set aside and restored
    library = Library(paths.db_path(), paths.art_dir())
    dbguard.backup_if_due(paths.db_path(), backup_dir)
    from . import cachetrim
    cachetrim.trim_in_background({paths.data_dir() / "thumbs": cachetrim.LIMITS["thumbs"],
                                  paths.cache_dir() / "waveforms": cachetrim.LIMITS["waveforms"]})
    control.setLibrary(library)
    player = Player(session_file=paths.data_dir() / "session.json")
    waveforms = WaveformService(paths.cache_dir() / "waveforms")
    player.setWaveformService(waveforms)
    control.setPlayer(player)
    library.setPlayer(player)
    user_lib = UserLibrary(paths.db_path(), player)
    library.reloaded.connect(user_lib.refresh)
    meta_editor = MetadataEditor(paths.db_path(), paths.art_dir())
    meta_editor.changed.connect(library.reload)
    replay_gain = ReplayGainAnalyzer(paths.db_path())
    replay_gain.finished.connect(library.reload)
    headphones = HeadphoneFinder(paths.cache_dir(), player)
    lyrics = LyricsController(paths.db_path(), player)
    scrobbler = LastFmScrobbler(player, paths.data_dir())
    listenbrainz = ListenBrainzScrobbler(player, paths.data_dir(), user_lib)
    theme_manager = ThemeManager(paths.config_dir(), player)

    discord = DiscordPresence(player)
    shell = DesktopShell(app, player, app.windowIcon())
    shell.setReportSources(library=library, theme_manager=theme_manager)
    shell.setStartupNotice(db_notice)
    shell.setCrashReport(last_crash, last_crashed)

    if not library.folders and not args.folders:
        # A fresh install: open on the welcome (music folder, theme, scrobbling) until it is finished
        shell.setUiValue("welcome", "1")
    for f in args.folders:
        library.addFolder(f)
    if not library.folders:
        music = Path.home() / "Music"
        if music.is_dir():
            library.addFolder(str(music))
    QTimer.singleShot(0, library.rescan)
    player.restoreSession()

    engine = QQmlApplicationEngine()
    from . import qmlnet
    qmlnet.install(engine)  # the interface never goes online (see qmlnet)
    engine.addImageProvider("art", ArtProvider(paths.data_dir() / "thumbs"))
    ctx = engine.rootContext()
    ctx.setContextProperty("library", library)
    ctx.setContextProperty("player", player)
    ctx.setContextProperty("userLib", user_lib)
    ctx.setContextProperty("metaEditor", meta_editor)
    ctx.setContextProperty("replayGain", replay_gain)
    ctx.setContextProperty("headphones", headphones)
    ctx.setContextProperty("lyricsCtl", lyrics)
    ctx.setContextProperty("scrobbler", scrobbler)
    ctx.setContextProperty("listenbrainz", listenbrainz)
    ctx.setContextProperty("shell", shell)
    ctx.setContextProperty("discord", discord)
    ctx.setContextProperty("themeManager", theme_manager)
    engine.addImportPath(str(HERE / "qml"))
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "main.qml")))
    if not engine.rootObjects():
        control.close()
        return 1

    shell.setWindow(engine.rootObjects()[0])
    control.setRaiseCallback(shell.showMain)
    mpris = None
    try:
        if not sys.platform.startswith("linux"):
            raise RuntimeError("only available on Linux")
        from .mpris import MprisService

        window = engine.rootObjects()[0]
        mpris = MprisService(player, lambda: (window.show(), window.raise_()), app.quit)
    except Exception as e:  # MPRIS is optional
        if sys.stderr is not None:
            print(f"MPRIS unavailable: {e}", file=sys.stderr)

    media_controls = None
    if sys.platform == "win32":
        from . import smtc

        media_controls = smtc.create(player)  # media overlay, lock screen and media keys; optional

    signal.signal(signal.SIGINT, lambda *_: app.quit())  # also valid on Windows
    if args.quit_after is not None:
        QTimer.singleShot(args.quit_after, app.quit)
    # Python needs to wake up periodically to handle SIGINT.
    tick = QTimer()
    tick.start(500)
    tick.timeout.connect(lambda: None)

    code = app.exec()
    control.close()
    del engine
    discord.shutdown()
    shell.shutdown()
    scrobbler.shutdown()
    listenbrainz.shutdown()
    del theme_manager
    if media_controls is not None:
        media_controls.shutdown()
    player.shutdown()
    waveforms.shutdown()
    replay_gain.shutdown()
    headphones.shutdown()
    lyrics.shutdown()
    meta_editor.shutdown()
    user_lib.shutdown()
    library.shutdown()
    del scrobbler, listenbrainz
    del mpris
    crashlog.finish()
    return code


if __name__ == "__main__":
    sys.exit(main())
