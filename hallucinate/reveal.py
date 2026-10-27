"""Show a song (or a folder) in the system's file manager, with the song selected.

In the Flatpak, opening a file:// folder with Qt goes through the desktop portal's file opener, which doesn't
open folders: nothing happened. The portal has a call for exactly this, OpenURI.OpenDirectory, which takes the
file itself (as a file descriptor, so the sandbox never names a path the host can't see) and opens its folder
with it selected. Outside the sandbox, file managers (Nautilus, Dolphin, Nemo, Thunar, Caja…) answer the
org.freedesktop.FileManager1 interface, which does the same. When neither answers, the caller opens the folder
the plain way. Calls go out with jeepney, as notifications do."""
import logging
import os

logger = logging.getLogger(__name__)

try:
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection
except ImportError:  # pragma: no cover - keyring needs it on Linux
    open_dbus_connection = None

PORTAL = None if open_dbus_connection is None else DBusAddress(
    "/org/freedesktop/portal/desktop", bus_name="org.freedesktop.portal.Desktop",
    interface="org.freedesktop.portal.OpenURI")
FILE_MANAGER = None if open_dbus_connection is None else DBusAddress(
    "/org/freedesktop/FileManager1", bus_name="org.freedesktop.FileManager1",
    interface="org.freedesktop.FileManager1")


def in_flatpak(env=None):
    env = os.environ if env is None else env
    return bool(env.get("FLATPAK_ID")) or os.path.exists("/.flatpak-info")


def uri(path):
    from pathlib import Path

    return Path(path).absolute().as_uri()


def calls(path, flatpak):
    """The D-Bus calls to try, in order: [(address, method, signature, args, wants a file descriptor)]."""
    if open_dbus_connection is None or not path:
        return []
    folder = os.path.isdir(path)
    if flatpak:
        # a file: its folder, with it selected; a folder: opened (the portal opens folders as files). Should the
        # portal refuse the file (it did for images saved in Pictures/Hallucinate), the folder alone is opened.
        if folder:
            return [(PORTAL, "OpenFile", "sha{sv}", ("", path, {}), True)]
        return [(PORTAL, "OpenDirectory", "sha{sv}", ("", path, {}), True),
                (PORTAL, "OpenFile", "sha{sv}", ("", os.path.dirname(path), {}), True)]
    return [(FILE_MANAGER, "ShowFolders" if folder else "ShowItems", "ass", ([uri(path)], ""), False)]


def show(path, flatpak=None, connect=None):
    """Ask the desktop to show `path`. True when a file manager (or the portal) took the call; False means open
    the folder some other way. Blocks for up to a few seconds: call it from a worker thread."""
    flatpak = in_flatpak() if flatpak is None else flatpak
    todo = calls(path, flatpak)
    if not todo:
        return False
    connect = connect or (lambda: open_dbus_connection(bus="SESSION", enable_fds=True))
    try:
        conn = connect()
    except Exception:  # noqa: BLE001 - no session bus
        return False
    try:
        for address, method, signature, args, wants_fd in todo:
            fd = None
            try:
                if wants_fd:
                    fd = os.open(args[1], os.O_PATH | os.O_CLOEXEC)
                    args = (args[0], fd, args[2])
                reply = conn.send_and_get_reply(new_method_call(address, method, signature, args), timeout=5)
                if reply.header.message_type.name != "error":
                    return True
                # (kept for Copy debug info: why a file manager didn't open)
                logger.warning("Show in folder: %s refused: %s", method, (getattr(reply, "body", None) or ["?"])[0])
            except Exception as e:  # noqa: BLE001 - not there, refused, timed out: try the next, or give up
                logger.warning("Show in folder: %s failed: %s", method, type(e).__name__)
                continue
            finally:
                if fd is not None:
                    os.close(fd)
        return False
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
