"""Desktop integration: system tray icon, close-to-tray and the mini player window."""
import os
import sqlite3
import sys
import time

from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .core import net

VISUALIZER_STYLES = ("liquid", "aurora", "nebula", "halo", "waves", "bars")
# What closing the main window does. "tray" needs a visible tray icon; without one it quits.
CLOSE_ACTIONS = ("ask", "quit", "minimize", "tray")
# Parts of the app that can be switched off in Settings → Features, and whether they're on to begin with. A
# feature that's off is gone everywhere: the sidebar, Ctrl+K, menus, Home and its shortcuts.
FEATURES = {
    "liked": True, "folders": True, "stats": True, "history": True, "recap": True, "visualizer": True,
    "health": True, "lyrics": True, "stations": False, "podcasts": False, "servers": False,
    "homeRandom": True, "homeListening": True, "homeFacts": True, "homeShelves": True,
}
# The sidebar's pages in their usual order; people can rearrange them (Settings → Appearance or right-click).
SIDEBAR_PAGES = ("home", "albums", "artists", "songs", "folders", "liked", "stats", "history", "recap", "visualizer",
                 "stations", "podcasts")


def sidebar_order(saved):
    """The saved order with anything unknown dropped and any page it lacks (new in an update) put back where it
    usually goes."""
    order = [p for p in dict.fromkeys(saved or []) if p in SIDEBAR_PAGES]
    for i, page in enumerate(SIDEBAR_PAGES):
        if page not in order:
            before = [p for p in SIDEBAR_PAGES[:i] if p in order]
            order.insert(order.index(before[-1]) + 1 if before else 0, page)
    return order


# masterBadge: the Hi-Res badge as a gold M ("Master", as some stores mark it) instead of a "Hi-Res" pill
SONG_BADGES = {"explicitBadges": True, "hiResBadges": True, "bitDepth": False, "masterBadge": False}

# Tiling compositors and window managers that have no minimize: offering it there would do nothing.
NO_MINIMIZE = ("hyprland", "sway", "i3", "niri", "river", "dwm", "bspwm", "qtile", "awesome")


def can_minimize(env=None, platform=None):
    env = os.environ if env is None else env
    if not (platform or sys.platform).startswith("linux"):
        return True
    if env.get("HYPRLAND_INSTANCE_SIGNATURE") or env.get("SWAYSOCK") or env.get("I3SOCK") or env.get("NIRI_SOCKET"):
        return False
    desktops = env.get("XDG_CURRENT_DESKTOP", "").lower().replace(";", ":").split(":")
    return not any(d in NO_MINIMIZE for d in desktops)


# Desktops whose compositor draws good window frames itself (KDE's KWin, COSMIC), and X11, where every window
# manager does: their own title bar is the better default there. GNOME on Wayland leaves frames to the app
# (Qt's own is plain), and tiling compositors (Hyprland, niri, Sway) draw none: the built-in one is the default.
OWN_FRAMES = ("kde", "cosmic", "lxqt")


