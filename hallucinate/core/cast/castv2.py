"""Talking to a Chromecast (Google's "Cast v2" protocol): a TLS connection to port 8009 carrying small framed
messages, each a protobuf "CastMessage" whose payload is JSON.

The protobuf has six plain fields, so it's written and read here by hand rather than pulling in protobuf.
Chromecasts present a certificate signed by Google's device authority, not one a computer can check by name, so
like every Cast sender this doesn't verify it: the connection is encrypted but the device isn't authenticated.
What a device can do to us is limited to what it says in its JSON, which is read with size caps and type checks.

The media itself isn't sent over this connection: the device is given an address on our own small media server
(hallucinate/castserver.py) and fetches the song from there."""
import itertools
import json
import socket
import ssl
import struct
import threading
import time

PORT = 8009
DEFAULT_MEDIA_RECEIVER = "CC1AD845"  # Google's built-in audio/video player app on every Cast device
NS_CONNECTION = "urn:x-cast:com.google.cast.tp.connection"
NS_HEARTBEAT = "urn:x-cast:com.google.cast.tp.heartbeat"
NS_RECEIVER = "urn:x-cast:com.google.cast.receiver"
NS_MEDIA = "urn:x-cast:com.google.cast.media"
SENDER = "sender-hallucinate"
RECEIVER = "receiver-0"
MAX_MESSAGE = 64 * 1024  # status messages are a few KB; anything bigger is refused and the connection closed
PING_EVERY = 5.0
DEAD_AFTER = 16.0  # no word from the device this long (it answers pings) and it's gone
LAUNCH_TIMEOUT = 20.0


class CastError(Exception):
    pass


# --- the CastMessage protobuf ---------------------------------------------------------------------------------
def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def encode(namespace, payload, source=SENDER, destination=RECEIVER):
    """A framed CastMessage carrying `payload` (a dict, sent as JSON)."""
    def text(field, value):
        raw = value.encode("utf-8")
        return _varint(field << 3 | 2) + _varint(len(raw)) + raw

    body = json.dumps(payload, separators=(",", ":"))
    msg = (_varint(1 << 3) + _varint(0)  # protocol_version CASTV2_1_0
           + text(2, source) + text(3, destination) + text(4, namespace)
           + _varint(5 << 3) + _varint(0)  # payload_type STRING
           + text(6, body))
    return struct.pack("!I", len(msg)) + msg


def _read_varint(data, pos):
    n, shift = 0, 0
    while True:
        if pos >= len(data) or shift > 63:
            raise CastError("bad varint")
        b = data[pos]
        n |= (b & 0x7F) << shift
        pos += 1
        if not b & 0x80:
            return n, pos
        shift += 7


