"""The web interface and phone remote: a small HTTP server for the browser app in web/, the commands in api.py,
live updates and album covers.

Off until you switch it on. It listens on this computer only unless you allow other devices on your network, and
everything but the pairing page needs a paired device:

- Pairing: the app shows a one-time code for a few minutes; a browser
  that enters it gets a long random key, kept as a cookie only the page's own requests send (HttpOnly,
  SameSite=Strict). Only a hash of each key is stored, and each paired device can be removed. Wrong codes are
  limited, and too many end the code.
- Other web pages can't use it: requests must name this server as their Host (a name that resolves to it from
  elsewhere, "DNS rebinding", is turned away), commands need a header a cross-site form can't send, and no
  other site is allowed to read the answers.
- What it can do is limited to listening: playing, the queue, browsing, likes, ratings and playlists (see api.py).
  It can't read or list your files, edit tags, delete anything or change settings.

Requests are answered on worker threads; the commands themselves run on the window's thread."""
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import sys
import threading
import time
import urllib.parse
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot

from .api import Api, ApiError

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"
# The only files the server hands out, and their types: nothing else on the disk can be asked for
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
}
DEFAULT_PORT = 8483
CODE_LIFETIME_S = 300
CODE_TRIES = 5  # wrong guesses before a pairing code stops working
MAX_BODY = 64 * 1024
MAX_EVENT_STREAMS = 16
MAX_CONNECTIONS = 64  # open connections at once; more are closed straight away (no thread each)
COOKIE = "hallucinate_key"
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; manifest-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                               "form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def _hash(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class Devices:
    """Paired devices, kept in a JSON file in the data folder (readable by you only): a name, when it was paired
    and last seen, and a hash of its key. Thread-safe."""

    def __init__(self, path):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._devices = []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._devices = [d for d in data.get("devices", []) if isinstance(d, dict) and d.get("hash")]
        except (OSError, ValueError):
            pass

    def _save(self):
        from .core.atomic import write_atomic

        text = json.dumps({"devices": self._devices}, indent=1)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(self._path, lambda fh: fh.write(text.encode("utf-8")))
            self._path.chmod(0o600)
        except OSError as exc:
            logger.warning("Couldn't save the paired devices: %s", exc)

    def add(self, name):
        """A new device's key (returned once, never kept)."""
        key = secrets.token_urlsafe(32)
        with self._lock:
            self._devices.append({"id": secrets.token_hex(6), "name": (name or "A device")[:60],
                                  "hash": _hash(key), "paired": time.time(), "seen": time.time()})
            self._save()
        return key

    def check(self, key):
        """The device a key belongs to, or None (compared in constant time)."""
        if not key or len(key) > 200:
            return None
        h = _hash(key)
        with self._lock:
            for d in self._devices:
                if hmac.compare_digest(d["hash"], h):
                    if time.time() - d.get("seen", 0) > 60:
                        d["seen"] = time.time()
                        self._save()
                    return dict(d)
        return None

    def remove(self, device_id):
        with self._lock:
            before = len(self._devices)
            self._devices = [d for d in self._devices if d["id"] != device_id]
            if len(self._devices) != before:
                self._save()
                return True
        return False

    def remove_all(self):
        with self._lock:
            self._devices = []
            self._save()

    def listing(self):
        with self._lock:
            return [{"id": d["id"], "name": d["name"], "paired": d.get("paired", 0), "seen": d.get("seen", 0)}
                    for d in self._devices]


class Pairing:
    """The one pairing code there is at a time: made on request, good for a few minutes and a few wrong tries."""

    def __init__(self):
        self._lock = threading.Lock()
        self._code, self._until, self._tries = "", 0.0, 0

    def new_code(self):
        with self._lock:
            self._code = f"{secrets.randbelow(10**6):06d}"
            self._until = time.monotonic() + CODE_LIFETIME_S
            self._tries = 0
            return self._code

    def current(self):
        """(code, seconds left), or ("", 0) when there's none."""
        with self._lock:
            left = self._until - time.monotonic()
            return (self._code, int(left)) if self._code and left > 0 else ("", 0)

    def cancel(self):
        with self._lock:
            self._code, self._until = "", 0.0

    def redeem(self, code):
        """True once for the right code; a wrong one counts against it."""
        with self._lock:
            if not self._code or time.monotonic() > self._until:
                return False
            if hmac.compare_digest(str(code or "").strip(), self._code):
                self._code, self._until = "", 0.0
                return True
            self._tries += 1
            if self._tries >= CODE_TRIES:
                self._code, self._until = "", 0.0
            return False


