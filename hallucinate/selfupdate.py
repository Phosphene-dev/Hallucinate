"""Installing a new release from inside the app, where Hallucinate owns its own files: the Windows installer
build and the AppImage. Everywhere else (Flatpak, AUR and other packages, pip, the portable Windows zip, the
unsigned macOS app) updates stay with whatever installed it, and the app only links to the release.

Every download is checked against the SHA-256 digest GitHub publishes for the release asset before it is run
or swapped in."""
import hashlib
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from .core import net

DOWNLOAD_PREFIX = "https://github.com/Phosphene-dev/Hallucinate/releases/download/"
MAX_BYTES = 1_000_000_000
CHUNK = 256 * 1024


def install_kind(env=None, platform=None, frozen=None, executable=None):
    """"windows" (installed with the setup program), "appimage" (a writable AppImage) or "" (update elsewhere)."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = Path(sys.executable if executable is None else executable)
    if platform == "win32" and frozen and (executable.parent / "unins000.exe").exists():
        return "windows"
    image = env.get("APPIMAGE", "")
    if platform.startswith("linux") and image and not env.get("FLATPAK_ID"):
        path = Path(image)
        if path.is_file() and os.access(path, os.W_OK) and os.access(path.parent, os.W_OK):
            return "appimage"
    return ""


def asset_name(kind, version):
    return {"windows": f"hallucinate-{version}-windows-x64-setup.exe",
            "appimage": f"hallucinate-{version}-x86_64.AppImage"}.get(kind, "")


def pick_asset(assets, version, kind):
    """{"name", "url", "size", "sha256"} for this install, or None when the release doesn't have a usable one."""
    want = asset_name(kind, version)
    for a in assets or ():
        if a.get("name") != want:
            continue
        url, digest = str(a.get("url") or ""), str(a.get("digest") or "")
        m = re.fullmatch(r"sha256:([0-9a-f]{64})", digest)
        size = int(a.get("size") or 0)
        if url.startswith(DOWNLOAD_PREFIX) and m and 0 < size <= MAX_BYTES:
            return {"name": want, "url": url, "size": size, "sha256": m.group(1)}
    return None


def download(asset, dest, progress=None, cancelled=lambda: False, opener=None):
    """Download to dest and check its digest. Raises OSError (network, cancel) or ValueError (bad file); dest is
    removed on any failure."""
    import urllib.request

    opener = opener or net.urlopen
    dest = Path(dest)
    digest, got = hashlib.sha256(), 0
    try:
        req = urllib.request.Request(asset["url"], headers={"User-Agent": "Hallucinate updater"})
        with opener(req, timeout=30, limit=asset["size"] + 1) as resp, open(dest, "wb") as out:
            while True:
                if cancelled():
                    raise OSError("Update cancelled")
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                got += len(chunk)
                if got > asset["size"]:
                    raise ValueError("The download is larger than the release says")
                digest.update(chunk)
                out.write(chunk)
                if progress:
                    progress(got / asset["size"])
        if got != asset["size"] or digest.hexdigest() != asset["sha256"]:
            raise ValueError("The download doesn't match the release's checksum")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return dest


def run_windows_installer(path, popen=subprocess.Popen):
    """Start the installer without its wizard. It waits for this app to close, installs over it and starts it
    again (installer.iss runs the app after a silent install)."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
          creationflags=flags, close_fds=True)


def swap_appimage(new_path, target, pid, env=None, popen=subprocess.Popen):
    """Replace the AppImage in place, then start the new one as soon as this process has exited (it is a single
    instance, so starting it earlier would only hand over to this one)."""
    target = Path(target)
    os.chmod(new_path, 0o755)
    os.replace(new_path, target)
    env = dict(os.environ if env is None else env)
    appdir = env.get("APPDIR", "")
    # Drop what this AppImage's launcher set up, so the new one starts from the user's own environment.
    clean = {k: v for k, v in env.items()
             if k not in ("APPIMAGE", "APPDIR", "ARGV0", "OWD") and not (appdir and appdir in v)}
    script = f"while kill -0 {int(pid)} 2>/dev/null; do sleep 0.2; done; exec {shlex.quote(str(target))}"
    popen(["/bin/sh", "-c", script], env=clean, start_new_session=True, close_fds=True,
          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
