"""Desktop notifications on Linux, sent to org.freedesktop.Notifications with the exact argument types the
specification asks for. QtDBus can't type them from Python (the id goes out as int32 and the empty lists have no
element type), and strict daemons (mako, dunst, swaync, GNOME's) reject the call, so they're sent with jeepney,
which keyring already brings on Linux."""
import html
import threading

try:
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection
except ImportError:  # pragma: no cover - keyring needs it on Linux, but a distro package might not
    open_dbus_connection = None

NOTIFICATIONS = None if open_dbus_connection is None else DBusAddress(
    "/org/freedesktop/Notifications", bus_name="org.freedesktop.Notifications",
    interface="org.freedesktop.Notifications")


def notify_args(title, body, replaces=0, image="", app_icon="hallucinate", timeout=5000, category=""):
    """The Notify call's arguments, signature susssasa{sv}i."""
    hints = {}
    if image:
        hints["image-path"] = ("s", image)
    if category:
        hints["category"] = ("s", category)
    # Most daemons read the body as markup: a song's tags mustn't format it, add links or have it fetch images
    return ("Hallucinate", int(replaces) & 0xFFFFFFFF, app_icon, title or "",
            html.escape(body or "", quote=False), [], hints, int(timeout))


class Notifier:
    """Sends notifications from a worker thread (the session bus can be slow to answer, or not there at all).
    A notification with a `key` replaces the last one sent with the same key, so skipping through songs updates
    one notification instead of stacking them."""

    def __init__(self):
        self._lock = threading.Lock()
        self._conn = None
        self._ids = {}

    @staticmethod
    def available():
        return open_dbus_connection is not None

    def send(self, title, body, key="", image="", category=""):
        if open_dbus_connection is None:
            return False
        threading.Thread(target=self._send, args=(title, body, key, image, category), daemon=True,
                         name="notify").start()
        return True

    def _send(self, title, body, key, image, category):
        with self._lock:
            try:
                if self._conn is None:
                    self._conn = open_dbus_connection(bus="SESSION")
                msg = new_method_call(NOTIFICATIONS, "Notify", "susssasa{sv}i",
                                      notify_args(title, body, self._ids.get(key, 0) if key else 0, image,
                                                  category=category))
                reply = self._conn.send_and_get_reply(msg, timeout=5)
                if key and reply.body:
                    self._ids[key] = int(reply.body[0])
            except Exception:  # noqa: BLE001 - no daemon, no bus, a daemon that errors: nothing to show
                try:
                    if self._conn is not None:
                        self._conn.close()
                except Exception:  # noqa: BLE001
                    pass
                self._conn = None