class _MainThread(QObject):
    """Runs a function on the thread this object lives on (the window's) and hands back its result."""
    _run = Signal(object)

    def __init__(self):
        super().__init__()
        self._run.connect(self._do, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def _do(self, job):
        fn, future = job
        if future.set_running_or_notify_cancel():
            try:
                future.set_result(fn())
            except BaseException as exc:  # noqa: BLE001 - passed back to the request
                future.set_exception(exc)

    def call(self, fn, timeout=10.0):
        future = Future()
        self._run.emit((fn, future))
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            future.cancel()  # not run later, after whoever asked has been told it didn't work
            raise


class Events:
    """The latest state for live updates: a version that goes up whenever something a remote shows changed.
    Event streams wait on it."""

    def __init__(self):
        self._cond = threading.Condition()
        self.version = 0
        self.state = None
        self.queue_version = 0

    def publish(self, state, queue_changed=False):
        with self._cond:
            self.state = state
            self.version += 1
            if queue_changed:
                self.queue_version += 1
            self._cond.notify_all()

    def wait(self, seen, timeout):
        with self._cond:
            self._cond.wait_for(lambda: self.version != seen, timeout=timeout)
            return self.version, self.state, self.queue_version


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows the same option lets another program bind the port alongside this one and take its requests
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, address, handler, owner, family=socket.AF_INET):
        self.address_family = family
        self.owner = owner
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):  # a flood of connections can't pile up threads
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def server_bind(self):
        if self.address_family == socket.AF_INET6:
            try:  # one socket for IPv6 and IPv4 where the system allows it
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError:
                pass
        super().server_bind()


