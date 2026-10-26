import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QIcon

from hallucinate.player import Player
from hallucinate.shell import DesktopShell


class FakeWindow:
    def __init__(self):
        self.visible, self.calls, self.active = True, [], False

    def isActive(self):
        return self.active

    def isVisible(self):
        return self.visible

    def show(self):
        self.visible = True
        self.calls.append("show")

    def hide(self):
        self.visible = False
        self.calls.append("hide")

    def raise_(self):
        self.calls.append("raise")

    def requestActivate(self):
        self.calls.append("activate")


@pytest.fixture
def make_shell(qapp, tmp_path, monkeypatch):
    """Build a shell and destroy its Qt objects when the test ends.

    Patch DesktopShell methods on the class, not the instance: undoing an instance patch stores a bound
    method in the instance dict, creating a reference cycle that the garbage collector later frees at an
    arbitrary point (observed as segfaults in unrelated worker-thread tests)."""
    made = []

    def make():
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        player = Player(session_file=tmp_path / "s.json")
        shell = DesktopShell(qapp, player, QIcon())
        shell._settings.clear()
        win = FakeWindow()
        shell.setWindow(win)
        made.append((shell, player))
        return shell, win, player

    yield make
    for shell, player in made:
        shell.shutdown()
        player.shutdown()
        shell.deleteLater()
        player.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_mini_player_toggle_hides_and_restores_main(make_shell):
    shell, win, player = make_shell()
    shell.toggleMini()
    assert shell.miniOpen and not win.visible
    shell.toggleMini()
    assert not shell.miniOpen and win.visible
    shell.toggleMini()
    shell.showMain()
    assert not shell.miniOpen and win.visible


def fake_app(quits):
    return type("A", (), {"quit": lambda self: quits.append(1), "setQuitOnLastWindowClosed": lambda *a: None})()


def test_close_asks_by_default_and_does_nothing_yet(make_shell):
    shell, win, _player = make_shell()
    quits = []
    shell._app = fake_app(quits)
    assert shell.closeAction == "ask"
    assert shell.handleClose() == "ask" and win.visible and not quits  # the window shows the choice


def test_close_choices(make_shell, monkeypatch):
    shell, win, _player = make_shell()
    quits = []
    shell._app = fake_app(quits)
    win.showMinimized = lambda: win.calls.append("minimize")

    shell.setCloseAction("minimize")
    assert shell.handleClose() == "kept" and win.calls[-1] == "minimize" and not quits

    told = []
    monkeypatch.setattr(DesktopShell, "notify", lambda self, title, body: told.append(title))
    shell.setCloseAction("tray")
    assert shell.handleClose() == "kept" and not win.visible and not quits  # no tray icon: in the background
    assert told == ["Hallucinate is still playing"]  # and says how to get it back, once
    shell.showMain()
    assert win.visible
    shell.handleClose()
    assert len(told) == 1
    shell.showMain()
    monkeypatch.setattr(DesktopShell, "_tray_visible", lambda self: True)
    assert shell.handleClose() == "kept" and not win.visible

    shell.setCloseAction("quit")
    quits.clear()
    assert shell.handleClose() == "quit" and quits
    shell.setCloseAction("nonsense")
    assert shell.closeAction == "quit"


def test_close_choice_persists_and_old_tray_setting_carries_over(make_shell):
    shell, _win, _player = make_shell()
    shell.setCloseAction("minimize")
    assert shell._settings.value("shell/closeAction") == "minimize"
    shell._settings.remove("shell/closeAction")
    shell._settings.setValue("shell/closeToTray", True)
    again, _w, _p = make_shell()
    assert again.closeAction == "tray"


def test_desktop_notifications_are_opt_in_and_skip_initial_track(make_shell, monkeypatch):
    shell, _, player = make_shell()
    shown = []
    monkeypatch.setattr(DesktopShell, "_send_notification",
                        lambda self, title, body, key="", image="": shown.append((title, body, key, image)))
    shell._player = type(
        "Playback",
        (),
        {"hasTrack": True, "current": {"title": "New song", "artist": "New artist", "album": "Record",
                                        "artUrl": "file:///covers/a.jpg"}},
    )()
    shell.setDesktopNotifications(True)
    shell._on_track_changed()
    assert shown == []  # just started: the song brought back from last time
    shell._started -= 10
    shell.setDesktopNotifications(False)
    shell._on_track_changed()
    assert shown == []
    shell.setDesktopNotifications(True)
    shell._on_track_changed()
    assert shown == [("New song", "New artist — Record", "track", "file:///covers/a.jpg")]


