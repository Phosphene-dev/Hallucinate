"""Handing what's playing to another computer running Hallucinate (`handoff` in QML), and taking it from one.

Computers pair once, the way a phone does: the other computer shows a code (Settings → Remote & web → Pair a
device), this one enters it and keeps the key it gets in the system keyring. Both need Remote & web on with other
devices on the network allowed. While that's on, each answers a small broadcast on the local network, so paired
and unpaired computers show up in the cast menu by themselves; an address can be typed in too.

Handing off sends the queue (what identifies each song, never a path), the place in the song, shuffle, repeat
and whether it was playing. The other computer plays each song from its own library when it has it (see
core/handoff.py) and the rest from this one, through a link only it can use; this computer then pauses. The
receiving side only ever streams from the computer that sent the handoff, whatever the message says."""
import json
import logging
import os
import secrets
import socket
import threading
import time

from PySide6.QtCore import Property, QObject, QSettings, Qt, QTimer, Signal, Slot

from . import keyringwait
from .core import handoff as core
from .core import net
from .core.i18n import fill, translate

logger = logging.getLogger(__name__)

DISCOVERY_PORT = 8485
HELLO = b"HALLUCINATE-DISCOVER 1"
ANSWER = b"HALLUCINATE-HERE 1 "
KEYRING_SERVICE = "Hallucinate Paired computers"
SEARCH_S = 2.0
ANSWERS_PER_MINUTE = 120  # a responder flooded with questions stops answering for a moment
TIMEOUT_S = 8.0


class PeerError(Exception):
    pass


# --- talking to another Hallucinate (blocking: worker threads) --------------------------------------------------
def _post(host, port, path, body, key=""):
    headers = {"Content-Type": "application/json", "X-Hallucinate": "1"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        status, raw = net.local_http(f"http://{host}:{int(port)}{path}", "POST", json.dumps(body).encode("utf-8"),
                                     headers, timeout=TIMEOUT_S, limit=256 * 1024)
    except (OSError, ValueError) as e:
        raise PeerError(str(e) or type(e).__name__) from e
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeError, ValueError):
        data = {}
    if status != 200:
        message = data.get("error") if isinstance(data, dict) else ""
        raise PeerError(translate("Api", message) if isinstance(message, str) and message else f"HTTP {status}")
    return data if isinstance(data, dict) else {}


def pair_with(host, port, code, my_name):
    """Pairs with the computer at host:port using the code it shows; returns the key it hands back."""
    data = _post(host, port, "/api/pair", {"code": str(code).strip(), "name": my_name, "token": True})
    key = data.get("key")
    if not isinstance(key, str) or not 16 <= len(key) <= 200:
        raise PeerError(translate("Handoff", "The other computer didn't give a key"))
    return key


def call(host, port, key, method, params=None):
    return _post(host, port, "/api/call", {"method": method, "params": params or {}}, key).get("result")


# --- finding other computers -------------------------------------------------------------------------------------
def search(timeout=SEARCH_S, interfaces=("",), my_id=""):
    """Other computers running Hallucinate that answer on the local network: {id: {"id", "name", "host", "port"}}."""
    found, socks = {}, []
    for iface in interfaces:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((iface, 0))
            s.setblocking(False)
            s.sendto(HELLO, ("255.255.255.255", DISCOVERY_PORT))
            socks.append(s)
        except OSError:
            continue
    import select

    deadline = time.monotonic() + timeout
    try:
        while socks and len(found) < 32:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            ready, _, _ = select.select(socks, [], [], left)
            for s in ready:
                try:
                    data, (sender, _p) = s.recvfrom(1024)
                except OSError:
                    continue
                peer = _read_answer(data, sender)
                if peer and peer["id"] != my_id:
                    found[peer["id"]] = peer
    finally:
        for s in socks:
            s.close()
    return found


def _read_answer(data, sender):
    if not data.startswith(ANSWER) or not net.is_local_address(sender):
        return None
    try:
        info = json.loads(data[len(ANSWER):].decode("utf-8"))
    except (UnicodeError, ValueError):
        return None
    if not isinstance(info, dict):
        return None
    port, pid, name = info.get("port"), info.get("id"), info.get("name")
    if not (isinstance(port, int) and 0 < port < 65536 and isinstance(pid, str) and 8 <= len(pid) <= 64):
        return None
    return {"id": pid, "name": (name if isinstance(name, str) else "")[:60] or sender, "host": sender,
            "port": port}


