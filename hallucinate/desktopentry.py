"""Give an AppImage's window its icon in docks and taskbars, and add it to the app launcher when asked.

On Wayland a dock finds a window's icon through its app id ("hallucinate"), by looking for hallucinate.desktop
among the installed launchers. An AppImage installs nothing, so without a tool such as Gear Lever or
AppImageLauncher, docks (noctalia's, KDE's task manager, GNOME's dash) show a blank icon. This writes the same
launcher the packages install, into ~/.local/share, pointing at the AppImage file itself, and the icon beside
it. A launcher that AppImageLauncher, Gear Lever or anyone else already wrote for this AppImage (named after
themselves: appimagekit_<hash>-Hallucinate.desktop, gearlever_…) is used instead: the window takes that
launcher's name as its app id (see launcher_id), so the dock matches it, and no second launcher is offered.
Only when asked (Settings → Desktop, or the one-time offer at the first start of an AppImage); "Remove"
takes both away again. The launcher carries a marker, so a launcher someone else wrote is never touched."""
import os
import shutil
from pathlib import Path

from .core.i18n import fill, translate

APP_ID = "hallucinate"
MARKER = "X-Hallucinate-AppImage=true"
ICON_SIZES = (("hallucinate.png", "256x256"), ("hallucinate-1024.png", "1024x1024"))
ASSETS = Path(__file__).resolve().parent / "assets"


def appimage(env=None):
    """The AppImage file this runs from, or "" when it isn't one."""
    env = os.environ if env is None else env
    path = env.get("APPIMAGE", "")
    return path if path and os.path.isfile(path) else ""


def _data_home(env):
    return Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _applications(env):
    return _data_home(env) / "applications"


def _exec_target(line):
    """The program an Exec= or TryExec= line runs (its first word, unquoted)."""
    value = line.split("=", 1)[1].strip()
    if value.startswith('"'):
        end = value.find('"', 1)
        while end > 0 and value[end - 1] == "\\":
            end = value.find('"', end + 1)
        return value[1:end].replace('\\"', '"').replace("\\\\", "\\") if end > 0 else value[1:]
    return value.split()[0] if value else ""


def launcher_id(env=None):
    """The desktop id (file name without .desktop) of an installed launcher that starts this AppImage, or "".
    Ours counts too, so the answer is "hallucinate" once it's installed."""
    env = os.environ if env is None else env
    image = appimage(env)
    if not image:
        return ""
    folder = _applications(env)
    try:
        names = sorted(p for p in folder.iterdir() if p.suffix == ".desktop")
    except OSError:
        return ""
    real = os.path.realpath(image)
    for path in names:
        try:
            if path.stat().st_size > 65536:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if line.startswith(("Exec=", "TryExec=")):
                target = _exec_target(line)
                if target and (target == image or os.path.realpath(target) == real):
                    return path.stem
    return ""


def entry_path(env=None):
    return _data_home(os.environ if env is None else env) / "applications" / f"{APP_ID}.desktop"


def _quote(path):
    """A path in an Exec line (the desktop entry spec's quoting)."""
    if not any(c in path for c in ' \t\n"\'\\><~|&;$*?#()`'):
        return path
    escaped = path.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


# The launcher's right-click actions in docks and taskbars (as the packages' hallucinate.desktop has them):
# the tray menu's player controls, which start Hallucinate first when it isn't running (--launch). Not Quit:
# docks put the actions among their own entries, where a Quit sat oddly (the tester's call; the tray keeps it).
ACTIONS = (("PlayPause", "Play/Pause", "--play-pause --launch"), ("Next", "Next", "--next --launch"),
           ("Previous", "Previous", "--prev --launch"), ("MiniPlayer", "Mini Player", "--mini-player --launch"))


def entry_text(image):
    actions = "".join(f"\n[Desktop Action {key}]\nName={name}\nExec={_quote(image)} {args}\n" for key, name, args in ACTIONS)
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Hallucinate\n"
        "GenericName=Music Player\n"
        "Comment=Hallucinate music library and player with instant search\n"
        f"Exec={_quote(image)} %F\n"
        f"TryExec={image}\n"
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        "Categories=AudioVideo;Audio;Player;Qt;\n"
        "MimeType=audio/mpeg;audio/flac;audio/x-flac;audio/ogg;audio/opus;audio/x-wav;audio/mp4;audio/aac;"
        "audio/x-ms-wma;audio/x-ape;\n"
        f"StartupWMClass={APP_ID}\n"
        f"Actions={''.join(key + ';' for key, _, _ in ACTIONS)}\n"
        f"{MARKER}\n"
        f"{actions}"
    )


def ours(env=None):
    """Whether the launcher there is one this module wrote."""
    try:
        return MARKER in entry_path(env).read_text(encoding="utf-8")
    except OSError:
        return False


def taken(env=None):
    """A hallucinate.desktop someone else put there (a package, Gear Lever): leave it alone."""
    return entry_path(env).exists() and not ours(env)


def install(env=None):
    """Write the launcher and the icon. Returns "" or what went wrong, in words."""
    env = os.environ if env is None else env
    image = appimage(env)
    if not image:
        return translate("Shell", "This isn't running from an AppImage")
    if taken(env):
        return translate("Shell", "Another Hallucinate launcher is already installed")
    other = launcher_id(env)
    if other and other != APP_ID:
        return translate("Shell", "It's already in your app launcher")
    data = _data_home(env)
    try:
        for name, size in ICON_SIZES:
            source = ASSETS / name
            if source.exists():
                folder = data / "icons" / "hicolor" / size / "apps"
                folder.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, folder / f"{APP_ID}.png")
        path = entry_path(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(entry_text(image), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        return fill(translate("Shell", "Couldn't write the launcher: %1"), exc.strerror or exc)
    return ""


def remove(env=None):
    """Take away the launcher and icon this module wrote (nothing else)."""
    env = os.environ if env is None else env
    if not ours(env):
        return
    data = _data_home(env)
    for _name, size in ICON_SIZES:
        try:
            (data / "icons" / "hicolor" / size / "apps" / f"{APP_ID}.png").unlink()
        except OSError:
            pass
    try:
        entry_path(env).unlink()
    except OSError:
        pass


def follow(env=None):
    """At start: the AppImage was moved or renamed since its launcher was written. Point the launcher at it
    again (only a launcher of ours)."""
    env = os.environ if env is None else env
    image = appimage(env)
    if image and ours(env):
        try:
            if entry_path(env).read_text(encoding="utf-8") != entry_text(image):
                install(env)
        except OSError:
            pass
