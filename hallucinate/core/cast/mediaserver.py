"""The small media server cast devices fetch songs from.

A Chromecast or a TV is told "play http://<this computer>:<port>/m/<link>" and fetches the song itself. So this
server has to accept connections from the network, but it hands out almost nothing:

- Only what's being cast: each song gets its own link, a long random one, made when it's sent to the device.
  There's no listing and no way to name a file; old links are dropped as songs move on.
- Only to the device it was made for: a link answers the address it was shared with and no one else.
- Only reading, and only what the device needs: GET/HEAD, byte ranges for seeking, no other methods.

It runs only while you're casting. Requests aren't logged (they'd carry what you play)."""
import collections
import ipaddress
import logging
import os
import re
import secrets
import socket
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8484
KEEP_LINKS = 8  # the playing song, the next one and a few just finished (a device may re-read the end)
CHUNK = 64 * 1024
MAX_CONNECTIONS = 16
CONTENT_TYPES = {
    ".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".aac": "audio/aac",
    ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav", ".aif": "audio/aiff",
    ".aiff": "audio/aiff", ".wma": "audio/x-ms-wma", ".ape": "audio/x-ape", ".wv": "audio/x-wavpack",
    ".dsf": "audio/x-dsf", ".dff": "audio/x-dff", ".mka": "audio/x-matroska", ".webm": "audio/webm",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
}
DLNA_SEEKABLE = "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"
DLNA_LIVE = "DLNA.ORG_OP=00;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"


def content_type(path):
    return CONTENT_TYPES.get(os.path.splitext(str(path))[1].lower(), "application/octet-stream")


