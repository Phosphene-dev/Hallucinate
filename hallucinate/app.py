import argparse
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from . import __version__
from .control import ControlServer, send_control
from .core import atomic, paths, remote  # noqa: F401 - atomic reads the umask before any threads start
from .core.i18n import fill, translate
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
_TRACE = bool(os.environ.get("HALLUCINATE_STARTUP_TRACE"))


def _mark(step):
    """With HALLUCINATE_STARTUP_TRACE set, print when each start-up step is reached (scripts/startup_check.py)."""
    if _TRACE and sys.stderr is not None:
        print(f"startup-trace {step} {time.time():.4f}", file=sys.stderr, flush=True)
# Our Qt Quick Controls style (qml/HallucinateStyle): the app's look for menus, dialogs, tooltips and text fields,
# with Qt's Basic style for everything else. Found through the qml/ import path.
QML_STYLE = "HallucinateStyle"


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv[:1] == ["--analysis-worker"]:  # the helper that decodes songs for waveforms and ReplayGain
        from .analysis import serve

        return serve()
    if argv[:1] == ["cmd"]:  # control a running Hallucinate from the command line
        from . import cli

        return cli.main(argv[1:])
    if argv[:1] == ["tui"]:  # the terminal version
        from . import tui

        return tui.main(argv[1:])
    ap = argparse.ArgumentParser(
        prog="hallucinate", description="A music player for the music you own.",
        epilog="Also: `hallucinate cmd …` controls a running Hallucinate from the command line (try "
               "`hallucinate cmd --help`), and `hallucinate tui` is the terminal version.")
    ap.add_argument("folders", nargs="*", help="music folders to add to the library")
    controls = ap.add_mutually_exclusive_group()
    controls.add_argument("--next", dest="control", action="store_const", const="next", help="skip to the next track")
    controls.add_argument("--prev", dest="control", action="store_const", const="prev", help="play the previous track")
    controls.add_argument("--play-pause", dest="control", action="store_const", const="play-pause", help="toggle playback")
    controls.add_argument("--mini-player", dest="control", action="store_const", const="mini-player",
                          help="switch between the mini player and the window")
    controls.add_argument("--quit", dest="control", action="store_const", const="quit", help="quit Hallucinate")
    controls.add_argument("--status", dest="control", action="store_const", const="status", help="print current playback status as JSON")
    controls.add_argument("--pair", dest="control", action="store_const", const="pair",
                          help="show a code to pair a phone or browser with the web interface")
    server = ap.add_argument_group("without a window (a home server, a container)")
    server.add_argument("--headless", action="store_true",
                        help="run without a window; use the web interface or `hallucinate cmd` to control it")
    server.add_argument("--network", action="store_true", default=None,
                        help="let other devices on your network reach the web interface (kept for next time)")
    server.add_argument("--port", type=int, help="the web interface's port (kept for next time; default 8483)")
    server.add_argument("--no-web", action="store_true", help="don't start the web interface")
    # the launcher's right-click actions: start Hallucinate when it isn't running, then do it
    ap.add_argument("--safe-mode", action="store_true",
                    help="start without the visualizer and moving effects (for a graphics driver that crashes)")
    ap.add_argument("--launch", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--quit-after", type=int, metavar="MS", help=argparse.SUPPRESS)
    ap.add_argument("--decode-check", nargs="+", metavar="FILE", help=argparse.SUPPRESS)  # packaging CI
    ap.add_argument("--version", action="version", version=__version__)
    args, qt_args = ap.parse_known_args(argv)

    if args.port is not None and not 1024 <= args.port <= 65535:
        ap.error("--port must be from 1024 to 65535")
    if args.decode_check:
        from . import decodecheck

        return decodecheck.main(args.decode_check)
    if args.control == "pair":
        from . import cli

        return cli.main(["pair"])
    launch_then = None
    if args.control:
        response = send_control(args.control)
        if response is None and args.launch and args.control not in ("status", "quit"):
            launch_then = args.control  # done once the window is up (below)
            response = {"ok": True, "starting": True}
        elif response is None and args.control == "quit":
            return 0  # nothing to quit
        if response is None:
            print("Hallucinate is not running; start it before using playback controls.", file=sys.stderr)
            return 1
        if not response.get("ok"):
            print(response.get("error", "Playback control failed."), file=sys.stderr)
            return 1
        if args.control == "status":
            print(json.dumps(response["status"], ensure_ascii=False))
        if launch_then is None:
            return 0

    if args.headless:
        from . import headless

        return headless.run(args)

    existing = (
        None if launch_then else
        send_control("add-folders", folders=args.folders)
        if args.folders
        else send_control("raise")
    )
    if existing is not None and existing.get("ok"):
        return 0

    _mark("imports")
    QQuickStyle.setStyle(QML_STYLE)
    # A window that can be see-through at its edges: with the built-in title bar its corners are rounded (#151)
    from PySide6.QtQuick import QQuickWindow

    QQuickWindow.setDefaultAlphaBuffer(True)
    app = QApplication([sys.argv[0], *qt_args])
    from . import diagnostics

    diagnostics.install()
    app.setApplicationName("Hallucinate")
    app.setOrganizationName("hallucinate")
    from .i18n import Translations

    translations = Translations(app)  # before anything makes text people read
    app.setApplicationDisplayName("Hallucinate")
    # the window's app id: docks find its icon through the launcher of that name. An AppImage uses the launcher
    # that starts it (AppImageLauncher's, Gear Lever's or our own: see desktopentry), when there is one.
    from . import desktopentry

    desktopentry.follow()
    app.setDesktopFileName(os.environ.get("FLATPAK_ID") or desktopentry.launcher_id() or "hallucinate")
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
    # Safe start: the last start-up never finished, so leave out what most often brings one down (the
    # visualizer's shaders on a bad graphics driver, the moving effects) for this run only
    safe_mode = bool(getattr(args, "safe_mode", False)) or crashlog.start_failed(crash_dir)
    crashlog.starting(crash_dir)

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
    streams_db = paths.data_dir() / "streams.db"
    db_notice = " ".join(n for n in (db_notice, dbguard.check(streams_db, backup_dir)) if n)
    _mark("application")
    library = Library(paths.db_path(), paths.art_dir())
    diagnostics.set_private_folders(library.folders)  # kept out of debug info and crash reports
    library.foldersChanged.connect(lambda: diagnostics.set_private_folders(library.folders))
    _mark("library-opened")
    dbguard.backup_if_due(paths.db_path(), backup_dir)
    dbguard.backup_if_due(streams_db, backup_dir)
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
    library.scanFinished.connect(replay_gain.after_scan)
    headphones = HeadphoneFinder(paths.cache_dir(), player)
    lyrics = LyricsController(paths.db_path(), player)
    scrobbler = LastFmScrobbler(player, paths.data_dir())
    listenbrainz = ListenBrainzScrobbler(player, paths.data_dir(), user_lib)
    import weakref

    from .onlinesources import OnlineSources

    lastfm = weakref.ref(scrobbler)  # (the scrobbler is let go of first at the end)
    sources = OnlineSources(lambda: lastfm()._api_key if lastfm() is not None else "")
    scrobbler.connectionChanged.connect(sources.lastfmChanged)
    meta_editor.setSources(sources, paths.data_dir())
    from .bios import ArtistBios

    artist_bios = ArtistBios(paths.db_path(), sources)
    from .similar import SimilarArtists

    similar_artists = SimilarArtists(paths.db_path(), sources, library)
    theme_manager = ThemeManager(paths.config_dir(), player)

    discord = DiscordPresence(player)
    shell = DesktopShell(app, player, app.windowIcon())
    shell.setReportSources(library=library, theme_manager=theme_manager)
    shell.setStartupNotice(db_notice)
    shell.setCrashReport(last_crash, last_crashed)
    if safe_mode:
        shell.setSafeMode(True)
    from .podcasts import Podcasts
    from .stations import Stations

    stations = Stations(paths.data_dir() / "streams.db", paths.cache_dir(), player)
    stations.setLibraryDb(paths.db_path())
    podcasts = Podcasts(paths.data_dir() / "streams.db", paths.data_dir(), paths.cache_dir(), player)
    from .spectrogram import Spectrograms

    spectrograms = Spectrograms(paths.db_path(), paths.cache_dir())
    from .servers import Servers

    servers = Servers(paths.db_path(), paths.art_dir(), player)
    from .offline import OfflineCopies

    server_copies = OfflineCopies(paths.db_path(), paths.data_dir() / "server-copies")
    library.changed.connect(server_copies.tidy)  # a server removed, or songs gone from it: their copies go too
    server_copies.resumeNetwork()
    servers.libraryChanged.connect(library.reload)
    from .webserver import WebRemote

    web_remote = WebRemote(paths.data_dir(), paths.data_dir() / "thumbs", player, library, user_lib)
    web_remote.api.stations, web_remote.api.podcasts = stations, podcasts  # their pages in the remote (#128)
    web_remote.api.lyrics = lyrics  # the playing song's lyrics in the remote
    control.setApi(web_remote.api)
    control.setWebRemote(web_remote)
    shell.settingsChanged.connect(servers.recheck)  # offline mode switched off: try servers again

    offline = [net.is_offline()]

    def offline_switched():
        """Offline mode stops what's already going online too, not only new connections: a stream playing,
        episode downloads (they wait, and carry on afterwards) and the radio's song-title checks."""
        if net.is_offline() == offline[0]:
            return
        offline[0] = net.is_offline()
        if offline[0]:
            podcasts.stopNetwork()
            stations.stopNetwork()
            server_copies.stopNetwork()
            path = str(player.current.get("path", "")) if player.hasTrack else ""
            # a stream, not a file here (a server song kept on this computer plays on)
            if path.startswith(("http://", "https://")) or remote.streamed(path):
                player.stop()
        else:
            podcasts.resumeNetwork()
            stations.resumeNetwork()
            server_copies.resumeNetwork()

    shell.settingsChanged.connect(offline_switched)

    def apply_features():
        lyrics.setEnabled(shell.featureOn("lyrics"))
        stations.setEnabled(shell.featureOn("stations"))
        podcasts.setEnabled(shell.featureOn("podcasts"))
        servers.setEnabled(shell.featureOn("servers"))

    apply_features()
    shell.featuresChanged.connect(apply_features)
    podcasts.newEpisodes.connect(lambda show, title: shell.notify(fill(translate("Podcasts", "New from %1"), show), title))

    def after_restore():
        library.reload()
        user_lib.refresh()
        user_lib.refreshStats()
        stations.refresh()
        podcasts.reload()
        library.rescan()  # folders and hidden songs from the backup take effect

    user_lib.likeChanged.connect(scrobbler.love)
    scrobbler.lovesImported.connect(user_lib.likeLoved)
    shell.setBackupSources(paths.db_path(), paths.data_dir() / "streams.db", after_restore)

    if not library.folders and not args.folders:
        # A fresh install: open on the welcome (music folder, theme, scrobbling) until it is finished
        shell.setUiValue("welcome", "1")
    for f in args.folders:
        library.addFolder(f)
    if not library.folders:
        music = Path.home() / "Music"
        if music.is_dir():
            library.addFolder(str(music))
    if library.scanAtStart or library.empty():
        QTimer.singleShot(0, library.rescan)
    player.restoreSession()
    if player.resumeOnStart and player.hasTrack:
        QTimer.singleShot(600, player.play)  # carry on where it was (Settings → Playback)

    _mark("services")
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
    ctx.setContextProperty("sources", sources)
    ctx.setContextProperty("artistBios", artist_bios)
    ctx.setContextProperty("similarArtists", similar_artists)
    ctx.setContextProperty("shell", shell)
    ctx.setContextProperty("i18n", translations)
    translations.setEngine(engine)
    translations.changed.connect(shell.retranslateTray)  # the tray menu is Qt widgets, not QML
    ctx.setContextProperty("discord", discord)
    ctx.setContextProperty("themeManager", theme_manager)
    ctx.setContextProperty("stations", stations)
    ctx.setContextProperty("servers", servers)
    ctx.setContextProperty("serverCopies", server_copies)
    ctx.setContextProperty("webRemote", web_remote)
    ctx.setContextProperty("podcasts", podcasts)
    ctx.setContextProperty("spectrograms", spectrograms)
    engine.addImportPath(str(HERE / "qml"))
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "main.qml")))
    if not engine.rootObjects():
        control.close()
        return 1

    _mark("window-loaded")
    if _TRACE:
        window = engine.rootObjects()[0]
        window.frameSwapped.connect(lambda: _mark("first-frame"), Qt.ConnectionType.SingleShotConnection)
        library.readyChanged.connect(lambda: library.ready and _mark("library-ready"))
    shell.setWindow(engine.rootObjects()[0])
    diagnostics.watch_graphics(engine.rootObjects()[0])
    # the start-up went fine once the window has drawn and stayed up for a while
    engine.rootObjects()[0].frameSwapped.connect(lambda: QTimer.singleShot(8000, lambda: crashlog.started(crash_dir)),
                                                 Qt.ConnectionType.SingleShotConnection)
    root_window = engine.rootObjects()[0]

    def freeze_context():
        cur = player.current if player.hasTrack else {}
        return (f"window {'shown' if root_window.isVisible() else 'hidden'}, {root_window.visibility().name}, "
                f"{root_window.width()}x{root_window.height()}, {'active' if root_window.isActive() else 'inactive'}; "
                f"{'playing' if player.playing else 'not playing'} {cur.get('kind') or ('music' if cur else 'nothing')}"
                f"{', ' + player.error if player.error else ''}")

    freeze_watch = crashlog.watch_freezes(context=freeze_context)  # noqa: F841 - kept alive for the run
    control.setRaiseCallback(shell.showMain)
    control.setShell(shell)
    if launch_then == "mini-player":
        QTimer.singleShot(0, shell.toggleMini)
    elif launch_then:  # play/pause, next, previous: on the queue the last session left
        QTimer.singleShot(0, {"play-pause": player.toggle, "next": player.next, "prev": player.previous}[launch_then])
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
    crashlog.stop_watching()  # the window is gone: a slow shutdown isn't a freeze
    control.close()
    del engine
    web_remote.shutdown()  # (before the player: remotes are told it's going)
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
    stations.shutdown()
    servers.shutdown()
    server_copies.shutdown()
    podcasts.shutdown()
    spectrograms.shutdown()
    meta_editor.shutdown()
    artist_bios.shutdown()
    similar_artists.shutdown()
    user_lib.shutdown()
    library.shutdown()
    dbguard.mark_clean(paths.db_path())  # every connection is closed now
    dbguard.mark_clean(paths.data_dir() / "streams.db")
    del scrobbler, listenbrainz
    del mpris
    crashlog.finish()
    from .player import still_opening

    if still_opening():
        # A stream or file still opening (a stuck lookup, a network share gone away) would keep the app
        # running, window closed, until it gives up. Everything is saved and closed by now: leave at once.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
