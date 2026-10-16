import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QIcon

from hallucinate.player import Player
from hallucinate.shell import DesktopShell


class FakeWindow:
    def __init__(self):
        self.visible, self.calls = True, []

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

    shell.setCloseAction("tray")
    assert shell.handleClose() == "quit" and quits  # no tray icon offscreen: quitting beats vanishing
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
    monkeypatch.setattr(
        DesktopShell, "_send_notification", lambda self, title, artist: shown.append((title, artist))
    )
    shell._player = type(
        "Playback",
        (),
        {"hasTrack": True, "current": {"title": "New song", "artist": "New artist"}},
    )()

    shell._on_track_changed()
    assert shown == []
    shell.setDesktopNotifications(True)
    shell._on_track_changed()
    assert shown == [("New song", "New artist")]
    shell.setDesktopNotifications(False)
    shell._on_track_changed()
    assert len(shown) == 1


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
    assert shell.handleClose() == "quit" and quits  # no minimize, no tray: nothing to ask about
    monkeypatch.setattr(DesktopShell, "_tray_visible", lambda self: True)
    assert shell.handleClose() == "ask"
    assert shell.closeWith("minimize") == "kept" and not win.visible  # a remembered minimize falls back to the tray


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
