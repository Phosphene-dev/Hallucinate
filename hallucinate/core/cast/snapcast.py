"""Snapcast (https://github.com/badaix/snapcast): playing to a Snapcast server's speakers, every room in step.

Unlike a Chromecast, a Snapcast server doesn't fetch songs: it plays one live stream of audio to its rooms
("groups" of speakers). So Hallucinate adds a stream of its own to the server while it plays there (JSON-RPC
Stream.AddStream, nothing to set up on the server), switches the chosen room to it, and sends the audio itself,
at the pace it's heard: 48 kHz, 16-bit stereo PCM. When it stops, the room goes back to what it was playing and
the stream is taken away again.

The audio is Hallucinate's sound (the equalizer, ReplayGain and so on: see Casting.media_for), as WAV files the
decoding helper writes. The feeder plays them one after another with no gap, and keeps time: pause sends
silence, seek jumps in the file, and it says when a song ends or the next one begins.

The server is only ever reached on the local network (net.connect_local), its answers are size-checked, and
the stream's port only takes the connection from the server's own address."""
import json
import os
import socket
import threading
import time
import wave

from .. import net

CONTROL_PORT = 1705
SERVICE = "_snapcast-jsonrpc._tcp.local"
RATE, CHANNELS, WIDTH = 48000, 2, 2
FRAME = CHANNELS * WIDTH
SAMPLE_FORMAT = f"{RATE}:{WIDTH * 8}:{CHANNELS}"
CHUNK_FRAMES = RATE // 50  # 20 ms at a time
LEAD_S = 0.25  # how far ahead of real time the stream runs (smaller: quicker to pause and seek)
SERVER_BUFFER_S = 1.0  # what a Snapcast server holds back before the speakers play (its default)
MAX_LINE = 4 * 1024 * 1024
STREAM_NAME = "Hallucinate"


class SnapcastError(OSError):
    pass


# --- the server's controls (JSON-RPC over TCP, one JSON object a line) ---------------------------------------
class Control:
    def __init__(self, host, port=CONTROL_PORT, timeout=5.0, connect=None):
        self.host, self.port = host, int(port)
        self._sock = (connect or net.connect_local)(host, self.port, timeout)
        self._sock.settimeout(timeout)
        self._buf = b""
        self._id = 0
        self._lock = threading.Lock()

    def call(self, method, params=None):
        with self._lock:
            self._id += 1
            mine = self._id
            self._sock.sendall((json.dumps({"id": mine, "jsonrpc": "2.0", "method": method,
                                            "params": params or {}}) + "\n").encode("utf-8"))
            while True:
                msg = self._line()
                if not isinstance(msg, dict) or msg.get("id") != mine:
                    continue  # (a notification, or an answer to something else)
                if "error" in msg:
                    err = msg["error"]
                    raise SnapcastError(str(err.get("message") if isinstance(err, dict) else err)[:200])
                return msg.get("result")

    def _line(self):
        while b"\n" not in self._buf:
            more = self._sock.recv(65536)
            if not more:
                raise SnapcastError("the Snapcast server closed the connection")
            self._buf += more
            if len(self._buf) > MAX_LINE:
                raise SnapcastError("an answer from the Snapcast server was too long")
        line, self._buf = self._buf.split(b"\n", 1)
        try:
            return json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeError):
            return None

    def status(self):
        result = self.call("Server.GetStatus")
        server = result.get("server") if isinstance(result, dict) else None
        if not isinstance(server, dict):
            raise SnapcastError("the Snapcast server's status made no sense")
        return server

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass


def _text(value, limit=100):
    return str(value or "").strip()[:limit]