def address_towards(host):
    """This computer's address as `host` sees it (the one to put in links for it). No packet is sent."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, 9))
        return s.getsockname()[0]


def parse_range(header, size):
    """(start, end inclusive) for a single "bytes=" range, None for no/ignorable range, or "bad" if it can't be
    satisfied."""
    if not header:
        return None
    m = re.fullmatch(r"\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*", header)
    if not m or (not m.group(1) and not m.group(2)):
        return None  # several ranges or junk: answer with the whole file, as the spec allows
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:
        n = int(m.group(2))
        if n == 0:
            return "bad"
        start, end = max(0, size - n), size - 1
    end = min(end, size - 1)
    if start >= size or start > end:
        return "bad"
    return start, end


class Link:
    """What one link serves: a file, some bytes, a live stream (a callable that yields chunks), or something
    relayed from elsewhere (`relay(range_header)` opens it: a server's song, whose own address holds a login
    the device must never see)."""

    def __init__(self, client, ctype, path=None, data=None, live=None, relay=None, name="media"):
        self.client, self.ctype, self.name = client, ctype, name
        self.path, self.data, self.live, self.relay = path, data, live, relay
        self.fetched = False  # whether the device has asked for it (if not, it may not be able to reach us)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16

    def __init__(self, address, owner):
        self.owner = owner
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(address, _Handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class _Handler(BaseHTTPRequestHandler):
    server_version = "Hallucinate"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 60

    def log_message(self, fmt, *args):  # nothing: requests would carry what you play
        pass

    def _plain(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def do_GET(self):  # noqa: N802
        self._serve(head=False)

    def do_HEAD(self):  # noqa: N802
        self._serve(head=True)

    def _other(self):
        self._plain(HTTPStatus.METHOD_NOT_ALLOWED)

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _other  # noqa: N815

    def _serve(self, head):
        m = re.fullmatch(r"/m/([A-Za-z0-9_-]{16,64})(?:\.[A-Za-z0-9]{1,5})?", urllib.parse.urlsplit(self.path).path)
        link = self.server.owner.find(m.group(1)) if m else None
        if link is None or not self.server.owner.allowed(link, self.client_address[0]):
            self._plain(HTTPStatus.NOT_FOUND)  # the same answer either way: nothing to learn by guessing
            return
        link.fetched = True
        try:
            if link.relay is not None:
                self._relay(link, head)
            elif link.live is not None:
                self._live(link, head)
            elif link.data is not None:
                self._bytes(link, link.data, head)
            else:
                self._file(link, head)
        except (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout):
            self.close_connection = True  # the device stopped reading (a seek, or the next song)

    def _common(self, link, live=False):
        self.send_header("Content-Type", link.ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")  # the Cast receiver page fetches with CORS
        self.send_header("transferMode.dlna.org", "Streaming")
        self.send_header("contentFeatures.dlna.org", DLNA_LIVE if live else DLNA_SEEKABLE)

    def _bytes(self, link, data, head):
        self.send_response(HTTPStatus.OK)
        self._common(link)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def _file(self, link, head):
        try:
            f = open(link.path, "rb")
        except OSError:
            self._plain(HTTPStatus.NOT_FOUND)
            return
        with f:
            size = os.fstat(f.fileno()).st_size
            rng = parse_range(self.headers.get("Range"), size)
            if rng == "bad":
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            start, end = rng if rng else (0, size - 1)
            self.send_response(HTTPStatus.PARTIAL_CONTENT if rng else HTTPStatus.OK)
            self._common(link)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            if rng:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if head or size == 0:
                return
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(CHUNK, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def _relay(self, link, head):
        try:
            resp = link.relay(self.headers.get("Range") or "")
        except Exception as e:  # noqa: BLE001 - whatever the far side did, the device just gets a 502
            logger.info("Couldn't relay a song to a cast device: %s", e)
            self._plain(HTTPStatus.BAD_GATEWAY)
            return
        with resp:
            status = getattr(resp, "status", 200)
            if status not in (200, 206):
                self._plain(HTTPStatus.BAD_GATEWAY)
                return
            length = resp.headers.get("Content-Length")
            self.send_response(status)
            self._common(link, live=not length)
            for name in ("Content-Length", "Content-Range", "Accept-Ranges"):
                value = resp.headers.get(name)
                if value and re.fullmatch(r"[A-Za-z0-9 */=,-]{1,100}", value):
                    self.send_header(name, value)
            if not length:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            if head:
                return
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _live(self, link, head):
        # A live stream has no length: sent until it ends, then the connection closes (HTTP/1.0 style, which
        # every device reads; some choke on chunked encoding)
        self.protocol_version = "HTTP/1.0"
        self.send_response(HTTPStatus.OK)
        self._common(link, live=True)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if head:
            return
        for chunk in link.live():
            if chunk:
                self.wfile.write(chunk)


class MediaServer:
    """Serves what's being cast. start() before sharing; stop() when casting ends. Thread-safe."""

    def __init__(self, port=DEFAULT_PORT):
        self.port = port
        self._links = collections.OrderedDict()
        self._lock = threading.Lock()
        self._server = None
        self._thread = None
        self.error = ""

    @property
    def running(self):
        return self._server is not None

    def start(self, bind=""):
        """Starts listening (on every address unless `bind` names one). Falls back to a free port if the chosen
        one is taken; the port in use is `self.port`. Returns False with `self.error` set if it can't."""
        if self._server is not None:
            return True
        last = None
        for port in (self.port, 0) if self.port else (0,):
            try:
                self._server = _Server((bind, port), self)
                break
            except OSError as e:
                last = e
        if self._server is None:
            self.error = str(last)
            return False
        self.port = self._server.server_address[1]
        self.error = ""
        self._thread = threading.Thread(target=self._server.serve_forever, name="cast-media", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            server.server_close()
        with self._lock:
            self._links.clear()

    def share(self, client, path=None, data=None, live=None, relay=None, ctype=None, name="media"):
        """A link to `path` (a file), `data` (bytes), `live` (a callable returning an iterator of chunks) or `relay`
        (see Link), usable only by the device at address `client`. Returns the link's path ("/m/<token>.<ext>")."""
        ipaddress.ip_address(client)  # (raises for anything but an address)
        if ctype is None:
            ctype = content_type(path or name)
        token = secrets.token_urlsafe(24)
        ext = os.path.splitext(str(path or name))[1][:6] if (path or "." in name) else ""
        if not re.fullmatch(r"(\.[A-Za-z0-9]{1,5})?", ext):
            ext = ""
        with self._lock:
            self._links[token] = Link(client, ctype, path=path, data=data, live=live, relay=relay, name=name)
            while len(self._links) > KEEP_LINKS:
                self._links.popitem(last=False)
        return f"/m/{token}{ext}"

    def url(self, client, link_path):
        return f"http://{address_towards(client)}:{self.port}{link_path}"

    def find(self, token):
        with self._lock:
            return self._links.get(token)

    def allowed(self, link, address):
        try:
            return ipaddress.ip_address(address) == ipaddress.ip_address(link.client)
        except ValueError:
            return False

    def forget(self, link_path):
        token = link_path.rsplit("/", 1)[-1].split(".", 1)[0]
        with self._lock:
            self._links.pop(token, None)