class _Handler(BaseHTTPRequestHandler):
    server_version = "Hallucinate"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 30

    def log_message(self, fmt, *args):  # no request logging: it would carry what you play and search
        pass

    @property
    def owner(self):
        return self.server.owner

    # --- checks ----------------------------------------------------------------------------------------------
    def _host_ok(self):
        """The Host header names this server (an address, localhost or this computer's name), so a page from
        another site can't reach it through a name it controls."""
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return False
        name = host.rsplit(":", 1)[0] if not host.endswith("]") else host
        name = name.strip("[]")
        try:
            ipaddress.ip_address(name)
            return True
        except ValueError:
            pass
        return name in self.owner.host_names()

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True  # same-origin requests from some browsers, and non-browser clients
        parts = urllib.parse.urlsplit(origin)
        return parts.netloc.lower() == (self.headers.get("Host") or "").lower()

    def _key(self):
        key = ""
        auth = self.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            key = auth[7:].strip()
        else:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == COOKIE:
                    key = v
        return key

    def _device(self):
        return self.owner.devices.check(self._key())

    # --- answers -------------------------------------------------------------------------------------------
    def _send(self, status, body=b"", ctype="application/json", extra=None, cache="no-store"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status, message):
        self._send(status, {"error": message})

    def _read_json(self):
        if self.headers.get("Transfer-Encoding"):  # only plain bodies of a stated length are read
            self.close_connection = True
            raise ApiError("Send a Content-Length")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self.close_connection = True  # the body isn't read, so the connection can't carry on
            raise ApiError("Request too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError("Not JSON") from None
        if not isinstance(data, dict):
            raise ApiError("Not a JSON object")
        return data

    # --- requests ------------------------------------------------------------------------------------------
    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802
        if not self._host_ok():
            return self._error(HTTPStatus.MISDIRECTED_REQUEST, "Unknown host name")
        path = urllib.parse.urlsplit(self.path).path
        if path in STATIC:  # the app itself (its pairing screen asks for a code)
            name, ctype = STATIC[path]
            try:
                body = (WEB_DIR / name).read_bytes()
            except OSError:
                return self._error(HTTPStatus.NOT_FOUND, "Not found")
            return self._send(HTTPStatus.OK, body, ctype, cache="no-cache")
        if path == "/api/hello":  # whether this browser is paired yet (nothing else)
            return self._send(HTTPStatus.OK, {"app": "Hallucinate", "paired": self._device() is not None})
        device = self._device()
        if device is None:
            return self._error(HTTPStatus.UNAUTHORIZED, "Pair this device first")
        if path == "/api/events":
            return self._events()
        if path.startswith("/art/"):
            return self._art(urllib.parse.unquote(path[5:]), urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query))
        return self._error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):  # noqa: N802
        if not self._host_ok():
            return self._error(HTTPStatus.MISDIRECTED_REQUEST, "Unknown host name")
        if not self._origin_ok() or self.headers.get("X-Hallucinate") != "1":
            return self._error(HTTPStatus.FORBIDDEN, "Not from this app")
        path = urllib.parse.urlsplit(self.path).path
        try:
            data = self._read_json()
        except ApiError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        if path == "/api/pair":
            return self._pair(data)
        device = self._device()
        if device is None:
            return self._error(HTTPStatus.UNAUTHORIZED, "Pair this device first")
        if path == "/api/forget":  # this device unpairs itself
            self.owner.devices.remove(device["id"])
            return self._send(HTTPStatus.OK, {"ok": True},
                              extra={"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
        if path != "/api/call":
            return self._error(HTTPStatus.NOT_FOUND, "Not found")
        try:
            result = self.owner.run(lambda: self.owner.command(data.get("method"), data.get("params")))
        except ApiError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except FutureTimeout:
            return self._error(HTTPStatus.SERVICE_UNAVAILABLE, "Hallucinate is busy; try again")
        except Exception:  # noqa: BLE001
            logger.exception("A remote command failed")
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "That didn't work")
        return self._send(HTTPStatus.OK, {"result": result})

    def _pair(self, data):
        ip = self.client_address[0]
        if not self.owner.allow_attempt(ip):
            return self._error(HTTPStatus.TOO_MANY_REQUESTS, "Too many tries; wait a minute")
        if not self.owner.pairing.redeem(str(data.get("code") or "")):
            return self._error(HTTPStatus.FORBIDDEN, "That code isn't right, or it has run out")
        key = self.owner.devices.add(str(data.get("name") or "")[:60])
        self.owner.paired()
        cookie = f"{COOKIE}={key}; Path=/; Max-Age={400 * 86400}; HttpOnly; SameSite=Strict"
        # A browser keeps the key only as the cookie, out of reach of the page's scripts; a program (the
        # terminal version) asks for it to send as a Bearer token.
        body = {"ok": True, **({"key": key} if data.get("token") is True else {})}
        return self._send(HTTPStatus.OK, body, extra={"Set-Cookie": cookie})

    def _art(self, album_key, query):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice

        from .thumbs import bucket, load_thumbnail

        try:
            px = bucket(int((query.get("s") or ["256"])[0]))
        except ValueError:
            px = 256
        try:
            path = self.owner.run(lambda: self.owner.api.art_file(album_key))
        except Exception:  # noqa: BLE001
            path = ""
        image = load_thumbnail(self.owner.thumb_dir, path, px) if path else None
        if image is None or image.isNull():
            return self._error(HTTPStatus.NOT_FOUND, "No cover")
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "JPG", 85)
        buf.close()
        return self._send(HTTPStatus.OK, bytes(data), "image/jpeg", cache="private, max-age=86400")

    def _events(self):
        """Server-sent events: the state now, then again whenever it changes (and a heartbeat)."""
        if not self.owner.stream_opened():
            return self._error(HTTPStatus.SERVICE_UNAVAILABLE, "Too many open connections")
        key = self._key()
        try:
            self.send_response(HTTPStatus.OK)
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            seen, queue_seen = -1, -1
            while not self.owner.stopping:
                version, state, queue_version = self.owner.events.wait(seen, 15)
                if self.owner.devices.check(key) is None:
                    break  # the device was removed: it hears nothing more
                if version == seen:
                    self.wfile.write(b": keep-alive\n\n")
                else:
                    seen = version
                    self.wfile.write(b"event: state\ndata: " + json.dumps(state, ensure_ascii=False).encode() + b"\n\n")
                    if queue_version != queue_seen:
                        queue_seen = queue_version
                        self.wfile.write(b"event: queue\ndata: {}\n\n")
                self.wfile.flush()
        except (OSError, ValueError):
            pass
        finally:
            self.owner.stream_closed()


