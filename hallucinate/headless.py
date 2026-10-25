"""`hallucinate --headless`: Hallucinate without a window, for a home server, a NAS, a Raspberry Pi, a container
or a Proxmox LXC. It plays through the machine's own sound output and is driven from the web interface on
your phone or another computer, or from the command line (`hallucinate cmd`, `hallucinate tui`).

What runs: the library (watching its folders), the player, likes, ratings, playlists and listening history,
Last.fm and ListenBrainz scrobbling (as set up), ReplayGain analysis, music servers and their kept copies, and
the web remote, which is switched on. What doesn't: anything that is only for a window (themes, visualizers,
waveforms, lyrics display, desktop media controls). The data folders are the same as the desktop app's, so a
library made one way works the other.

It stops cleanly on Ctrl+C or SIGTERM (systemd, docker stop)."""
import logging
import signal
import sys

from PySide6.QtCore import QCoreApplication, QSettings, QTimer

from .control import ControlServer

logger = logging.getLogger(__name__)


def say(text):
    if sys.stdout is not None:
        print(text, flush=True)


def run(args):
    from . import __version__

    app = QCoreApplication([sys.argv[0]])
    app.setApplicationName("Hallucinate")
    app.setOrganizationName("hallucinate")

    control = ControlServer()
    if not control.listen():
        say("Hallucinate is already running here. Control it with `hallucinate cmd` or its web interface.")
        return 1

    from . import crashlog, dbguard
    from .core import net, paths

    crash_dir = paths.data_dir() / "crash"
    crashlog.take_previous(crash_dir)
    crashlog.install(crash_dir)
    settings = QSettings("hallucinate", "hallucinate")
    net.set_offline(settings.value("privacy/offline", False, bool))
    sys.setswitchinterval(0.001)

    backup_dir = paths.data_dir() / "backups"
    streams_db = paths.data_dir() / "streams.db"
    for notice in (dbguard.check(paths.db_path(), backup_dir), dbguard.check(streams_db, backup_dir)):
        if notice:
            say(notice)

    from .library import Library
    from .listenbrainz import ListenBrainzScrobbler
    from .offline import OfflineCopies
    from .player import Player
    from .replaygain import ReplayGainAnalyzer
    from .scrobbling import LastFmScrobbler
    from .servers import Servers
    from .userlib import UserLibrary
    from .webserver import WebRemote

    library = Library(paths.db_path(), paths.art_dir())
    dbguard.backup_if_due(paths.db_path(), backup_dir)
    dbguard.backup_if_due(streams_db, backup_dir)
    control.setLibrary(library)
    player = Player(session_file=paths.data_dir() / "session.json")
    control.setPlayer(player)
    library.setPlayer(player)
    user_lib = UserLibrary(paths.db_path(), player)
    library.reloaded.connect(user_lib.refresh)
    replay_gain = ReplayGainAnalyzer(paths.db_path())
    replay_gain.finished.connect(library.reload)
    library.scanFinished.connect(replay_gain.after_scan)
    scrobbler = LastFmScrobbler(player, paths.data_dir())
    listenbrainz = ListenBrainzScrobbler(player, paths.data_dir(), user_lib)
    user_lib.likeChanged.connect(scrobbler.love)
    servers = Servers(paths.db_path(), paths.art_dir(), player)
    from .shell import FEATURES

    servers.setEnabled(settings.value("features/servers", FEATURES["servers"], bool))
    servers.libraryChanged.connect(library.reload)
    server_copies = OfflineCopies(paths.db_path(), paths.data_dir() / "server-copies")
    library.changed.connect(server_copies.tidy)
    server_copies.resumeNetwork()

    web = WebRemote(paths.data_dir(), paths.data_dir() / "thumbs", player, library, user_lib)
    control.setApi(web.api)
    control.setWebRemote(web)
    # The web remote is how a headless Hallucinate is used: on, unless asked not to
    web.configure(enabled=not args.no_web, lan=args.network, port=args.port)

    for folder in args.folders:
        library.addFolder(folder)
    QTimer.singleShot(0, library.rescan)
    player.restoreSession()

    say(f"Hallucinate {__version__} is running without a window.")
    folders = library.folders
    say("Music folders: " + (", ".join(folders) if folders else
                             "none yet; add one with `hallucinate --headless /path/to/music`"))
    if web.running:
        say("Web interface: " + "  ".join(web.addresses()))
        if not web.lan:
            say("  (this computer only; add --network to reach it from your phone)")
        if not web.devices.listing():
            say("Pair a phone or browser: run `hallucinate --pair` here and enter the code it shows.")
    elif web.enabled:
        say("The web interface didn't start: " + (web.error or "unknown problem"))
    say("Command line: `hallucinate cmd status` (and `hallucinate cmd --help`). Stop with Ctrl+C.")

    def stop(*_):
        app.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    if args.quit_after is not None:
        QTimer.singleShot(args.quit_after, app.quit)
    tick = QTimer()  # Python needs to wake now and then to see a signal
    tick.start(500)
    tick.timeout.connect(lambda: None)

    code = app.exec()
    say("Stopping…")
    control.close()
    web.shutdown()
    scrobbler.shutdown()
    listenbrainz.shutdown()
    player.shutdown()
    replay_gain.shutdown()
    servers.shutdown()
    server_copies.shutdown()
    user_lib.shutdown()
    library.shutdown()
    dbguard.mark_clean(paths.db_path())
    dbguard.mark_clean(streams_db)
    crashlog.finish()
    return code