def test_no_notification_while_the_window_is_in_front_unless_asked(make_shell, monkeypatch):
    shell, win, _player = make_shell()
    shown = []
    monkeypatch.setattr(DesktopShell, "_send_notification", lambda self, title, body, key="", image="": shown.append(title))
    shell._player = type("Playback", (), {"hasTrack": True, "current": {"title": "Song"}})()
    shell._started -= 10
    shell.setDesktopNotifications(True)
    win.active = True
    shell._on_track_changed()
    assert shown == []  # the window already shows it
    shell.setNotifyAlways(True)
    shell._on_track_changed()
    assert shown == ["Song"]
    shell.setNotifyAlways(False)
    win.active = False
    shell._on_track_changed()
    assert shown == ["Song", "Song"]


def test_the_title_bar_default_follows_the_desktop(make_shell):
    from hallucinate.shell import default_title_bar

    wl = {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-1"}
    for desk in ("GNOME", "Hyprland", "niri", "sway", "ubuntu:GNOME"):
        assert default_title_bar({**wl, "XDG_CURRENT_DESKTOP": desk}, "linux"), desk
    for desk in ("KDE", "COSMIC"):
        assert not default_title_bar({**wl, "XDG_CURRENT_DESKTOP": desk}, "linux"), desk
    assert not default_title_bar({"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "GNOME"}, "linux")
    assert not default_title_bar({"DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "XFCE"}, "linux")
    assert not default_title_bar({}, "win32")

    shell, _win, _player = make_shell()
    assert shell.titleBarSide == "right"
    shell.setTitleBarSide("left")
    assert shell.titleBarSide == "left"
    shell.setTitleBarSide("middle")
    assert shell.titleBarSide == "left"


def test_notifications_go_out_with_the_types_the_spec_asks_for():
    """QtDBus sent the id as int32 and the lists untyped, which strict daemons (mako, dunst, swaync) refuse."""
    from jeepney import new_method_call

    from hallucinate import notifications

    args = notifications.notify_args("<b>Song</b>", "A & B <i>", replaces=7, image="file:///c.jpg")
    assert args[1] == 7 and args[3] == "<b>Song</b>" and args[4] == "A &amp; B &lt;i&gt;"
    assert args[6] == {"image-path": ("s", "file:///c.jpg")}
    msg = new_method_call(notifications.NOTIFICATIONS, "Notify", "susssasa{sv}i", args)
    assert b"susssasa{sv}i" in msg.serialise(serial=1)  # it serializes with the spec's signature


def test_sidebar_and_ambient_motion_preferences_persist(make_shell):
    from PySide6.QtCore import QSettings

    shell, _win, _player = make_shell()
    assert shell.sidebarCollapsed is False and shell.ambientMotion is True
    shell.setSidebarCollapsed(True)
    shell.setAmbientMotion(False)
    assert shell.sidebarCollapsed is True and shell.ambientMotion is False
    stored = QSettings("hallucinate", "hallucinate")
    assert stored.value("ui/sidebarCollapsed", type=bool) is True
    assert stored.value("ui/ambientMotion", type=bool) is False


def test_visualizer_style_and_vinyl_preferences_persist(make_shell):
    from PySide6.QtCore import QSettings

    shell, _win, _player = make_shell()
    assert shell.visualizerStyle == "liquid" and shell.nowPlayingVinyl is False
    shell.setVisualizerStyle("aurora")
    shell.setVisualizerStyle("not-a-style")  # ignored
    shell.setNowPlayingVinyl(True)
    assert shell.visualizerStyle == "aurora" and shell.nowPlayingVinyl is True
    stored = QSettings("hallucinate", "hallucinate")
    assert stored.value("ui/visualizerStyle") == "aurora"
    assert stored.value("ui/nowPlayingVinyl", type=bool) is True


def test_offline_mode_persists_and_closes_the_network(make_shell):
    from PySide6.QtCore import QSettings

    from hallucinate.core import net

    shell, _win, _player = make_shell()
    try:
        assert not shell.offlineMode
        shell.setOfflineMode(True)
        assert net.is_offline() and shell.offlineMode
        assert QSettings("hallucinate", "hallucinate").value("privacy/offline", False, bool)
        shell.setOfflineMode(False)
        assert not net.is_offline() and not shell.offlineMode
    finally:
        net.set_offline(False)


def test_no_minimize_on_tiling_window_managers(make_shell, monkeypatch):
    from hallucinate.shell import can_minimize

    assert not can_minimize({"HYPRLAND_INSTANCE_SIGNATURE": "x"}, "linux")
    assert not can_minimize({"XDG_CURRENT_DESKTOP": "sway"}, "linux")
    assert can_minimize({"XDG_CURRENT_DESKTOP": "KDE"}, "linux") and can_minimize({}, "win32")

    monkeypatch.setattr(DesktopShell, "canMinimize", property(lambda self: False))
    shell, win, _player = make_shell()
    quits = []
    shell._app = fake_app(quits)
    monkeypatch.setattr(DesktopShell, "notify", lambda self, title, body: None)
    # No minimize and no tray (Hyprland without a tray in the bar): it still asks, and can keep playing hidden
    assert shell.handleClose() == "ask" and not quits
    assert shell.closeWith("minimize") == "kept" and not win.visible  # a remembered minimize: the background


def test_features_are_remembered_and_new_kinds_start_off(make_shell):
    shell, _, _ = make_shell()
    assert shell.features["stats"] is True
    assert shell.features["stations"] is False and shell.features["podcasts"] is False
    seen = []
    shell.featuresChanged.connect(lambda: seen.append(1))
    shell.setFeature("stats", False)
    shell.setFeature("stats", False)
    shell.setFeature("nonsense", True)
    assert seen == [1] and not shell.featureOn("stats") and "nonsense" not in shell.features
    assert shell._settings.value("features/stats", True, bool) is False
    shell.setFeature("stats", True)  # the settings are shared by the whole test run


def test_whats_new_once_after_an_update(make_shell):
    from hallucinate import __version__
    from hallucinate.whatsnew import HIGHLIGHTS

    shell, _, _ = make_shell()
    assert __version__ in HIGHLIGHTS, "this version needs its highlights in whatsnew.py"
    assert shell.whatsNew == []  # a first start
    shell._settings.setValue("ui/lastVersion", "0.0.1")
    assert shell.whatsNew == HIGHLIGHTS[__version__]
    shell.dismissWhatsNew()
    assert shell.whatsNew == []


def test_sidebar_pages_can_be_rearranged(make_shell):
    from hallucinate.shell import SIDEBAR_PAGES, sidebar_order

    shell, _, _ = make_shell()
    assert shell.sidebarOrder == list(SIDEBAR_PAGES)
    shell.moveSidebarPage("songs", -1)
    assert shell.sidebarOrder[:4] == ["home", "albums", "songs", "artists"]
    shell.placeSidebarPage("history", 0)
    assert shell.sidebarOrder[0] == "history"
    # switched-off pages (radio and podcasts start off) keep their places and are stepped over
    shell.placeSidebarPage("visualizer", 99)
    order = shell.sidebarOrder
    assert order.index("visualizer") > order.index("recap") and order[-2:] == ["stations", "podcasts"]
    shell.setFeature("stations", True)
    shell.moveSidebarPage("stations", -1)
    assert shell.sidebarOrder.index("stations") < shell.sidebarOrder.index("visualizer")
    shell.setFeature("stations", False)
    shell.resetSidebarOrder()
    assert shell.sidebarOrder == list(SIDEBAR_PAGES) and not shell._settings.contains("ui/sidebarOrder")
    # a saved order from an older version: unknown pages dropped, a new one put after the page it usually follows
    old = [p for p in SIDEBAR_PAGES if p != "podcasts"][::-1] + ["gone"]
    assert sidebar_order(old) == ["stations", "podcasts", *old[1:-1]]  # podcasts usually follows stations
    assert sidebar_order(["songs", "home"])[:3] == ["songs", "folders", "liked"]
    assert sorted(sidebar_order(["songs"])) == sorted(SIDEBAR_PAGES)


def test_the_tray_menu_goes_to_the_sidebar_pages(make_shell):
    from PySide6.QtWidgets import QMenu

    shell, win, _player = make_shell()
    shell._goto = QMenu("Go to")  # the tray itself isn't built without a tray (as here, offscreen)
    shell._fill_goto()
    titles = [a.text() for a in shell._goto.actions()]
    assert titles[0] == "Home" and titles[-1] == "Settings" and "Liked Songs" in titles
    assert "Podcasts" not in titles  # switched off by default, as in the sidebar
    shell.setFeature("podcasts", True)
    shell._fill_goto()
    assert "Podcasts" in [a.text() for a in shell._goto.actions()]

    went = []
    shell.navigateRequested.connect(went.append)
    win.hide()
    next(a for a in shell._goto.actions() if a.text() == "Stats").trigger()
    assert went == ["stats"] and win.visible
    shell._goto.deleteLater()


def test_start_page(make_shell):
    shell, _win, _player = make_shell()
    assert shell.startPage == "home" and shell.openingPage() == "home"
    shell.setStartPage("albums")
    assert shell.openingPage() == "albums"
    shell.setStartPage("last")
    shell.setUiValue("lastPage", "stats")
    assert shell.openingPage() == "stats"
    shell.setUiValue("lastPage", "nowhere")
    assert shell.openingPage() == "home"
    shell.setStartPage("bogus")
    assert shell.startPage == "last"