def groups(server_status):
    """The server's rooms: [{"id", "name", "stream", "clients": [{"id", "name", "connected", "volume", "muted"}]}].
    A room without a name of its own is called after its speakers."""
    out = []
    for g in server_status.get("groups") or []:
        if not isinstance(g, dict) or not g.get("id"):
            continue
        clients = []
        for c in g.get("clients") or []:
            if not isinstance(c, dict):
                continue
            cfg = c.get("config") if isinstance(c.get("config"), dict) else {}
            host = c.get("host") if isinstance(c.get("host"), dict) else {}
            vol = cfg.get("volume") if isinstance(cfg.get("volume"), dict) else {}
            clients.append({"id": _text(c.get("id"), 200), "name": _text(cfg.get("name")) or _text(host.get("name")),
                            "connected": bool(c.get("connected")), "volume": int(vol.get("percent") or 0),
                            "muted": bool(vol.get("muted"))})
        name = _text(g.get("name")) or ", ".join(c["name"] for c in clients if c["name"])[:100] or "Snapcast"
        out.append({"id": _text(g.get("id"), 200), "name": name, "stream": _text(g.get("stream_id"), 200),
                    "clients": clients})
    return out


def devices(host, port=CONTROL_PORT, server_name="", connect=None):
    """The rooms of the Snapcast server at host:port as cast devices (each with a speaker playing)."""
    ctl = Control(host, port, connect=connect)
    try:
        status = ctl.status()
    finally:
        ctl.close()
    label = server_name or _text((status.get("host") or {}).get("name") if isinstance(status.get("host"), dict) else "")
    out = {}
    for g in groups(status):
        if not any(c["connected"] for c in g["clients"]):
            continue
        dev_id = f"snapcast:{host}:{port}:{g['id']}"
        out[dev_id] = {"id": dev_id, "kind": "snapcast", "name": g["name"], "model": "Snapcast" + (
            f" · {label}" if label else ""), "host": host, "port": int(port), "group": g["id"]}
    return out


def discover(timeout=2.0, interfaces=("",), browse=None, connect=None):
    """Snapcast servers announced on the network, and their rooms: {device id: device}."""
    from . import mdns

    found = {}
    for server in (browse or mdns.browse)(timeout=timeout, interfaces=interfaces, service=SERVICE).values():
        try:
            found.update(devices(server["host"], server["port"], server.get("name", ""), connect=connect))
        except (OSError, ValueError):
            continue
    return found


def local_address_for(host):
    """This computer's address that `host` reaches it on (the stream is offered there)."""
    if host in ("127.0.0.1", "localhost", "::1"):
        return "127.0.0.1"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, CONTROL_PORT))
        return s.getsockname()[0]
    finally:
        s.close()


# --- the stream ------------------------------------------------------------------------------------------------
class _Source:
    """A WAV file (48 kHz, 16-bit stereo) being read, from a frame on."""

    def __init__(self, path, start_s=0.0, end_s=0.0, tag=None):
        self.tag = tag
        self.wav = wave.open(path, "rb")
        if (self.wav.getframerate(), self.wav.getnchannels(), self.wav.getsampwidth()) != (RATE, CHANNELS, WIDTH):
            self.wav.close()
            raise SnapcastError("the song wasn't got ready in the stream's format")
        self.frames = self.wav.getnframes()
        self.end = min(self.frames, int(end_s * RATE)) if end_s else self.frames
        self.at = max(0, min(self.end, int(start_s * RATE)))
        self.wav.setpos(self.at)

    def read(self, frames):
        frames = max(0, min(frames, self.end - self.at))
        data = self.wav.readframes(frames) if frames else b""
        self.at += len(data) // FRAME
        return data

    def seek(self, seconds):
        self.at = max(0, min(self.end, int(seconds * RATE)))
        self.wav.setpos(self.at)

    def close(self):
        try:
            self.wav.close()
        except Exception:  # noqa: BLE001
            pass