class Responder:
    """Answers other computers' searches (only while the remote takes connections from the network). Says only
    this computer's name, its remote's port and an id."""

    def __init__(self, info):
        self._info = info  # () -> {"id", "name", "port"} or None (not answering now)
        self._sock = None
        self._thread = None
        self._stop = threading.Event()
        self._answered = []

    def start(self):
        if self._sock is not None:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", DISCOVERY_PORT))
            s.settimeout(0.5)
        except OSError as e:
            logger.info("Can't answer handoff searches on port %s: %s", DISCOVERY_PORT, e)
            return False
        self._sock = s
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="handoff-responder", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock is not None:
            sock.close()

    def _run(self):
        sock = self._sock
        while not self._stop.is_set() and sock is not None:
            try:
                data, addr = sock.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                return
            if data != HELLO or not net.is_local_address(addr[0]):
                continue
            now = time.monotonic()
            self._answered = [t for t in self._answered if now - t < 60]
            if len(self._answered) >= ANSWERS_PER_MINUTE:
                continue
            info = self._info()
            if not info:
                continue
            self._answered.append(now)
            try:
                sock.sendto(ANSWER + json.dumps(info).encode("utf-8"), addr)
            except OSError:
                pass


# --- the app's side ----------------------------------------------------------------------------------------------
def _keyring():
    from .servers import _keyring as servers_keyring

    return servers_keyring()