def decode(msg):
    """(namespace, source, destination, payload dict or None) from one CastMessage's bytes."""
    fields, pos = {}, 0
    while pos < len(msg):
        key, pos = _read_varint(msg, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _read_varint(msg, pos)
        elif wire == 2:
            size, pos = _read_varint(msg, pos)
            if pos + size > len(msg):
                raise CastError("field runs off the end")
            value = msg[pos:pos + size]
            pos += size
        else:
            raise CastError("unexpected field type")
        fields[field] = value
    payload = None
    if 6 in fields:
        try:
            payload = json.loads(fields[6].decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):  # (JSON nested thousands deep, inside the size cap)
            payload = None
    if not isinstance(payload, dict):
        payload = None

    def s(n):
        v = fields.get(n, b"")
        return v.decode("utf-8", "replace") if isinstance(v, bytes) else ""
    return s(4), s(2), s(3), payload


def media_status(payload):
    """The parts of a MEDIA_STATUS we use, checked: {"session", "state", "idle_reason", "position", "duration"},
    or None."""
    status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(status, list) or not status or not isinstance(status[0], dict):
        return None
    st = status[0]

    def num(v):
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v >= 0 else None
    media = st.get("media") if isinstance(st.get("media"), dict) else {}
    session = st.get("mediaSessionId")
    return {
        "session": session if isinstance(session, int) and not isinstance(session, bool) else None,
        "state": st.get("playerState") if st.get("playerState") in ("IDLE", "PLAYING", "PAUSED", "BUFFERING") else "",
        "idle_reason": st.get("idleReason") if isinstance(st.get("idleReason"), str) else "",
        "position": num(st.get("currentTime")),
        "duration": num(media.get("duration")),
    }


def receiver_status(payload):
    """{"volume", "muted", "app": {"transport", "session"} or None} from a RECEIVER_STATUS, or None."""
    status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(status, dict):
        return None
    vol = status.get("volume") if isinstance(status.get("volume"), dict) else {}
    level = vol.get("level")
    out = {"volume": float(level) if isinstance(level, (int, float)) and not isinstance(level, bool)
           and 0 <= level <= 1 else None,
           "muted": vol.get("muted") is True, "app": None}
    apps = status.get("applications")
    for app in apps if isinstance(apps, list) else []:
        if isinstance(app, dict) and app.get("appId") == DEFAULT_MEDIA_RECEIVER:
            transport, session = app.get("transportId"), app.get("sessionId")
            if isinstance(transport, str) and isinstance(session, str) and 0 < len(transport) < 128:
                out["app"] = {"transport": transport, "session": session}
    return out


# --- a connection ---------------------------------------------------------------------------------------------
def tls_connect(host, port=PORT, timeout=10.0):
    raw = socket.create_connection((host, port), timeout=timeout)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # see the module docstring: Cast devices can't be checked by name
    return ctx.wrap_socket(raw)


class CastClient:
    """One connection to one Chromecast, playing through its built-in media player.

    `on_media(dict)` and `on_receiver(dict)` are called on the reader thread with checked statuses (see
    media_status/receiver_status); `on_closed(reason)` once when the connection ends. `connect` lets tests use a
    plain socket."""

    def __init__(self, host, port=PORT, on_media=None, on_receiver=None, on_closed=None, connect=tls_connect):
        self.host, self.port = host, port
        self.on_media, self.on_receiver, self.on_closed = on_media, on_receiver, on_closed
        self._connect = connect
        self._sock = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._app = None
        self._media_session = None
        self._app_ready = threading.Event()
        self._closed = threading.Event()
        self._heard = time.monotonic()
        self._reader = None
        self._pinger = None

    # plumbing
    def _send(self, namespace, payload, destination=RECEIVER):
        data = encode(namespace, payload, destination=destination)
        with self._lock:
            if self._sock is None:
                raise CastError("not connected")
            try:
                self._sock.sendall(data)
            except OSError as e:
                raise CastError(str(e)) from e

    def _request(self, namespace, payload, destination=RECEIVER):
        payload = dict(payload, requestId=next(self._ids))
        self._send(namespace, payload, destination)
        return payload["requestId"]

    @staticmethod
    def _recv_exact(sock, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise CastError("the device closed the connection")
            buf += chunk
        return bytes(buf)

    def _read_loop(self):
        reason = ""
        sock = self._sock  # (close() clears self._sock from another thread)
        try:
            while not self._closed.is_set() and sock is not None:
                size = struct.unpack("!I", self._recv_exact(sock, 4))[0]
                if size > MAX_MESSAGE:
                    raise CastError("message too big")
                namespace, source, _dest, payload = decode(self._recv_exact(sock, size))
                self._heard = time.monotonic()
                if payload is None:
                    continue
                self._handle(namespace, payload, source)
        except (OSError, CastError, struct.error) as e:
            reason = str(e)
        finally:
            self._finish(reason)

    def _app_gone(self):
        self._app = None
        self._media_session = None
        self._app_ready.clear()
        if self.on_media:
            self.on_media({"session": None, "state": "IDLE", "idle_reason": "INTERRUPTED",
                           "position": None, "duration": None})

    def _handle(self, namespace, payload, source=RECEIVER):
        kind = payload.get("type")
        if namespace == NS_HEARTBEAT and kind == "PING":
            try:
                self._send(NS_HEARTBEAT, {"type": "PONG"})
            except CastError:
                pass
        elif namespace == NS_CONNECTION and kind == "CLOSE":
            if self._app is not None and source == self._app["transport"]:
                self._app_gone()  # only the player app went away; the device is still there
            else:
                raise CastError("the device closed the session")
        elif namespace == NS_RECEIVER and kind == "RECEIVER_STATUS":
            status = receiver_status(payload)
            if status is None:
                return
            app = status["app"]
            if app and (self._app is None or app["transport"] != self._app["transport"]):
                self._app = app
                self._send(NS_CONNECTION, {"type": "CONNECT"}, destination=app["transport"])
                self._app_ready.set()
            elif app is None and self._app is not None and self._app_ready.is_set():
                self._app_gone()  # our player app was closed (someone cast something else to it)
            if self.on_receiver:
                self.on_receiver(status)
        elif namespace == NS_MEDIA and kind == "MEDIA_STATUS":
            status = media_status(payload)
            if status is None:
                return
            if status["session"] is not None:
                self._media_session = status["session"]
            if self.on_media:
                self.on_media(status)
        elif namespace == NS_MEDIA and kind in ("LOAD_FAILED", "LOAD_CANCELLED", "INVALID_REQUEST"):
            if self.on_media:
                self.on_media({"session": None, "state": "IDLE", "idle_reason": "ERROR",
                               "position": None, "duration": None})

    def _ping_loop(self):
        while not self._closed.wait(PING_EVERY):
            if time.monotonic() - self._heard > DEAD_AFTER:
                self._finish("the device stopped answering")
                return
            try:
                self._send(NS_HEARTBEAT, {"type": "PING"})
            except CastError as e:
                self._finish(str(e))
                return

    def _finish(self, reason):
        with self._lock:
            if self._closed.is_set():
                return
            self._closed.set()
            sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self._app_ready.set()  # wake a launch() that's waiting
        if self.on_closed:
            self.on_closed(reason)

    # what the app uses
    @property
    def connected(self):
        return self._sock is not None and not self._closed.is_set()

    def start(self, timeout=10.0):
        sock = self._connect(self.host, self.port, timeout)
        sock.settimeout(None)
        self._sock = sock
        self._heard = time.monotonic()
        self._send(NS_CONNECTION, {"type": "CONNECT", "origin": {},
                                   "userAgent": "Hallucinate", "senderInfo": {"sdkType": 2, "platform": 4}})
        self._reader = threading.Thread(target=self._read_loop, name="cast-reader", daemon=True)
        self._reader.start()
        self._pinger = threading.Thread(target=self._ping_loop, name="cast-ping", daemon=True)
        self._pinger.start()
        self._request(NS_RECEIVER, {"type": "GET_STATUS"})

    def launch(self, timeout=LAUNCH_TIMEOUT):
        """Opens the device's media player (or joins it if it's already open). Blocks until it's ready."""
        if self._app is None:
            self._app_ready.clear()
            self._request(NS_RECEIVER, {"type": "LAUNCH", "appId": DEFAULT_MEDIA_RECEIVER})
        if not self._app_ready.wait(timeout) or self._app is None:
            raise CastError("the device didn't open its media player")

    def load(self, url, content_type, title="", artist="", album="", image="", duration=None, position=0.0,
             live=False, autoplay=True):
        if self._app is None:
            self.launch()
        metadata = {"metadataType": 3, "title": title, "artist": artist, "albumName": album}
        if image:
            metadata["images"] = [{"url": image}]
        media = {"contentId": url, "contentUrl": url, "streamType": "LIVE" if live else "BUFFERED",
                 "contentType": content_type, "metadata": metadata}
        if duration:
            media["duration"] = float(duration)
        self._media_session = None
        self._request(NS_MEDIA, {"type": "LOAD", "sessionId": self._app["session"], "media": media,
                                 "autoplay": bool(autoplay), "currentTime": float(position)},
                      destination=self._app["transport"])

    def _media(self, kind, **extra):
        if self._app is None or self._media_session is None:
            return
        self._request(NS_MEDIA, dict(extra, type=kind, mediaSessionId=self._media_session),
                      destination=self._app["transport"])

    def play(self):
        self._media("PLAY")

    def pause(self):
        self._media("PAUSE")

    def seek(self, seconds):
        self._media("SEEK", currentTime=max(0.0, float(seconds)))

    def stop_media(self):
        self._media("STOP")

    def poll(self):
        if self._app is not None:
            self._request(NS_MEDIA, {"type": "GET_STATUS"}, destination=self._app["transport"])

    def set_volume(self, level):
        self._request(NS_RECEIVER, {"type": "SET_VOLUME", "volume": {"level": min(1.0, max(0.0, float(level)))}})

    def set_muted(self, muted):
        self._request(NS_RECEIVER, {"type": "SET_VOLUME", "volume": {"muted": bool(muted)}})

    def close(self, stop_app=True):
        """Ends the connection; with `stop_app` the device's player is closed too (its screen goes back to idle)."""
        if self.connected:
            try:
                if stop_app and self._app is not None:
                    self._request(NS_RECEIVER, {"type": "STOP", "sessionId": self._app["session"]})
                self._send(NS_CONNECTION, {"type": "CLOSE"})
            except CastError:
                pass
        self._finish("")