class Feeder:
    """Serves the stream to the Snapcast server: it connects to us (mode=client) on `port` from `server_ip`.

    on_event(kind, tag): "started" (a song began to be heard), "ended" (it finished, nothing next), "advanced"
    (it went straight on into the next song), "lost" (the server went away and didn't come back). Called on the
    feeder's thread."""

    def __init__(self, bind_host, server_ip, on_event=None, clock=time.monotonic):
        self.server_ip = server_ip
        self.on_event = on_event or (lambda kind, tag: None)
        self._clock = clock
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((bind_host, 0))
        self._sock.listen(2)
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        self._lock = threading.Lock()
        self._current = self._next = None
        self._paused = True
        self._closed = False
        self._ending = None  # (tag, seconds it ends at, when that's heard): a song still playing out of the buffer
        self.connected = threading.Event()
        self._thread = threading.Thread(target=self._run, name="snapcast-stream", daemon=True)
        self._thread.start()

    def uri(self, host):
        return f"tcp://{host}:{self.port}?name={STREAM_NAME}&mode=client&sampleformat={SAMPLE_FORMAT}"

    # --- commands --------------------------------------------------------------------------------------------
    def load(self, path, start_s=0.0, end_s=0.0, tag=None, play=True):
        source = _Source(path, start_s, end_s, tag)
        with self._lock:
            self._ending = None
            for old in (self._current, self._next):
                if old is not None:
                    old.close()
            self._current, self._next = source, None
            self._paused = not play

    def queue_next(self, path, tag=None):
        source = _Source(path, tag=tag) if path else None
        with self._lock:
            if self._next is not None:
                self._next.close()
            self._next = source

    def pause(self):
        with self._lock:
            self._paused = True

    def play(self):
        with self._lock:
            self._paused = False

    def seek(self, seconds):
        with self._lock:
            if self._current is not None:
                self._current.seek(seconds)

    def stop(self):
        with self._lock:
            self._ending = None
            for old in (self._current, self._next):
                if old is not None:
                    old.close()
            self._current = self._next = None
            self._paused = True

    def position(self):
        """(tag, seconds) of what the speakers are playing now, as near as can be told: what's been sent less
        what's still on its way (a song that just ended is still heard for that long)."""
        with self._lock:
            now = self._clock()
            if self._ending is not None:
                tag, end, heard = self._ending
                if now < heard:
                    return tag, max(0.0, end - (heard - now))
                self._ending = None
            src = self._current
            if src is None:
                return None, 0.0
            behind = (LEAD_S + SERVER_BUFFER_S) if not self._paused else 0.0
            return src.tag, max(0.0, src.at / RATE - behind)

    def close(self):
        self._closed = True
        self.stop()
        try:
            self._sock.close()
        except OSError:
            pass

    # --- the stream's thread -----------------------------------------------------------------------------------
    def _run(self):
        misses = 0
        while not self._closed:
            try:
                conn, (ip, _port) = self._sock.accept()
            except socket.timeout:
                if self.connected.is_set():
                    misses += 1
                    if misses > 40:  # 20 s without the server coming back
                        self.on_event("lost", None)
                        return
                continue
            except OSError:
                return
            if ip != self.server_ip and not (self.server_ip == "127.0.0.1" and ip.startswith("127.")):
                conn.close()  # only the Snapcast server may take the stream
                continue
            misses = 0
            self.connected.set()
            try:
                self._send(conn)
            except OSError:
                pass
            finally:
                conn.close()

    def _send(self, conn):
        conn.settimeout(5.0)
        start = self._clock()
        sent = 0  # frames sent since the server connected
        silence = b"\0" * (CHUNK_FRAMES * FRAME)
        while not self._closed:
            ahead = sent / RATE - (self._clock() - start)
            if ahead > LEAD_S:
                time.sleep(min(0.02, ahead - LEAD_S))
                continue
            events = []
            with self._lock:
                if self._paused or self._current is None:
                    data = silence
                else:
                    src = self._current
                    data = src.read(CHUNK_FRAMES)
                    if len(data) < len(silence):  # this song is over: on into the next, or silence
                        nxt = self._next
                        src.close()
                        self._ending = (src.tag, src.end / RATE, self._clock() + LEAD_S + SERVER_BUFFER_S)
                        self._current, self._next = nxt, None
                        if nxt is not None:
                            data += nxt.read(CHUNK_FRAMES - len(data) // FRAME)
                            events.append(("advanced", nxt.tag))
                        else:
                            self._paused = True
                            events.append(("ended", src.tag))
                        data += silence[len(data):]
            conn.sendall(data)
            sent += len(data) // FRAME
            for kind, tag in events:
                # heard once what's ahead of the speakers has played: say so then
                delay = LEAD_S + SERVER_BUFFER_S
                threading.Timer(delay, self.on_event, (kind, tag)).start()


def write_wav(path, frames):
    """A WAV in the stream's format (for tests)."""
    with wave.open(path, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(WIDTH)
        w.setframerate(RATE)
        w.writeframes(frames)
    return os.path.getsize(path)