class Handoff(QObject):
    changed = Signal()
    notice = Signal(str)
    _done = Signal(object)  # (callable to run on the window's thread)

    def __init__(self, player=None, library=None, web_remote=None, parent=None):
        super().__init__(parent)
        self._settings = QSettings()
        self._player, self._library, self._remote = player, library, web_remote
        self._done.connect(lambda fn: fn(), Qt.ConnectionType.QueuedConnection)
        self._id = str(self._settings.value("handoff/id", "") or "")
        if not 8 <= len(self._id) <= 64:
            self._id = secrets.token_hex(8)
            self._settings.setValue("handoff/id", self._id)
        self._peers = self._load_peers()
        self._found = {}
        self._searching = False
        self._busy = ""
        self._error = ""
        self._links = {}  # token -> core.HandoffLink (songs another computer may stream from this one)
        self._responder = Responder(self._answer)
        self._watch = QTimer(self, interval=5000, timeout=self._sync_responder)
        self._watch.start()
        self.search_fn = search  # (tests swap these)
        self.http = {"pair": pair_with, "call": call}

    # --- this computer ------------------------------------------------------------------------------------------
    def my_name(self):
        name = str(self._settings.value("handoff/name", "") or "") or socket.gethostname() or "Hallucinate"
        return name[:60]

    def _answer(self):
        r = self._remote
        if r is None or not (r.isRunning and r.network):
            return None
        return {"id": self._id, "name": self.my_name(), "port": int(r.port)}

    def _sync_responder(self):
        if self._answer() is not None:
            self._responder.start()
        else:
            self._responder.stop()

    # --- paired computers ---------------------------------------------------------------------------------------
    def _load_peers(self):
        try:
            peers = json.loads(str(self._settings.value("handoff/peers", "[]") or "[]"))
        except ValueError:
            peers = []
        out = []
        for p in peers if isinstance(peers, list) else []:
            if (isinstance(p, dict) and isinstance(p.get("id"), str) and net.is_local_address(p.get("host", ""))
                    and isinstance(p.get("port"), int)):
                out.append({"id": p["id"], "name": str(p.get("name") or p["host"])[:60], "host": p["host"],
                            "port": p["port"]})
        return out

    def _save_peers(self):
        self._settings.setValue("handoff/peers", json.dumps(self._peers))

    @Property("QVariantList", notify=changed)
    def computers(self):
        """Paired computers first (whether they answered the last search), then ones found but not paired."""
        out = [dict(p, paired=True, online=p["id"] in self._found) for p in self._peers]
        paired = {p["id"] for p in self._peers}
        out += [dict(f, paired=False, online=True) for f in self._found.values() if f["id"] not in paired]
        return out

    @Property(bool, notify=changed)
    def searching(self):
        return self._searching

    @Property(str, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def error(self):
        return self._error

    def _fail(self, message):
        self._busy = ""
        self._error = message
        self.changed.emit()
        self.notice.emit(message)

    @Slot()
    def refresh(self):
        if self._searching or net.is_offline():
            return
        self._searching = True
        self.changed.emit()
        from .core.cast.upnp import local_interfaces

        def run():
            try:
                found = self.search_fn(SEARCH_S, local_interfaces(), self._id)
            except Exception as e:  # noqa: BLE001
                logger.info("Looking for other computers failed: %s", e)
                found = {}
            self._done.emit(lambda: self._on_found(found))
        threading.Thread(target=run, name="handoff-search", daemon=True).start()

    def _on_found(self, found):
        self._searching = False
        self._found = found
        for p in self._peers:  # a paired computer that moved to another address
            if p["id"] in found and (found[p["id"]]["host"], found[p["id"]]["port"]) != (p["host"], p["port"]):
                p["host"], p["port"] = found[p["id"]]["host"], found[p["id"]]["port"]
                self._save_peers()
        self.changed.emit()

    @Slot(str, int, str, str)
    def pair(self, host, port, code, name=""):
        """Pairs with the computer at host:port with the code it shows (Settings → Remote & web on it)."""
        host = host.strip()
        if not net.is_local_address(host):
            self._fail(translate("Handoff", "Type the other computer's address on your network (like 192.168.1.20)"))
            return
        found = next((f for f in self._found.values() if f["host"] == host and f["port"] == port), None)
        peer_id = found["id"] if found else "addr-" + host.replace(":", "-") + f"-{port}"
        name = (name or (found or {}).get("name") or host)[:60]
        self._busy, self._error = name, ""
        self.changed.emit()

        def run():
            try:
                key = self.http["pair"](host, port, code, self.my_name())
                kr = _keyring()
                problem = keyringwait.call(lambda: kr.set_password(KEYRING_SERVICE, peer_id, key), timeout=10)
                if problem:
                    raise PeerError(str(problem))
            except Exception as e:  # noqa: BLE001
                message = fill(translate("Handoff", "Couldn't pair with %1: %2"), name, str(e) or type(e).__name__)
                self._done.emit(lambda: self._fail(message))
                return
            self._done.emit(lambda: self._paired(peer_id, name, host, port))
        threading.Thread(target=run, name="handoff-pair", daemon=True).start()

    def _paired(self, peer_id, name, host, port):
        self._peers = [p for p in self._peers if p["id"] != peer_id] + [
            {"id": peer_id, "name": name, "host": host, "port": port}]
        self._save_peers()
        self._busy = ""
        self.changed.emit()
        self.notice.emit(fill(translate("Handoff", "Paired with %1"), name))

    @Slot(str)
    def forget(self, peer_id):
        self._peers = [p for p in self._peers if p["id"] != peer_id]
        self._save_peers()
        try:
            kr = _keyring()
            keyringwait.call(lambda: kr.delete_password(KEYRING_SERVICE, peer_id), timeout=5)
        except Exception:  # noqa: BLE001 - nothing kept, or no keyring: nothing to remove
            pass
        self.changed.emit()

    # --- handing off ------------------------------------------------------------------------------------------
    @Slot(str)
    def handTo(self, peer_id):
        """Sends what's playing to a paired computer, which carries on from here; this one pauses."""
        peer = next((p for p in self._peers if p["id"] == peer_id), None)
        player = self._player
        if peer is None or player is None or self._busy:
            return
        if not player.hasTrack:
            self._fail(translate("Handoff", "Nothing is playing to hand over"))
            return
        payload, paths = self._describe_queue()
        stream = ""
        r = self._remote
        if any(paths) and r is not None and r.isRunning and r.network:
            link = core.HandoffLink(peer["host"], paths)
            self._links = {t: v for t, v in self._links.items() if not v.expired}
            self._links[link.token] = link
            try:
                from .core.cast.mediaserver import address_towards

                stream = f"http://{address_towards(peer['host'])}:{int(r.port)}/h/{link.token}/"
            except OSError:
                stream = ""
        payload["stream"] = stream
        self._busy, self._error = peer["name"], ""
        self.changed.emit()

        def run():
            try:
                key = self._read_key(peer["id"])
                result = self.http["call"](peer["host"], peer["port"], key, "handoff.receive", payload)
            except Exception as e:  # noqa: BLE001
                message = fill(translate("Handoff", "Couldn't hand over to %1: %2"), peer["name"],
                               str(e) or type(e).__name__)
                self._done.emit(lambda: self._fail(message))
                return
            self._done.emit(lambda: self._handed(peer, result if isinstance(result, dict) else {}))
        threading.Thread(target=run, name="handoff-send", daemon=True).start()

    def _read_key(self, peer_id):
        kr = _keyring()
        got = keyringwait.read(lambda k: kr.get_password(KEYRING_SERVICE, k), (peer_id,), timeout=10, patient=True)
        key = (got or {}).get("values", {}).get(peer_id) if got and not got.get("error") else None
        if not key:
            raise PeerError(translate("Handoff", "The pairing was lost: pair again"))
        return key

    def _describe_queue(self):
        from .core.kinds import is_url
        from .player import track_file

        player = self._player
        queue = player.queue
        start = max(0, player.currentIndex - core.MAX_SONGS // 2)
        part = queue[start:start + core.MAX_SONGS]
        songs, paths = [], []
        for t in part:
            songs.append(core.describe(t))
            f = track_file(t)
            # only this computer's own files are streamed (a CUE song plays its part of the album's file there)
            paths.append(f if isinstance(f, str) and f and not is_url(f) and os.path.isfile(f)
                         and not t.get("file") else None)
        payload = {"from": self.my_name(), "songs": songs, "index": player.currentIndex - start,
                   "position": int(player.position), "playing": bool(player.playing),
                   "shuffle": bool(player.shuffle), "repeat": int(player.repeat), "streamable": [p is not None for p in paths]}
        return payload, paths

    def _handed(self, peer, result):
        self._busy = ""
        if self._player is not None and self._player.playing:
            self._player.pause()
        self.changed.emit()
        missing = int(result.get("missing") or 0)
        message = fill(translate("Handoff", "Now playing on %1"), peer["name"])
        if missing:
            message += "  ·  " + fill(translate("Handoff", "%1 songs it doesn't have play from here"), missing)
        self.notice.emit(message)

    def stream_link(self, token):
        """The handoff link with this token, if it's still good (the web remote serves its songs)."""
        link = self._links.get(token)
        return None if link is None or link.expired else link

    # --- being handed to ---------------------------------------------------------------------------------------
    def receive(self, params, caller):
        """Another computer handed what it's playing to this one (on the window's thread). `caller` is the address
        the request came from: songs are only ever streamed from there."""
        player, library = self._player, self._library
        if player is None or library is None or not isinstance(params, dict):
            raise ValueError("can't take it here")
        songs = [core.clean(s) for s in (params.get("songs") or [])[:core.MAX_SONGS]]
        streamable = params.get("streamable") if isinstance(params.get("streamable"), list) else []
        stream = params.get("stream") if isinstance(params.get("stream"), str) else ""
        if stream and not _same_host(stream, caller):
            stream = ""  # a link to somewhere else than the computer that sent this: never followed
        found = core.match(library._db.conn, songs)
        rows = self._rows_for([p for p in found if p])
        tracks, kept_index, missing = [], 0, 0
        index = params.get("index") if isinstance(params.get("index"), int) else 0
        for i, (song, path) in enumerate(zip(songs, found)):
            if i == index:
                kept_index = len(tracks)
            if song is None:
                continue
            if path and path in rows:
                tracks.append(rows[path])
            elif song["kind"] == "station":
                tracks.append({"path": song["url"], "kind": "station", "station": song.get("station") or song["title"],
                               "title": song.get("station") or song["title"], "artist": "", "album": "",
                               "duration": 0, "artUrl": ""})
            elif stream and i < len(streamable) and streamable[i] is True:
                missing += 1
                tracks.append({"path": f"{stream}{i}", "title": song["title"], "artist": song["artist"],
                               "album": song["album"], "album_artist": song["album_artist"],
                               "duration": song["duration"], "track_no": song["track_no"],
                               "disc_no": song["disc_no"], "artUrl": "", "kind": "music", "handoff": True})
            else:
                missing += 1  # (an episode, or a song the other computer can't stream: not playable here)
        if not tracks:
            raise ValueError(translate("Handoff", "None of these songs can play here"))
        player.setShuffle(bool(params.get("shuffle")))
        repeat = params.get("repeat")
        player.setRepeat(repeat if isinstance(repeat, int) else 0)
        position = params.get("position") if isinstance(params.get("position"), int) else 0
        player.playList(tracks, min(kept_index, len(tracks) - 1), start_ms=max(0, position),
                        autoplay=bool(params.get("playing")))
        sender = params.get("from") if isinstance(params.get("from"), str) else ""
        self.notice.emit(fill(translate("Handoff", "Carrying on from %1"), sender[:60] or caller))
        return {"ok": True, "songs": len(tracks), "missing": missing}

    def _rows_for(self, paths):
        from .library import decorate

        out = {}
        db = self._library._db
        for i in range(0, len(paths), 500):
            chunk = paths[i:i + 500]
            rows = db._rows(f"SELECT * FROM tracks WHERE path IN ({','.join('?' * len(chunk))})", chunk)
            for r in decorate(rows):
                out[r["path"]] = r
        return out

    def shutdown(self):
        self._watch.stop()
        self._responder.stop()
        for link in self._links.values():
            link.revoke()
        # let go of what points back here (the web remote, the responder), so nothing keeps the other alive
        if self._remote is not None and getattr(self._remote, "handoff", None) is self:
            self._remote.handoff = None
        self._remote = self._player = self._library = None
        self._responder._info = lambda: None


def _same_host(url, caller):
    import urllib.parse

    try:
        parts = urllib.parse.urlsplit(url)
        return (parts.scheme == "http" and parts.hostname is not None and net.same_address(parts.hostname, caller)
                and parts.path.startswith("/h/"))
    except ValueError:
        return False