def default_title_bar(env=None, platform=None):
    env = os.environ if env is None else env
    if not (platform or sys.platform).startswith("linux"):
        return False
    if env.get("XDG_SESSION_TYPE", "").lower() == "x11" or (env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY")):
        return False
    desktops = env.get("XDG_CURRENT_DESKTOP", "").lower().replace(";", ":").split(":")
    return not any(d in OWN_FRAMES for d in desktops)


class DesktopShell(QObject):
    miniChanged = Signal()
    settingsChanged = Signal()
    navigateRequested = Signal(str)  # a page picked in the tray menu

    def __init__(self, app, player, icon: QIcon, parent=None):
        super().__init__(parent)
        self._app = app
        self._player = player
        self._window = None
        self._mini = False
        self._settings = QSettings("hallucinate", "hallucinate")
        self._tray_pref = self._settings.value("shell/tray", True, bool)
        # Before 0.9 there was only "keep playing in the tray"; anyone who turned it on keeps it.
        legacy = "tray" if self._settings.value("shell/closeToTray", False, bool) else "ask"
        self._close_action = str(self._settings.value("shell/closeAction", legacy))
        if self._close_action not in CLOSE_ACTIONS:
            self._close_action = "ask"
        self._desktop_notifications = self._settings.value("shell/desktopNotifications", False, bool)
        # only while the window isn't in front (it already shows the song), or every time
        self._notify_always = self._settings.value("shell/notifyAlways", False, bool)
        self._sidebar_collapsed = self._settings.value("ui/sidebarCollapsed", False, bool)
        self._ambient_motion = self._settings.value("ui/ambientMotion", True, bool)
        # An album may have several genres: albums and artists show them all, a song only its album's main one
        self._all_genres_albums = self._settings.value("ui/allGenresAlbums", True, bool)
        self._all_genres_songs = self._settings.value("ui/allGenresSongs", False, bool)
        self._reduce_motion = self._settings.value("ui/reduceMotion", False, bool)
        # The window's title bar drawn into the window itself (Linux, where Qt otherwise draws its own plain one on
        # Wayland compositors without server-side decorations), or the system's; and whether it has a minimize
        self._title_bar = self._settings.value("ui/customTitleBar", default_title_bar(), bool)
        side = str(self._settings.value("ui/titleBarSide", "right"))
        self._title_side = side if side in ("left", "right") else "right"
        self._title_minimize = self._settings.value("ui/titleBarMinimize", can_minimize(), bool)
        # How far a notch of the mouse wheel scrolls, as a multiple of the usual distance (see WheelScroll.qml)
        self._scroll_speed = self._float_ui("ui/scrollSpeed", 1.0, 0.25, 4.0)
        # Badges on songs: E for explicit lyrics, Hi-Res for 24-bit and up, and (off to begin with) every bit depth
        self._badges = {name: self._settings.value(f"ui/{name}", on, bool) for name, on in SONG_BADGES.items()}
        self._visualizer_style = str(self._settings.value("ui/visualizerStyle", "liquid"))
        self._now_playing_vinyl = self._settings.value("ui/nowPlayingVinyl", False, bool)
        self._features = {name: self._settings.value(f"features/{name}", on, bool) for name, on in FEATURES.items()}
        if self._visualizer_style not in VISUALIZER_STYLES:
            self._visualizer_style = "liquid"
        self._tray = None
        self._menu = None
        self._icon = icon
        self._started = time.monotonic()
        self._told_background = False
        from .notifications import Notifier

        self._notifier = Notifier()
        from .updates import UpdateChecker

        self._updates = UpdateChecker(self)
        self._build_tray()
        player.stateChanged.connect(self._refresh)
        player.trackChanged.connect(self._refresh)
        player.trackChanged.connect(self._on_track_changed)

    # --- tray -------------------------------------------------------------------------
    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self._icon, self)
        menu = QMenu()
        self._act_toggle = QAction("Play", menu)
        self._act_toggle.triggered.connect(self._player.toggle)
        prev, nxt = QAction("Previous", menu), QAction("Next", menu)
        prev.triggered.connect(self._player.previous)
        nxt.triggered.connect(self._player.next)
        show, mini, quit_ = QAction("Show Hallucinate", menu), QAction("Mini player", menu), QAction("Quit", menu)
        show.triggered.connect(self.showMain)
        mini.triggered.connect(self.toggleMini)
        quit_.triggered.connect(self._app.quit)
        # Go to: the sidebar's pages, in its order, without the ones switched off (rebuilt each time it opens)
        self._goto = QMenu("Go to", menu)
        self._goto.aboutToShow.connect(self._fill_goto)
        self._fill_goto()
        for a in (show, mini, None, self._act_toggle, prev, nxt, None):
            menu.addSeparator() if a is None else menu.addAction(a)
        menu.addMenu(self._goto)
        menu.addSeparator()
        menu.addAction(quit_)
        self._menu = menu  # keep alive
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.setVisible(self._tray_pref)
        self._refresh()
        self._sync_quit_policy()

    PAGE_TITLES = {"home": "Home", "albums": "Albums", "artists": "Artists", "songs": "Songs", "folders": "Folders",
                   "liked": "Liked Songs", "stats": "Stats", "history": "History", "recap": "Recap",
                   "visualizer": "Visualizer", "stations": "Internet radio", "podcasts": "Podcasts",
                   "settings": "Settings"}

    def _fill_goto(self):
        self._goto.clear()
        for page in [*self.sidebarOrder, "settings"]:
            if self._shown(page):
                self._goto.addAction(self.PAGE_TITLES.get(page, page.title())).triggered.connect(
                    lambda _=False, p=page: self.goTo(p))

    @Slot(str)
    def goTo(self, page):
        """Bring the window back and open a page (the tray menu's Go to)."""
        self.showMain()
        self.navigateRequested.emit(page)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._window is not None and self._window.isVisible() and not self._mini:
                self._window.hide()
            else:
                self.showMain()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self._player.toggle()

    def _refresh(self):
        if self._tray is None:
            return
        self._act_toggle.setText("Pause" if self._player.playing else "Play")
        cur = self._player.current if self._player.hasTrack else {}
        self._tray.setToolTip(f"{cur['title']} — {cur['artist']}" if cur else "Hallucinate")

    def _tray_visible(self):
        return self._tray is not None and self._tray.isVisible()

    def _sync_quit_policy(self):
        self._app.setQuitOnLastWindowClosed(not self._tray_visible())

    def setWindow(self, window):
        self._window = window

    # --- properties ---------------------------------------------------------------------
    @Property(bool, constant=True)
    def trayAvailable(self):
        return self._tray is not None

    @Property(bool, notify=settingsChanged)
    def trayEnabled(self):
        return self._tray_pref

    @Property(str, notify=settingsChanged)
    def closeAction(self):
        return self._close_action

    @Property(bool, constant=True)
    def canMinimize(self):
        """False under tiling window managers that have no minimize (Hyprland, Sway, i3…)."""
        return can_minimize()

    @Slot(str)
    def setCloseAction(self, action):
        if action in CLOSE_ACTIONS:
            self._close_action = action
            self._settings.setValue("shell/closeAction", action)
            self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def desktopNotifications(self):
        return self._desktop_notifications

    @Property(bool, notify=settingsChanged)
    def sidebarCollapsed(self):
        return self._sidebar_collapsed

    @Slot(bool)
    def setSidebarCollapsed(self, on):
        self._sidebar_collapsed = bool(on)
        self._settings.setValue("ui/sidebarCollapsed", self._sidebar_collapsed)
        self.settingsChanged.emit()

    sidebarOrderChanged = Signal()

    @Property("QStringList", notify=sidebarOrderChanged)
    def sidebarOrder(self):
        raw = self._settings.value("ui/sidebarOrder", "")
        return sidebar_order([p for p in str(raw or "").split(",") if p])

    @Slot("QStringList")
    def setSidebarOrder(self, order):
        order = sidebar_order(list(order))
        if order == list(SIDEBAR_PAGES):
            self._settings.remove("ui/sidebarOrder")
        else:
            self._settings.setValue("ui/sidebarOrder", ",".join(order))
        self.sidebarOrderChanged.emit()

    def _shown(self, page):
        return page not in FEATURES or self.featureOn(page)

    @Slot(str, int)
    def placeSidebarPage(self, page, index):
        """Put a page at `index` among the pages showing (as dragged in the sidebar). Switched-off pages keep
        their places for when they come back."""
        order = self.sidebarOrder
        shown = [p for p in order if self._shown(p)]
        if page not in shown:
            return
        shown.remove(page)
        shown.insert(max(0, min(index, len(shown))), page)
        slots = iter(shown)
        self.setSidebarOrder([next(slots) if self._shown(p) else p for p in order])

    @Slot(str, int)
    def moveSidebarPage(self, page, step):
        """Move a page up (-1) or down (+1) past the next one that's showing."""
        shown = [p for p in self.sidebarOrder if self._shown(p)]
        if page in shown:
            self.placeSidebarPage(page, shown.index(page) + (1 if step > 0 else -1))

    @Slot()
    def resetSidebarOrder(self):
        self.setSidebarOrder(list(SIDEBAR_PAGES))

    featuresChanged = Signal()

    @Property("QVariantMap", notify=featuresChanged)
    def features(self):
        """Which optional parts of the app are on, by name (see FEATURES)."""
        return dict(self._features)

    @Slot(str, bool)
    def setFeature(self, name, on):
        if name in FEATURES and self._features[name] != bool(on):
            self._features[name] = bool(on)
            self._settings.setValue(f"features/{name}", bool(on))
            self.featuresChanged.emit()

    def featureOn(self, name):
        return self._features.get(name, False)

    def setStartupNotice(self, text):
        self._startup_notice = text or ""

    @Property(str, constant=True)
    def startupNotice(self):
        """Something the user should hear about as the window opens (a restored database), or ""."""
        return getattr(self, "_startup_notice", "")

    @Property(bool, notify=settingsChanged)
    def offlineMode(self):
        """No internet at all: lyrics and cover lookups, scrobbling, EQ downloads and update checks stay off,
        and scrobbles wait in their queues until it's turned off again."""
        return net.is_offline()

    @Slot(bool)
    def setOfflineMode(self, on):
        net.set_offline(on)
        self._settings.setValue("privacy/offline", bool(on))
        self.settingsChanged.emit()
        self._updates.changed.emit()

    @Property(bool, notify=settingsChanged)
    def ambientMotion(self):
        """Whether the ambient backdrop drifts (off: it stays still, for less motion and lower power use)."""
        return self._ambient_motion

    @Slot(bool)
    def setAmbientMotion(self, on):
        self._ambient_motion = bool(on)
        self._settings.setValue("ui/ambientMotion", self._ambient_motion)
        self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def allGenresAlbums(self):
        """Album and artist pages show every genre (off: only the main one)."""
        return self._all_genres_albums

    @Slot(bool)
    def setAllGenresAlbums(self, on):
        self._all_genres_albums = bool(on)
        self._settings.setValue("ui/allGenresAlbums", self._all_genres_albums)
        self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def allGenresSongs(self):
        """A song (in Now Playing) shows all its album's genres (off: only the main one)."""
        return self._all_genres_songs

    @Slot(bool)
    def setAllGenresSongs(self, on):
        self._all_genres_songs = bool(on)
        self._settings.setValue("ui/allGenresSongs", self._all_genres_songs)
        self.settingsChanged.emit()

    @Slot(str, bool, result=str)
    def genresText(self, text, all_of_them):
        """How a song's or album's genres read: "IDM, Ambient, Electronic", or just the main one."""
        from .core import genres

        names = genres.split(text)
        return ", ".join(names if all_of_them else names[:1])

    @Property(bool, notify=settingsChanged)
    def reduceMotion(self):
        """Keep movement to a minimum: no page transitions, zooms, spinning record, hover growth or drifting
        backdrop (for motion sensitivity, or just a calmer window)."""
        return self._reduce_motion

    @Slot(bool)
    def setReduceMotion(self, on):
        self._reduce_motion = bool(on)
        self._settings.setValue("ui/reduceMotion", self._reduce_motion)
        self.settingsChanged.emit()

    def _float_ui(self, key, default, low, high):
        try:
            value = float(self._settings.value(key, default))
        except (TypeError, ValueError):
            return default
        return min(high, max(low, value)) if value == value else default  # NaN: the default

    @Property(float, notify=settingsChanged)
    def scrollSpeed(self):
        """How far the mouse wheel scrolls lists and pages: 1 is the usual distance a notch."""
        return self._scroll_speed

    @Slot(float)
    def setScrollSpeed(self, speed):
        self._scroll_speed = min(4.0, max(0.25, float(speed))) if speed == speed else 1.0
        self._settings.setValue("ui/scrollSpeed", self._scroll_speed)
        self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def customTitleBar(self):
        """The title bar built into the window (move, maximize, minimize, close) instead of the system's."""
        return self._title_bar

    @Slot(bool)
    def setCustomTitleBar(self, on):
        self._title_bar = bool(on)
        self._settings.setValue("ui/customTitleBar", self._title_bar)
        self.settingsChanged.emit()

    @Property(str, notify=settingsChanged)
    def titleBarSide(self):
        """Where the built-in title bar's buttons go: "right" (Windows, KDE, GNOME) or "left" (macOS-style)."""
        return self._title_side

    @Slot(str)
    def setTitleBarSide(self, side):
        if side in ("left", "right"):
            self._title_side = side
            self._settings.setValue("ui/titleBarSide", side)
            self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def titleBarMinimize(self):
        """Whether the built-in title bar has a minimize button (off to begin with where minimize does nothing)."""
        return self._title_minimize

    @Slot(bool)
    def setTitleBarMinimize(self, on):
        self._title_minimize = bool(on)
        self._settings.setValue("ui/titleBarMinimize", self._title_minimize)
        self.settingsChanged.emit()

    @Property("QVariantMap", notify=settingsChanged)
    def songBadges(self):
        """Which badges song rows and the player show: explicitBadges, hiResBadges, bitDepth, masterBadge."""
        return dict(self._badges)

    @Slot(str, bool)
    def setSongBadge(self, name, on):
        if name in SONG_BADGES:
            self._badges[name] = bool(on)
            self._settings.setValue(f"ui/{name}", bool(on))
            self.settingsChanged.emit()

    @Property(str, notify=settingsChanged)
    def visualizerStyle(self):
        """The visualizer look: one of VISUALIZER_STYLES."""
        return self._visualizer_style

    @Slot(str)
    def setVisualizerStyle(self, style):
        if style in VISUALIZER_STYLES and style != self._visualizer_style:
            self._visualizer_style = style
            self._settings.setValue("ui/visualizerStyle", style)
            self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def nowPlayingVinyl(self):
        """Whether Now Playing shows the record spinning out of its sleeve."""
        return self._now_playing_vinyl

    @Slot(bool)
    def setNowPlayingVinyl(self, on):
        self._now_playing_vinyl = bool(on)
        self._settings.setValue("ui/nowPlayingVinyl", self._now_playing_vinyl)
        self.settingsChanged.emit()

    crashReportChanged = Signal()

    def setCrashReport(self, text, crashed):
        self._crash_report, self._crashed = text or "", bool(crashed)
        self.crashReportChanged.emit()

    @Property(str, notify=crashReportChanged)
    def crashReport(self):
        """What went wrong in the previous run (see crashlog), until it's copied or dismissed; "" if nothing."""
        return getattr(self, "_crash_report", "")

    @Property(bool, notify=crashReportChanged)
    def lastRunCrashed(self):
        """Whether the previous run crashed, rather than only hitting an error it carried on from."""
        return getattr(self, "_crashed", False)

    @Slot(result=str)
    def copyCrashReport(self):
        """The debug info followed by the previous run's crash record, on the clipboard."""
        text = self.debugInfo() + "\n\nPrevious run\n" + self.crashReport
        self._app.clipboard().setText(text)
        self.dismissCrashReport()
        return text

    @Slot()
    def dismissCrashReport(self):
        self._crash_report = ""
        self.crashReportChanged.emit()

    def setReportSources(self, library=None, theme_manager=None):
        self._report_sources = {"library": library, "theme_manager": theme_manager}

    @Slot(result=str)
    def debugInfo(self):
        """Versions, platform, display, audio and the recent log, for bug reports (no personal paths)."""
        from . import diagnostics

        return diagnostics.report(player=self._player, window=self._window,
                                  **getattr(self, "_report_sources", {}))

    @Slot(str, result=bool)
    def openWebLink(self, url):
        """Open a link that came from outside (a station's website) in the browser, but only an http(s)
        address: a file:, smb: or custom-scheme link could run a program or leak a password hash. Returns
        whether it was opened."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from .core.stations import web_homepage

        safe = web_homepage(url)
        return bool(safe) and QDesktopServices.openUrl(QUrl(safe, QUrl.ParsingMode.StrictMode))

    @Slot(str)
    def copyText(self, text):
        self._app.clipboard().setText(text)

    @Slot(result=str)
    def copyDebugInfo(self):
        text = self.debugInfo()
        self._app.clipboard().setText(text)
        return text

    @Property(str, constant=True)
    def appVersion(self):
        from . import __version__

        return __version__

    @Slot(str, str, result=str)
    def uiValue(self, key, default):
        """A small remembered view choice (e.g. the Albums page layout), stored under ui/<key>."""
        return str(self._settings.value("ui/" + key, default))

    @Slot(str, str)
    def setUiValue(self, key, value):
        self._settings.setValue("ui/" + key, value)

    @Property(bool, notify=miniChanged)
    def miniOpen(self):
        return self._mini

    @Slot(bool)
    def setTrayEnabled(self, on):
        self._tray_pref = on
        self._settings.setValue("shell/tray", on)
        if self._tray is not None:
            self._tray.setVisible(on)
        self._sync_quit_policy()
        self.settingsChanged.emit()

    @Slot(bool)
    def setDesktopNotifications(self, on):
        self._desktop_notifications = on
        self._settings.setValue("shell/desktopNotifications", on)
        self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def notifyAlways(self):
        return self._notify_always

    @Slot(bool)
    def setNotifyAlways(self, on):
        self._notify_always = bool(on)
        self._settings.setValue("shell/notifyAlways", self._notify_always)
        self.settingsChanged.emit()

    def _in_front(self):
        """The main window is showing and has the keyboard: what's playing is already on screen."""
        win = self._window
        return bool(win is not None and not self._mini and win.isVisible() and win.isActive())

    def _on_track_changed(self):
        if time.monotonic() - self._started < 3:
            return  # the song brought back from last time, not a change
        if not self._desktop_notifications or not self._player.hasTrack:
            return
        if not self._notify_always and self._in_front():
            return
        track = self._player.current
        title = track.get("title") or "Unknown track"
        body = " — ".join(x for x in (track.get("artist", ""), track.get("album", "")) if x)
        art = str(track.get("artUrl") or "")
        self._send_notification(title, body, key="track", image=art if art.startswith("file://") else "")

    # --- backup ---------------------------------------------------------------------------------------------
    def setBackupSources(self, library_db, streams_db, after_restore):
        self._backup = (library_db, streams_db, after_restore)

    @Slot(str, result=str)
    def exportBackup(self, url):
        """Write a backup of your own data (see core/backup); returns what happened, for a toast."""
        from PySide6.QtCore import QUrl

        from .core import backup

        library_db, streams_db, _ = getattr(self, "_backup", (None, None, None))
        if library_db is None:
            return "Backups aren't available here"
        path = QUrl(url).toLocalFile() if url.startswith("file:") else url
        if not path.endswith(".hallucinate-backup"):
            path += ".hallucinate-backup"
        try:
            s = backup.export(library_db, streams_db, path)
        except (OSError, ValueError, sqlite3.Error) as exc:
            return f"Couldn't save the backup: {exc}"
        return (f"Backed up {s['likes']} likes, {s['ratings']} ratings, {s['playlists']} playlists, "
                f"{s['listens']} listens, {s['stations']} stations and {s['podcasts']} shows")

    @Slot(str, result=str)
    def importBackup(self, url):
        from PySide6.QtCore import QUrl

        from .core import backup

        library_db, streams_db, after = getattr(self, "_backup", (None, None, None))
        if library_db is None:
            return "Backups aren't available here"
        path = QUrl(url).toLocalFile() if url.startswith("file:") else url
        try:
            s = backup.restore(backup.read(path), library_db, streams_db)
        except (OSError, ValueError, sqlite3.Error) as exc:
            return f"Couldn't restore that backup: {exc}"
        if after is not None:
            after()
        return (f"Restored {s['likes']} likes, {s['ratings']} ratings, {s['playlists']} playlists, "
                f"{s['listens']} listens, {s['stations']} stations and {s['podcasts']} shows")

    whatsNewChanged = Signal()

    @Property("QStringList", notify=whatsNewChanged)
    def whatsNew(self):
        """This version's highlights, once, after an update from an earlier one ([] on a first start, after it's
        been seen, or when there's nothing to say)."""
        from . import __version__
        from .whatsnew import highlights

        seen = str(self._settings.value("ui/lastVersion", "") or "")
        if seen == __version__ or self._whats_new_dismissed:
            return []
        if not seen:  # a first start: nothing is "new" yet
            self._settings.setValue("ui/lastVersion", __version__)
            return []
        return highlights(__version__)

    @Slot()
    def dismissWhatsNew(self):
        from . import __version__

        self._whats_new_dismissed = True
        self._settings.setValue("ui/lastVersion", __version__)
        self.whatsNewChanged.emit()

    _whats_new_dismissed = False

    @Slot(str, str)
    def notify(self, title, body):
        """A desktop notification (new podcast episodes); shown whatever the now-playing setting says."""
        self._send_notification(title, body)

    def _send_notification(self, title, artist, key="", image=""):
        if sys.platform.startswith("linux") and self._notifier.send(title, artist, key=key, image=image):
            return
        if self._tray is not None:
            self._tray.showMessage(
                title, artist, QSystemTrayIcon.MessageIcon.Information, 5000
            )

    # --- windows --------------------------------------------------------------------------
    @Slot()
    def showMain(self):
        if self._mini:
            self._mini = False
            self.miniChanged.emit()
        if self._window is not None:
            self._sync_quit_policy()  # back from the background: closing it can quit again
            self._window.show()
            self._window.raise_()
            self._window.requestActivate()

    @Slot()
    def toggleMini(self):
        if self._mini:
            self.showMain()
            return
        self._mini = True
        self.miniChanged.emit()
        if self._window is not None:
            self._window.hide()

    @Slot(result=str)  # one signature only: with a second (result=bool) QML got True back, never "ask"
    def handleClose(self):
        """Called when the main window is closed. Returns "ask" (the window shows the choice and stays open),
        "quit", or "kept" (the window was minimized or hidden, the music goes on)."""
        if self._close_action == "ask":
            return "ask"
        return self.closeWith(self._close_action)

    @Slot(str, result=str)
    def closeWith(self, action):
        """Carry out a close choice: "minimize", "tray" (keep playing in the background: the window is hidden
        and comes back from the tray icon, by opening Hallucinate again, or from the desktop's media controls)
        or "quit"."""
        if action == "minimize" and not self.canMinimize:
            action = "tray"  # chosen on another desktop; hiding is the nearest thing here
        if action == "minimize" and self._window is not None:
            self._window.showMinimized()
            return "kept"
        if action == "tray" and self._window is not None:
            self._app.setQuitOnLastWindowClosed(False)
            self._window.hide()
            if not self._tray_visible() and not self._told_background:
                self._told_background = True  # no icon to find it by: say once how to get it back
                self.notify("Hallucinate is still playing",
                            "Open Hallucinate again to bring the window back.")
            return "kept"
        self._app.quit()
        return "quit"

    @Slot()
    def quit(self):
        self._app.quit()

    @Property(QObject, constant=True)
    def updates(self):
        """The optional new-version check (see updates.UpdateChecker)."""
        return self._updates

    def shutdown(self):
        self._updates.shutdown()
        if self._tray is not None:
            self._tray.hide()
