"""The AppImage's window finds its dock icon: the launcher that starts it (AppImageLauncher's, or our own)."""
from hallucinate import desktopentry as de


def env_for(tmp_path, image=True):
    app = tmp_path / "Apps" / "Hallucinate x86_64.AppImage"
    app.parent.mkdir(parents=True, exist_ok=True)
    app.write_bytes(b"\x7fELF")
    env = {"XDG_DATA_HOME": str(tmp_path / "share")}
    if image:
        env["APPIMAGE"] = str(app)
    return env, app


def test_not_an_appimage_does_nothing(tmp_path):
    env, _ = env_for(tmp_path, image=False)
    assert de.launcher_id(env) == ""
    assert de.install(env)  # says why
    assert not de.entry_path(env).exists()


def test_appimagelauncher_s_launcher_gives_the_window_its_name(tmp_path):
    """AppImageLauncher names its launcher after a hash: the window must take that name for the dock to match."""
    env, app = env_for(tmp_path)
    apps = tmp_path / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "other.desktop").write_text("[Desktop Entry]\nExec=/usr/bin/other\n")
    (apps / "appimagekit_1a2b-Hallucinate.desktop").write_text(
        f'[Desktop Entry]\nName=Hallucinate\nExec="{app}" %F\nIcon=appimagekit_1a2b_hallucinate\n')
    assert de.launcher_id(env) == "appimagekit_1a2b-Hallucinate"
    assert de.install(env)  # no second launcher beside it
    assert not de.entry_path(env).exists()


def test_add_follow_and_remove_our_own_launcher(tmp_path):
    env, app = env_for(tmp_path)
    assert de.launcher_id(env) == ""
    assert de.install(env) == ""
    text = de.entry_path(env).read_text()
    assert f'Exec="{app}" %F' in text and "StartupWMClass=hallucinate" in text and de.MARKER in text
    assert (tmp_path / "share" / "icons" / "hicolor" / "256x256" / "apps" / "hallucinate.png").exists()
    assert de.launcher_id(env) == "hallucinate" and de.ours(env)

    moved = tmp_path / "Elsewhere.AppImage"
    app.rename(moved)
    env["APPIMAGE"] = str(moved)
    de.follow(env)  # moved: the launcher follows it
    assert str(moved) in de.entry_path(env).read_text()

    de.remove(env)
    assert not de.entry_path(env).exists()
    assert not (tmp_path / "share" / "icons" / "hicolor" / "256x256" / "apps" / "hallucinate.png").exists()


def test_a_launcher_someone_else_wrote_is_never_touched(tmp_path):
    env, _ = env_for(tmp_path)
    path = de.entry_path(env)
    path.parent.mkdir(parents=True)
    path.write_text("[Desktop Entry]\nExec=/usr/bin/hallucinate\n")
    assert de.taken(env) and de.install(env)
    de.remove(env)
    de.follow(env)
    assert path.read_text() == "[Desktop Entry]\nExec=/usr/bin/hallucinate\n"


def test_launchers_offer_the_tray_menu_s_actions():
    """Issue 106: right-clicking Hallucinate in a dock or taskbar offers play/pause, next, previous and the mini
    player (not Quit: the tray menu keeps that), in the packages' launcher and the AppImage's alike, each a
    command line the app takes."""
    import configparser
    import pathlib

    from hallucinate import app

    root = pathlib.Path(__file__).resolve().parent.parent
    texts = [(root / "packaging" / "hallucinate.desktop").read_text(encoding="utf-8"),
             (root / "packaging" / "appimage" / "appdir" / "hallucinate.desktop").read_text(encoding="utf-8"),
             de.entry_text("/apps/Hallucinate.AppImage")]
    keys = [key for key, _, _ in de.ACTIONS]
    for text in texts:
        entry = configparser.ConfigParser(interpolation=None)
        entry.optionxform = str
        entry.read_string(text)
        assert entry["Desktop Entry"]["Actions"] == "".join(k + ";" for k in keys)
        for key, name, args in de.ACTIONS:
            action = entry[f"Desktop Action {key}"]
            assert action["Name"] == name and action["Exec"].endswith(" " + args)
    seen = []
    for _key, _name, args in de.ACTIONS:  # every one is a command line the app knows
        monkey = app.send_control
        try:
            app.send_control = lambda command, **_: seen.append(command) or {"ok": True}
            assert app.main(args.split()) == 0
        finally:
            app.send_control = monkey
    assert seen == ["play-pause", "next", "prev", "mini-player"]
    assert all("Quit" not in text for text in texts)