class WebRemote(QObject):
    """The server, switched on and off from settings (or for headless use). Lives on the window's thread."""
    changed = Signal()  # on/off, address, pairing code or devices changed

    def __init__(self, data_dir, thumb_dir, player=None, library=None, user_lib=None, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QSettings

        self._settings = QSettings("hallucinate", "hallucinate")
        self.api = Api(player, library, user_lib)
        self.devices = Devices(Path(data_dir) / "remote-devices.json")
        self.pairing = Pairing()
        self.events = Events()
        self.thumb_dir = Path(thumb_dir)
        self.stopping = False
        self._main = _MainThread()
        self._httpd = None
        self._thread = None
        self._error = ""
        self._attempts = {}
        self._attempts_lock = threading.Lock()
        self._streams = 0
        self._streams_lock = threading.Lock()
        self._player = player
        self._publish_timer = QTimer(self)
        self._publish_timer.setSingleShot(True)
        self._publish_timer.setInterval(120)  # changes that come together go out as one
        self._publish_timer.timeout.connect(self._publish)
        self._queue_dirty = False
        self._tick = QTimer(self)
        self._tick.setInterval(5000)  # the position, now and then while playing (remotes count on between)
        self._tick.timeout.connect(self._tick_now)
        self._code_timer = QTimer(self)
        self._code_timer.setInterval(1000)
        self._code_timer.timeout.connect(self._code_tick)
        if player is not None:
            for sig in (player.stateChanged, player.trackChanged, player.volumeChanged, player.shuffleChanged,
                        player.repeatChanged, player.sleepChanged, player.radioChanged, player.durationChanged,
                        player.errorChanged, player.upcomingChanged):
                sig.connect(self._soon)
            player.queueChanged.connect(self._queue_changed)
        if user_lib is not None and hasattr(user_lib, "likesChanged"):
            user_lib.likesChanged.connect(self._soon)
        if self.enabled:
            QTimer.singleShot(0, self.start)

    # --- settings ------------------------------------------------------------------------------------------
    @property
    def enabled(self):
        return self._settings.value("remote/enabled", False, bool)

    @property
    def lan(self):
        """Other devices on your network can reach it (else only this computer)."""
        return self._settings.value("remote/lan", False, bool)

    @property
    def port(self):
        try:
            p = int(self._settings.value("remote/port", DEFAULT_PORT))
        except (TypeError, ValueError):
            p = DEFAULT_PORT
        return p if 1024 <= p <= 65535 else DEFAULT_PORT

    def configure(self, enabled=None, lan=None, port=None):
        if enabled is not None:
            self._settings.setValue("remote/enabled", bool(enabled))
        if lan is not None:
            self._settings.setValue("remote/lan", bool(lan))
        if port is not None:
            self._settings.setValue("remote/port", int(port))
        self.stop()
        if self.enabled:
            self.start()
        self.changed.emit()

    @property
    def running(self):
        return self._httpd is not None

    @property
    def error(self):
        return self._error

    def host_names(self):
        names = {"localhost"}
        try:
            host = socket.gethostname().lower()
            names |= {host, host + ".local", host.split(".")[0], host.split(".")[0] + ".local"}
        except OSError:
            pass
        extra = str(self._settings.value("remote/hostNames", "") or "")
        names |= {n.strip().lower() for n in extra.split(",") if n.strip()}
        return names

    def addresses(self):
        """Links that open the web interface: this computer's own, and (when allowed) its network addresses."""
        port = self.port
        out = [f"http://localhost:{port}/"]
        if self.lan:
            ips = set()
            try:  # the address used to reach the network (no packet is sent)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("192.0.2.1", 9))
                    ips.add(s.getsockname()[0])
            except OSError:
                pass
            try:
                for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                    ips.add(info[4][0])
            except OSError:
                pass
            for ip in sorted(i for i in ips if not i.startswith("127.")):
                out.insert(0, f"http://{ip}:{port}/")
        return out

    # --- for the Settings page -----------------------------------------------------------------------------
    @Property(bool, notify=changed)
    def on(self):
        return self.enabled

    @Property(bool, notify=changed)
    def network(self):
        return self.lan

    @Property(bool, notify=changed)
    def isRunning(self):
        return self.running

    @Property(str, notify=changed)
    def problem(self):
        return self._error

    @Property(int, notify=changed)
    def portNumber(self):
        return self.port

    @Property("QVariantList", notify=changed)
    def links(self):
        return self.addresses() if self.running else []

    @Property(str, notify=changed)
    def code(self):
        return self.pairing.current()[0]

    @Property(int, notify=changed)
    def codeSeconds(self):
        return self.pairing.current()[1]

    @Property("QVariantList", notify=changed)
    def pairedDevices(self):
        return self.devices.listing()

    @Slot(bool)
    def setOn(self, on):
        self.configure(enabled=on)

    @Slot(bool)
    def setNetwork(self, on):
        self.configure(lan=on)

    @Slot(int)
    def setPortNumber(self, port):
        if 1024 <= int(port) <= 65535:
            self.configure(port=int(port))

    @Slot(result=str)
    def pairDevice(self):
        """A new pairing code to type into the browser (good for a few minutes)."""
        return self.new_code()

    @Slot()
    def cancelCode(self):
        self.pairing.cancel()
        self.changed.emit()

    @Slot(str)
    def forgetDevice(self, device_id):
        self.devices.remove(device_id)
        self.events.publish(self.events.state)  # its open event stream notices straight away
        self.changed.emit()

    @Slot()
    def forgetAllDevices(self):
        self.devices.remove_all()
        self.events.publish(self.events.state)
        self.changed.emit()

    # --- running -------------------------------------------------------------------------------------------
    def start(self):
        if self._httpd is not None:
            return True
        self.stopping = False
        host = "::" if self.lan else "127.0.0.1"
        family = socket.AF_INET6 if self.lan else socket.AF_INET
        try:
            self._httpd = _Server((host, self.port), _Handler, self, family)
        except OSError:
            if self.lan:  # no IPv6 here: IPv4 only
                try:
                    self._httpd = _Server(("0.0.0.0", self.port), _Handler, self)  # noqa: S104 - asked for
                except OSError as exc:
                    self._error = f"Port {self.port} is in use or can't be opened ({exc.strerror or exc})"
            else:
                self._error = f"Port {self.port} is in use or can't be opened"
            if self._httpd is None:
                logger.warning("Web remote didn't start: %s", self._error)
                self.changed.emit()
                return False
        self._error = ""
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="web-remote", daemon=True)
        self._thread.start()
        self._tick.start()
        self._publish()
        self.changed.emit()
        return True

    def stop(self):
        if self._httpd is None:
            return
        self.stopping = True
        self.events.publish(self.events.state)  # wake the event streams so they see it
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._tick.stop()
        self.changed.emit()

    def shutdown(self):
        self.pairing.cancel()
        self.stop()

    def run(self, fn):
        return self._main.call(fn)

    def command(self, method, params):
        """A remote's command (on the window's thread); what it changed goes out to every remote at once."""
        result = self.api.call(method, params)
        self._soon()
        return result

    # --- pairing -------------------------------------------------------------------------------------------
    def new_code(self):
        code = self.pairing.new_code()
        self._code_timer.start()
        self.changed.emit()
        return code

    def _code_tick(self):
        if not self.pairing.current()[0]:
            self._code_timer.stop()
        self.changed.emit()

    def paired(self):
        """A device just paired (called from a request thread)."""
        QTimer.singleShot(0, self, self.changed.emit)

    def allow_attempt(self, ip):
        """At most 10 pairing attempts a minute from one address."""
        now = time.monotonic()
        with self._attempts_lock:
            if len(self._attempts) > 1000:  # forget addresses that have gone quiet
                self._attempts = {k: v for k, v in self._attempts.items() if v and now - v[-1] < 60}
            recent = [t for t in self._attempts.get(ip, []) if now - t < 60]
            if len(recent) >= 10:
                self._attempts[ip] = recent
                return False
            recent.append(now)
            self._attempts[ip] = recent
            return True

    def stream_opened(self):
        with self._streams_lock:
            if self._streams >= MAX_EVENT_STREAMS:
                return False
            self._streams += 1
            return True

    def stream_closed(self):
        with self._streams_lock:
            self._streams = max(0, self._streams - 1)

    # --- live updates --------------------------------------------------------------------------------------
    @Slot()
    def _soon(self):
        if self._httpd is not None and not self._publish_timer.isActive():
            self._publish_timer.start()

    @Slot()
    def _tick_now(self):
        """Only while something plays and a remote is listening: otherwise there's nothing new to say."""
        if self._streams and self._player is not None and self._player.playing:
            self._soon()

    @Slot()
    def _queue_changed(self):
        self._queue_dirty = True
        self._soon()

    @Slot()
    def _publish(self):
        try:
            state = self.api.call("state")
        except ApiError:
            return
        state["at"] = time.time()
        self.events.publish(state, queue_changed=self._queue_dirty)
        self._queue_dirty = False
