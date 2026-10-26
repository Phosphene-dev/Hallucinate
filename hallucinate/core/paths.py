import os
import sys
from pathlib import Path


def _data_base() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _config_base() -> Path:
    override = os.environ.get("XDG_CONFIG_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path.home() / ".config"


def _cache_base() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


def legacy_locations() -> tuple:
    """Old Music Player paths, or None when data is explicitly redirected for isolation."""
    if os.environ.get("HALLUCINATE_DISABLE_LEGACY_MIGRATION"):
        return None
    return (_data_base() / "musicplayer", _config_base() / "musicplayer", _cache_base() / "musicplayer")


def data_dir() -> Path:
    override = os.environ.get("HALLUCINATE_DATA")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "hallucinate"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "hallucinate"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "hallucinate"
    return _private(base)


def _private(folder: Path) -> Path:
    """Make one of Hallucinate's own folders readable by you alone: it holds your listening history, backups
    and crash records, and a shared computer's other users have no business reading them."""
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        try:
            if folder.stat().st_mode & 0o077:
                folder.chmod(0o700)
        except OSError:
            pass
    return folder


def config_dir() -> Path:
    override = os.environ.get("XDG_CONFIG_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"
    return _private(base / "hallucinate")


def cache_dir() -> Path:
    return _private(_cache_base() / "hallucinate")


def art_dir() -> Path:
    p = data_dir() / "art"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "library.db"


def pictures_dir() -> Path:
    """Where Hallucinate saves images (recap cards, spectrograms): a Hallucinate folder in Pictures. The Flatpak
    may write there and nowhere else in Pictures (--filesystem=xdg-pictures/Hallucinate:create)."""
    base = ""
    try:
        from PySide6.QtCore import QStandardPaths

        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    except ImportError:  # pragma: no cover - headless installs without Qt
        pass
    return Path(base or Path.home() / "Pictures") / "Hallucinate"
