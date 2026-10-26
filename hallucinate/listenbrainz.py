"""ListenBrainz scrobbling (token in the system keyring, offline queue) and listen-history import."""
import json
import logging
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request

import keyring
from PySide6.QtCore import Property, QObject, QSettings, QTimer, Signal, Slot

from . import __version__, keyringwait
from .core import net
from .core.kinds import counts_for_scrobbling, scrobble_fields
from .scrobbling import REJECTED_KEPT, REPLAY_START_MS, heard_ms, listen_point, listen_threshold

DEFAULT_URL = "https://api.listenbrainz.org"
KEYRING_SERVICE = "Hallucinate ListenBrainz"
MAX_RETRY_SECONDS = 900
MAX_BATCH = 100  # listens sent in one submit-listens ("import" for more than one)
logger = logging.getLogger(__name__)


class Rejected(PermissionError):
    """ListenBrainz refused the request for good (HTTP 400, 401 or 403): sending it again won't help."""

    def __init__(self, code, text):
        super().__init__(text)
        self.code = code


def _words(exc):
    """A network or parsing error in plain words (never the request, which holds the API key)."""
    if isinstance(exc, ValueError) and not isinstance(exc, OSError):
        return "its answer couldn't be read"
    return net.describe(exc)


def normalize_server(text):
    """A server's ListenBrainz API address from what someone typed: "" for listenbrainz.org itself;
    https:// added when there's no scheme; a pasted endpoint ("…/1/submit-listens") cut back to the base. Self-hosted
    servers speak the same API under a path of their own (Maloja and Koito: https://host/apis/listenbrainz).
    Raises ValueError for anything but an http(s) address."""
    from urllib.parse import urlsplit

    text = (text or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Enter the server's address, such as https://maloja.example.com/apis/listenbrainz")
    path = parts.path.rstrip("/")
    for tail in ("/1/submit-listens", "/1/validate-token", "/1"):
        if path.endswith(tail):
            path = path[: -len(tail)]
            break
    base = f"{parts.scheme}://{parts.netloc}{path}"
    return "" if base.rstrip("/") == DEFAULT_URL else base


def server_label(base):
    """How a server is named in messages: ListenBrainz, or its host."""
    from urllib.parse import urlsplit

    return "ListenBrainz" if not base or base == DEFAULT_URL else (urlsplit(base).hostname or base)


def lb_request(base, path, token=None, payload=None, params=None):
    url = base.rstrip("/") + path + (("?" + urlencode(params)) if params else "")
    headers = {"User-Agent": "Hallucinate/0.3"}
    data = None
    if token:
        headers["Authorization"] = f"Token {token}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        with net.urlopen(Request(url, data=data, headers=headers), timeout=20) as r:
            body = r.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        if exc.code in (400, 401, 403):  # rejected for good, retrying won't help
            raise Rejected(exc.code, f"ListenBrainz rejected the request ({exc.code})") from exc
        raise RuntimeError(f"Couldn't reach ListenBrainz: {_words(exc)}") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Couldn't reach ListenBrainz: {_words(exc)}") from exc


def track_metadata(track):
    track = scrobble_fields(track)
    artist, title = track.get("artist", ""), track.get("title", "")
    if not artist or not title:
        raise ValueError("ListenBrainz requires a track title and artist.")
    info = {"media_player": "Hallucinate", "submission_client": "Hallucinate"}
    dur = int(float(track.get("duration", 0) or 0))
    if dur > 0:
        info["duration"] = dur
    if track.get("track_no"):
        info["tracknumber"] = int(track["track_no"])
    meta = {"artist_name": artist, "track_name": title, "additional_info": info}
    if track.get("album"):
        meta["release_name"] = track["album"]
    return meta


def parse_listens(data):
    out = []
    for item in (data.get("payload", {}) or {}).get("listens", []):
        meta = item.get("track_metadata") or {}
        out.append({"ts": item.get("listened_at"), "artist": meta.get("artist_name", ""),
                    "title": meta.get("track_name", ""), "album": meta.get("release_name", "")})
    return out


def parse_lastfm_page(data):
    tracks = (data.get("recenttracks") or {})
    items = tracks.get("track", [])
    if isinstance(items, dict):
        items = [items]
    out = []
    for t in items:
        ts = (t.get("date") or {}).get("uts")  # no date => currently playing
        if not ts:
            continue
        out.append({"ts": int(ts), "artist": (t.get("artist") or {}).get("#text", ""),
                    "title": t.get("name", ""), "album": (t.get("album") or {}).get("#text", "")})
    pages = int(((tracks.get("@attr") or {}).get("totalPages")) or 1)
    return out, pages


def fetch_listenbrainz_history(base, user, token=None, progress=None, limit=100000):
    items, max_ts = [], None
    while len(items) < limit:
        params = {"count": 1000}
        if max_ts:
            params["max_ts"] = max_ts
        page = parse_listens(lb_request(base, f"/1/user/{quote(user, safe='')}/listens", token, params=params))
        if not page:
            break
        items += page
        oldest = min(p["ts"] for p in page if p["ts"])
        if max_ts is not None and oldest >= max_ts:
            max_ts = max_ts - 1
        else:
            max_ts = oldest
        if progress:
            progress(len(items))
    return items


def fetch_lastfm_history(user, api_key, progress=None, max_pages=500):
    from .scrobbling import API_URL
    items, page, pages = [], 1, 1
    while page <= min(pages, max_pages):
        url = API_URL + "?" + urlencode({"method": "user.getrecenttracks", "user": user, "api_key": api_key,
                                         "format": "json", "limit": 200, "page": page})
        try:
            with net.urlopen(Request(url, headers={"User-Agent": f"Hallucinate/{__version__}"}), timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise RuntimeError(f"Couldn't reach Last.fm: {_words(exc)}") from exc
        if "error" in data:
            raise RuntimeError(f"Last.fm error {data['error']}: {data.get('message', '')}")
        got, pages = parse_lastfm_page(data)
        items += got
        if progress:
            progress(len(items))
        page += 1
    return items


class ListenBrainzScrobbler(QObject):
    statusChanged = Signal()
    _keyring_late = Signal(object)
    connectionChanged = Signal()
    pendingCountChanged = Signal()
    busyChanged = Signal()
    importChanged = Signal()
    importFinished = Signal(int)  # new listens added
    deliveryChanged = Signal()  # rejectedCount, rejected or lastError changed
    listenPointChanged = Signal()
    _jobFinished = Signal(str, object, str)
    _importDone = Signal(object, str)
    _stored = Signal(str, object)  # a keyring write finished: (what went wrong or "", what to do next)

    def __init__(self, player, data_dir, userlib=None, parent=None):
        super().__init__(parent)
        self.player = player
        self.userlib = userlib
        self._queue_path = Path(data_dir) / "listenbrainz-listens.json"
        # a server of your own that speaks the ListenBrainz API (Maloja, Koito, Multi-Scrobbler…): remembered,
        # so listens and the token keep going there after a restart, never to listenbrainz.org
        from PySide6.QtCore import QSettings as _QSettings

        self._server = str(_QSettings("hallucinate", "hallucinate").value("listenbrainz/server", "") or "")
        self._base = self._server or DEFAULT_URL
        self._token = ""
        self._user = ""
        self._status = ""
        self._busy = False
        self._pending = []
        self._retry_at = 0.0
        self._retry_delay = 5.0
        self._now_key = ""
        self._started = int(time.time())
        # the listen being counted (the same rule as Last.fm's: see scrobbling.listen_threshold)
        self._listen_key = None
        self._listened_ms = 0
        self._counted = False
        self._last_tick = time.monotonic()
        self._last_position = 0
        self._import_status = ""
        self._importing = False
        self._closing = False
        self._keyring_error = ""
        self._rejected = []  # [{artist, track, reason}] ListenBrainz refused for good, newest last
        self._rejected_count = 0
        self._last_error = ""
        self._single = False  # a batch was refused: send one at a time to find the listen at fault
        self._qsettings = QSettings("hallucinate", "hallucinate")
        self._listen_point = listen_point(self._qsettings.value("listenbrainz/listenPoint", "rule"))
        self._now_playing = self._qsettings.value("listenbrainz/nowPlaying", True, bool)  # "Playing now"
        self._load_keyring()
        self._load_queue()
        self._jobFinished.connect(self._on_job_finished)
        self._importDone.connect(self._on_import_done)
        self._stored.connect(self._on_stored)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        player.trackChanged.connect(self._on_track_changed)
        player.stateChanged.connect(self._on_state_changed)
        player.seeked.connect(self._on_seeked)

    # --- state ---------------------------------------------------------------
    @Property(str, notify=listenPointChanged)
    def listenPoint(self):
        """When a song counts as a listen: one of scrobbling.LISTEN_POINTS."""
        return self._listen_point

    @Property(bool, notify=listenPointChanged)
    def nowPlaying(self):
        """Tell ListenBrainz what's playing as it starts ("Playing now"). Off: only listens."""
        return self._now_playing

    @Slot(bool)
    def setNowPlaying(self, on):
        self._now_playing = bool(on)
        self._qsettings.setValue("listenbrainz/nowPlaying", self._now_playing)
        self.listenPointChanged.emit()

    @Slot(str)
    def setListenPoint(self, point):
        self._listen_point = listen_point(point)
        self._qsettings.setValue("listenbrainz/listenPoint", self._listen_point)
        self.listenPointChanged.emit()

    def _load_keyring(self):

        self._keyring_late.connect(self._apply_keyring)
        got = keyringwait.read(lambda k: keyring.get_password(KEYRING_SERVICE, k), ("token", "user"),
                               late=self._keyring_late.emit)
        if got is None:
            self._set_status("Waiting for the system keyring to unlock…")
            return
        self._apply_keyring(got)

    @Slot(object)
    def _apply_keyring(self, got):
        if got["error"]:
            self._keyring_error = got["error"]
        self._token = got["values"].get("token", "") or self._token
        self._user = got["values"].get("user", "") or self._user
        self.connectionChanged.emit()
        self._set_status(f"System keyring unavailable: {self._keyring_error}" if self._keyring_error
                         else (f"Connected to {server_label(self._server)}" + (f" as {self._user}." if self._user else "."))
                         if self._token else "Not connected to ListenBrainz.")

    def _load_queue(self):
        try:
            data = json.loads(self._queue_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("listen queue must be a list")
            self._pending = [
                item for item in data
                if isinstance(item, dict)
                and isinstance(item.get("listened_at"), int)
                and isinstance(item.get("track_metadata"), dict)
            ]
            if len(self._pending) != len(data):
                self._set_status("Ignored invalid records in the ListenBrainz offline queue.")
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Could not load ListenBrainz queue: %s", exc)

    def _save_queue(self):
        try:
            self._queue_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._queue_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._pending, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._queue_path)
        except OSError as exc:
            logger.warning("Could not persist ListenBrainz queue: %s", exc)
            self._set_status(f"Could not persist offline listens: {exc}")

    def _set_status(self, text):
        if text != self._status:
            self._status = text
            self.statusChanged.emit()

    @Property(bool, notify=connectionChanged)
    def connected(self):
        return bool(self._token)

    @Property(str, notify=connectionChanged)
    def username(self):
        return self._user

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(int, notify=pendingCountChanged)
    def pendingCount(self):
        return len(self._pending)

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @Property(int, notify=deliveryChanged)
    def rejectedCount(self):
        """Listens ListenBrainz refused for good (since the app started): they were dropped from the queue."""
        return self._rejected_count

    @Property("QVariantList", notify=deliveryChanged)
    def rejected(self):
        """The latest of those, newest last: [{artist, track, reason}]."""
        return list(self._rejected)

    @Property(str, notify=deliveryChanged)
    def lastError(self):
        """What went wrong with the last request ("" once one works again)."""
        return self._last_error

    def _set_last_error(self, text):
        if text != self._last_error:
            self._last_error = text
            self.deliveryChanged.emit()

    def _reject(self, item, reason):
        meta = item.get("track_metadata") or {}
        self._rejected.append({"artist": meta.get("artist_name", ""), "track": meta.get("track_name", ""),
                               "reason": reason})
        del self._rejected[:-REJECTED_KEPT]
        self._rejected_count += 1
        logger.info("ListenBrainz refused a listen (%s): dropped", reason)
        self.deliveryChanged.emit()

    @Slot()
    def retryNow(self):
        """Send what's waiting now instead of after the back-off."""
        self._retry_at, self._retry_delay = 0.0, 5.0
        self._send_now_playing()
        self._flush()

    def _store(self, fn, then=None):
        """Keyring writes on a thread of their own (a locked keyring mustn't freeze the window); then(error)
        follows on this thread once it's done."""
        def run():
            self._stored.emit(keyringwait.call(fn), then)

        threading.Thread(target=run, name="listenbrainz-keyring", daemon=True).start()

    @Slot(str, object)
    def _on_stored(self, error, then):
        if then is not None:
            then(error)
        elif error:
            logger.warning("ListenBrainz system keyring couldn't be updated: %s", error)

    @Property(str, notify=importChanged)
    def importStatus(self):
        return self._import_status

    @Property(bool, notify=importChanged)
    def importing(self):
        return self._importing

    # --- account ---------------------------------------------------------------
    @Property(str, notify=connectionChanged)
    def server(self):
        """The server listens go to: "" for listenbrainz.org, else its API address."""
        return self._server

    @Property(str, notify=connectionChanged)
    def serverName(self):
        return server_label(self._server)

    @Slot(str, str)
    def connectToken(self, token, server=""):
        token = token.strip()
        if not token or self._busy:
            return
        if self._keyring_error:
            self._set_status(f"System keyring is required: {self._keyring_error}")
            return
        try:
            wanted = normalize_server(server)
        except ValueError as exc:
            self._set_status(str(exc))
            return
        self._pending_server = wanted
        self._base = wanted or DEFAULT_URL
        self._set_status(f"Validating the token with {server_label(wanted)}…")
        base = self._base
        self._start("validate", lambda: lb_request(base, "/1/validate-token", token), item=token)

    @Slot()
    def disconnectAccount(self):
        if self._busy:
            self._set_status("Wait for the current ListenBrainz request to finish before disconnecting.")
            return
        self._forget_token()
        self._set_status("Disconnected from ListenBrainz. Pending listens are kept.")

    def _forget_token(self):
        """Sign out here at once, and take the token out of the keyring in the background."""
        self._token = self._user = ""
        self._now_key = ""
        self.connectionChanged.emit()

        def forget():
            for k in ("token", "user"):
                if keyring.get_password(KEYRING_SERVICE, k):
                    keyring.delete_password(KEYRING_SERVICE, k)

        def then(error):
            if error:
                self._set_status(f"{self._status} (the token couldn't be removed from the keyring: {error})")

        self._store(forget, then)

    def _start(self, action, work, item=None):
        if self._busy or self._closing:
            return False
        self._busy = True
        self.busyChanged.emit()

        def run():
            try:
                self._jobFinished.emit(action, (work(), item, 0), "")
            except Exception as exc:  # noqa: BLE001
                self._jobFinished.emit(action, (None, item, getattr(exc, "code", 0)), str(exc) or type(exc).__name__)

        threading.Thread(target=run, name=f"listenbrainz-{action}", daemon=True).start()
        return True

    def _on_job_finished(self, action, payload, error):
        self._busy = False
        self.busyChanged.emit()
        result, item, code = payload
        if error:
            if action == "validate":
                self._base = self._server or DEFAULT_URL  # not connected there: back to the server in use
                self._set_status(error.replace("ListenBrainz", server_label(getattr(self, "_pending_server", ""))))
                return
            self._set_status(error)
            self._set_last_error(error)
            if code in (401, 403):
                # the token was revoked or changed: asking again won't help
                self._forget_token()
                self._set_status("ListenBrainz no longer accepts this token: connect ListenBrainz again. "
                                 "Pending listens are kept.")
                return
            if code == 400 and action == "submit":
                if len(item) > 1:
                    self._single = True  # one of them is at fault: find it by sending them one at a time
                elif self._pending and self._pending[0] == item[0]:
                    self._pending.pop(0)
                    self._save_queue()
                    self.pendingCountChanged.emit()
                    self._reject(item[0], error)
                    self._single = False
                self._flush()
                return
            if action == "now":
                if code == 400:
                    return  # this one won't ever be accepted; the next track's may
                self._now_key = ""
            self._retry_delay = min(self._retry_delay * 2, MAX_RETRY_SECONDS)
            self._retry_at = time.monotonic() + self._retry_delay
            return
        self._retry_delay, self._retry_at = 5.0, 0.0
        if action != "validate":
            self._set_last_error("")
        if action == "validate":
            if not result.get("valid"):
                self._base = self._server or DEFAULT_URL
                self._set_status(f"{server_label(getattr(self, '_pending_server', ''))} says that token is not valid.")
                return
            user = result.get("user_name", "")

            def then(error):
                if error:
                    self._set_status(f"Could not store the token securely: {error}")
                    return
                self._token, self._user = item, user
                self._server = getattr(self, "_pending_server", "")
                self._base = self._server or DEFAULT_URL
                self._qsettings.setValue("listenbrainz/server", self._server)
                self.connectionChanged.emit()
                self._set_status(f"Connected to {server_label(self._server)} as {self._user}.")
                self._send_now_playing()
                self._flush()

            self._set_status("Saving the token…")
            self._store(lambda: (keyring.set_password(KEYRING_SERVICE, "token", item),
                                 keyring.set_password(KEYRING_SERVICE, "user", user)), then)
        elif action == "submit":
            if self._pending[:len(item)] == item:
                del self._pending[:len(item)]
                self._save_queue()
                self.pendingCountChanged.emit()
            if not self._pending:
                self._single = False
            self._set_status("Listen submitted to ListenBrainz." if len(item) == 1
                             else f"{len(item)} listens submitted to ListenBrainz.")
            self._flush()
        elif action == "now":
            self._set_status("ListenBrainz now-playing updated.")
            self._flush()

    # --- scrobbling ------------------------------------------------------------
    def _on_track_changed(self):
        track = dict(self.player.current or {})
        key = self._key(track)
        if key != self._listen_key:
            self._listen_key = key
            self._new_listen()
        else:
            self._maybe_replay(self.player.position)  # the same song loaded again (repeat one)
        self._send_now_playing()

    @staticmethod
    def _key(track):
        return "\x1f".join(str(track.get(k, "")) for k in ("path", "title", "artist", "album"))

    def _new_listen(self):
        """Start counting a listen afresh: a new song, or the same one heard again."""
        self._started = int(time.time())
        self._now_key = ""
        self._listened_ms = 0
        self._counted = False
        self._last_tick = time.monotonic()
        self._last_position = self.player.position

    def _maybe_replay(self, position):
        """Back at the start of a song that already counted (repeat one, or played again from the top)."""
        if self._counted and position < REPLAY_START_MS:
            self._new_listen()

    def _on_state_changed(self):
        self._last_tick = time.monotonic()
        self._last_position = self.player.position
        self._send_now_playing()

    def _on_seeked(self, position):
        self._maybe_replay(position)
        self._last_tick = time.monotonic()
        self._last_position = position

    def _count(self):
        """Add the listening time since the last tick, and queue the listen once enough of it is heard."""
        now, position = time.monotonic(), self.player.position
        track = dict(self.player.current or {})
        if self._key(track) != self._listen_key:
            self._on_track_changed()
        elif self.player.playing and track:
            if position < REPLAY_START_MS <= self._last_position:
                self._maybe_replay(position)  # it went back to the start by itself (a gapless repeat)
            self._listened_ms += heard_ms(now - self._last_tick, position - self._last_position)
            duration = int(self.player.duration or float(track.get("duration", 0) or 0) * 1000)
            threshold = listen_threshold(track, duration, self._listen_point)
            if not self._counted and threshold and self._listened_ms >= threshold:
                self._counted = True
                self._queue_listen(track, self._started)
        self._last_tick, self._last_position = now, position

    def _send_now_playing(self):
        track = dict(self.player.current or {})
        if not self._now_playing or not counts_for_scrobbling(track):
            return
        key = f"{track.get('path')}\x1f{track.get('stream_title', '')}"
        if (not (self.connected and self.player.playing and track and key != self._now_key)
                or self._busy or net.is_offline() or time.monotonic() < self._retry_at):
            return
        try:
            meta = track_metadata(track)
        except ValueError:
            return
        self._now_key = key
        payload = {"listen_type": "playing_now", "payload": [{"track_metadata": meta}]}
        base, token = self._base, self._token
        self._start("now", lambda: lb_request(base, "/1/submit-listens", token, payload))

    def _tick(self):
        self._count()
        self._send_now_playing()
        self._flush()

    def _queue_listen(self, track, listened_at):
        if not counts_for_scrobbling(dict(track)):
            return
        try:
            meta = track_metadata(dict(track))
        except ValueError:
            return
        self._pending.append({"listened_at": int(listened_at), "track_metadata": meta})
        self._save_queue()
        self.pendingCountChanged.emit()
        self._flush()

    def _flush(self):
        if (not self.connected or self._busy or not self._pending or net.is_offline()
                or time.monotonic() < self._retry_at):
            return
        batch = [dict(item) for item in self._pending[:1 if self._single else MAX_BATCH]]
        payload = {"listen_type": "single" if len(batch) == 1 else "import", "payload": batch}
        base, token = self._base, self._token

        def submit():
            result = lb_request(base, "/1/submit-listens", token, payload)
            if result.get("status") != "ok":
                raise RuntimeError(f"ListenBrainz did not accept the queued listen: {result.get('status', 'invalid response')}")
            return result

        self._start("submit", submit, item=batch)

    # --- history import ----------------------------------------------------------
    @Slot(str, str)
    def importHistory(self, source, user):
        """Import listens from 'listenbrainz' or 'lastfm' into the local play history."""
        if source not in ("listenbrainz", "lastfm"):
            self._import_status = "Choose ListenBrainz or Last.fm as the import source."
            self.importChanged.emit()
            return
        user = user.strip() or (self._user if source == "listenbrainz" else "")
        if self._closing or self._importing or not user:
            self._import_status = "Enter a username to import from."
            self.importChanged.emit()
            return
        self._importing = True
        self._import_status = "Fetching listens…"
        self.importChanged.emit()
        base, token = self._base, self._token
        ulib = self.userlib

        def progress(n):
            if not self._closing:
                self._importDone.emit({"progress": n}, "")

        def run():
            try:
                if source == "lastfm":
                    from .scrobbling import LastFmScrobbler  # noqa: F401
                    key = _lastfm_key()
                    if not key:
                        raise RuntimeError("Set a Last.fm API key first (Settings → Last.fm).")
                    items = fetch_lastfm_history(user, key, progress)
                else:
                    items = fetch_listenbrainz_history(base, user, token, progress)
                if self._closing:
                    return
                if ulib is None:
                    raise RuntimeError("Library unavailable")
                ulib.importPlays(items, source, lambda res, err="": self._importDone.emit(res, err))
            except Exception as exc:  # noqa: BLE001
                if not self._closing:
                    self._importDone.emit(None, str(exc))

        threading.Thread(target=run, name="history-import", daemon=True).start()

    def _on_import_done(self, result, error):
        if error:
            self._importing = False
            self._import_status = error
        elif "progress" in result:
            self._import_status = f"Fetched {result['progress']} listens…"
        else:
            self._importing = False
            self._import_status = f"Imported {result['added']} new listens ({result['matched']} matched your library)."
            self.importFinished.emit(result["added"])
        self.importChanged.emit()

    @Slot()
    def shutdown(self):
        self._closing = True
        self._timer.stop()


def _lastfm_key():
    import os
    key = os.environ.get("HALLUCINATE_LASTFM_API_KEY", "").strip()
    if key:
        return key
    try:
        from .scrobbling import KEYRING_SERVICE as svc
        return keyring.get_password(svc, "api_key") or ""
    except Exception:  # noqa: BLE001
        return ""
