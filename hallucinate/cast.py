"""Casting: playing the queue on a Chromecast or a DLNA/UPnP device on your network.

`Casting` (the `casting` object in QML) finds devices, connects to one and hands the player a session. While a
session is attached the player keeps the queue, shuffle, repeat, play counts and scrobbling, and sends play,
pause, seek, volume and "play this song" to the device instead of its own speakers; the device's reports (where
it is, playing or paused, the song ended) come back through the session. Stopping hands playback back to this
computer at the place the device had reached.

The protocols and the media server are in core/cast; this side runs their blocking calls on one worker thread
per session (so commands reach a device in the order they were given) and brings results to the window's
thread through queued signals."""
import hashlib
import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Property, QObject, QSettings, Qt, QTimer, Signal, Slot

from .core import net, remote
from .core.cast import castv2, mdns, mediaserver, upnp
from .core.i18n import QT_TRANSLATE_NOOP, fill, translate
from .core.kinds import is_url, track_kind

logger = logging.getLogger(__name__)

POLL_MS = 1000  # how often a device is asked where it is (a Chromecast also says so on its own)
START_TIMEOUT_S = 20  # a song that hasn't started this long after it was sent: something's wrong
DISCOVERY_S = 3.0
RELAY_LIMIT = 4 * 1024 ** 3  # a relayed song (a server's, an episode) may be large, but not endless
SENDING = ("original", "processed")

# What each kind of device plays as it is. Anything else needs Hallucinate's own sound (see the "processed"
# setting): it's decoded and sent in a form the device takes.
CHROMECAST_TYPES = {"audio/mpeg", "audio/flac", "audio/mp4", "audio/aac", "audio/ogg", "audio/wav", "audio/webm"}
CHROMECAST_MAX_RATE = 96000
UPNP_ASSUMED = {"audio/mpeg", "audio/flac", "audio/wav"}  # when a device won't say what it plays
UNPLAYABLE_CODECS = {"alac", "ape", "wavpack", "dsd", "dsf", "dff", "wma", "mpc", "tta", "tak"}
RENDER_MAX_RATE = 48000  # what every Chromecast and TV takes as WAV
KEEP_RENDERS = 4  # prepared songs kept while casting (the playing one, the next, a couple just played)

FIREWALL_HINT = QT_TRANSLATE_NOOP(
    "Casting", "%1 couldn't fetch the song from this computer. A firewall may be blocking port %2: allow it for "
               "your local network, or pick another port in Settings → Casting.")


def _seconds(ms):
    return max(0.0, (ms or 0) / 1000)


class CastSession(QObject):
    """One device being played on. Subclasses speak its protocol; this keeps the state the player reads.

    Signals arrive on the window's thread. `ended` is a song that finished by itself; `failed(message, skippable)`
    a song the device couldn't play (skippable: worth trying the next one; not when every song would fail the
    same way); `lost(message)` the device going away (the session is over)."""

    changed = Signal()
    ended = Signal()
    failed = Signal(str, bool)
    lost = Signal(str)
    _report = Signal(object)  # from worker threads: a callable to run here

    def __init__(self, device, server, parent=None):
        super().__init__(parent)
        self.device = device
        self.name = device["name"]
        self._server = server
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cast")
        self._report.connect(self._run_here, Qt.ConnectionType.QueuedConnection)
        self.state = "IDLE"  # PLAYING, PAUSED, BUFFERING, IDLE, LOADING
        self._pos, self._at = 0.0, time.monotonic()
        self.duration = 0.0
        self.volume = None
        self.muted = False
        self._gen = 0  # which load the device's reports belong to
        self._loaded_at = 0.0
        self._link = ""
        self._window = (0.0, 0.0)  # a CUE song's place in its file (start, end; 0 = to the end)
        self.closed = False
        self._poll = QTimer(self, interval=POLL_MS, timeout=self._tick)

    # --- running things -------------------------------------------------------------------------------------
    def _run_here(self, fn):
        if not self.closed:
            fn()

    def _later(self, fn):
        self._report.emit(fn)

    def _submit(self, fn, error=None):
        """Runs fn() on the worker; an exception becomes failed(error or its text)."""
        if self.closed:
            return

        def job():
            try:
                fn()
            except Exception as e:  # noqa: BLE001 - a device can fail in any way; the window just hears of it
                logger.info("Cast command to %s failed: %s", self.name, e)
                message = error if error is not None else fill(
                    translate("Casting", "%1 didn't answer: %2"), self.name, str(e))
                if message:
                    self._later(lambda: self.failed.emit(message, False))
        try:
            self._pool.submit(job)
        except RuntimeError:  # shut down
            pass

    # --- what the player reads ------------------------------------------------------------------------------
    @property
    def playing(self):
        return self.state in ("PLAYING", "BUFFERING", "LOADING")

    def position_ms(self):
        pos = self._pos
        if self.state == "PLAYING":
            pos += time.monotonic() - self._at
        if self.duration:
            pos = min(pos, self.duration)
        return int(max(0.0, pos - self._window[0]) * 1000)

    def duration_ms(self):
        start, end = self._window
        if end:
            return int((end - start) * 1000)
        return int(max(0.0, self.duration - start) * 1000) if self.duration else 0

    def _set(self, state=None, position=None, duration=None):
        if state is not None:
            self.state = state
        if position is not None:
            self._pos, self._at = position, time.monotonic()
        if duration:
            self.duration = duration
        self.changed.emit()

    # --- commands (the player calls these) ------------------------------------------------------------------
    def load(self, media, start_ms=0, autoplay=True):
        """Plays `media` (see Casting.media_for) from `start_ms` into the song."""
        self._gen += 1
        self._window = (media.get("start", 0.0), media.get("end", 0.0))
        self._link = media["link"]
        self._loaded_at = time.monotonic()
        self.duration = media.get("file_duration") or 0.0
        self._set("LOADING" if autoplay else "PAUSED", self._window[0] + _seconds(start_ms))
        self._do_load(media, self._window[0] + _seconds(start_ms), autoplay, self._gen)
        self._poll.start()

    def preparing(self, start_ms=0, autoplay=True):
        """The next song is being got ready (see Casting.media_for): show it as starting, send nothing yet."""
        self._gen += 1
        self._window = (0.0, 0.0)
        self._poll.stop()
        self._set("LOADING" if autoplay else "PAUSED", _seconds(start_ms))

    def play(self):
        if self.state in ("PAUSED", "IDLE"):
            self._set("PLAYING", self._pos)
        self._submit(self._do_play)

    def pause(self):
        self._set("PAUSED", self._pos + (time.monotonic() - self._at if self.state == "PLAYING" else 0))
        self._submit(self._do_pause)

    def seek(self, ms):
        target = self._window[0] + _seconds(ms)
        self._set(position=target)
        self._submit(lambda: self._do_seek(target))

    def set_volume(self, level):
        self.volume = min(1.0, max(0.0, float(level)))
        self.changed.emit()
        self._submit(lambda: self._do_volume(self.volume))

    def stop(self):
        self._set("IDLE", self._window[0])
        self._submit(self._do_stop)

    def close(self, stop_device=True):
        """Ends the session (the device stops playing unless not `stop_device`)."""
        if self.closed:
            return
        self.closed = True
        self._poll.stop()

        def finish():
            try:
                self._do_close(stop_device)
            except Exception as e:  # noqa: BLE001
                logger.info("Closing the cast session with %s: %s", self.name, e)
        try:
            self._pool.submit(finish)
        except RuntimeError:
            pass
        self._pool.shutdown(wait=False)

    def _tick(self):
        if self.closed:
            return
        start, end = self._window
        if end and self.state == "PLAYING" and self._pos + time.monotonic() - self._at >= end:
            self._gen += 1  # a CUE song ends mid-file: move on (the next one is sent at its own place)
            self._set("IDLE")
            self.ended.emit()
            return
        if (self.state == "LOADING" and time.monotonic() - self._loaded_at > START_TIMEOUT_S):
            self._set("IDLE")
            self.failed.emit(*self._not_started())
            return
        self._do_poll(self._gen)
        self.changed.emit()

    def _not_started(self):
        """Why a song didn't play: if the device never even asked for it, it couldn't reach us (a firewall)."""
        link = self._server.find(self._link.rsplit("/", 1)[-1].split(".", 1)[0]) if self._link else None
        if link is not None and not link.fetched:
            return fill(translate("Casting", FIREWALL_HINT), self.name, self._server.port), False
        return fill(translate("Casting", "%1 couldn't play this song."), self.name), True

    # --- reports from the device (on its threads; brought here) ---------------------------------------------
    def _status(self, gen, state, position=None, duration=None, finished=False, error=False, lost_media=False):
        def apply():
            if gen != self._gen:
                return  # about a song that's already been replaced
            if error:
                self._set("IDLE")
                self.failed.emit(*self._not_started())
                return
            if finished:
                self._gen += 1
                self._set("IDLE")
                self.ended.emit()
                return
            if lost_media:
                self._set("PAUSED")  # someone else took the device over, or stopped it there: hold here
                return
            if self.state == "LOADING" and state not in ("PLAYING",):
                self._set(position=position, duration=duration)
                return
            self._set(state, position, duration)
        self._later(apply)

    def _gone(self, reason):
        def apply():
            if self.closed:
                return
            self.close(stop_device=False)
            self.lost.emit(fill(translate("Casting", "Lost the connection to %1"), self.name)
                           + (f" ({reason})" if reason else ""))
        self._later(apply)

    # --- what each protocol does (on the worker thread) -----------------------------------------------------
    def connect_device(self):
        raise NotImplementedError

    def _do_load(self, media, position, autoplay, gen):
        raise NotImplementedError

    def _do_play(self):
        raise NotImplementedError

    def _do_pause(self):
        raise NotImplementedError

    def _do_seek(self, seconds):
        raise NotImplementedError

    def _do_volume(self, level):
        raise NotImplementedError

    def _do_stop(self):
        raise NotImplementedError

    def _do_poll(self, gen):
        pass

    def _do_close(self, stop_device):
        pass

    def plays(self, ctype, track):
        """Whether the device plays this file type (and this track's codec and rate) as it is."""
        raise NotImplementedError

    def share(self, **what):
        """A link to something for this device only (see mediaserver.Links.share)."""
        return self._server.share(self.device["host"], **what)

    def url(self, link):
        """The address the device fetches `link` from."""
        return self._server.url(self.device["host"], link)


class ChromecastSession(CastSession):
    kind = "chromecast"

    def __init__(self, device, server, parent=None, connect=castv2.tls_connect):
        super().__init__(device, server, parent)
        self._client = castv2.CastClient(device["host"], device.get("port") or castv2.PORT,
                                         on_media=self._on_media, on_receiver=self._on_receiver,
                                         on_closed=self._gone, connect=connect)
        self._media_gen = 0
        self._seen_session = None

    def connect_device(self):
        """Connects and opens the device's player (blocking: call from a worker)."""
        self._client.start()
        self._client.launch()

    def _on_receiver(self, status):
        def apply():
            if status["volume"] is not None:
                self.volume = status["volume"]
            self.muted = status["muted"]
            self.changed.emit()
        self._later(apply)

    def _on_media(self, st):
        gen = self._media_gen
        if st["session"] is not None:
            self._seen_session = st["session"]
        state = st["state"]
        if state == "IDLE":
            reason = st["idle_reason"]
            self._status(gen, "IDLE", finished=reason == "FINISHED", error=reason == "ERROR",
                         lost_media=reason in ("CANCELLED", "INTERRUPTED"))
        elif state:
            self._status(gen, state, st["position"], st["duration"])

    def _do_load(self, media, position, autoplay, gen):
        def job():
            self._media_gen = gen
            self._client.load(media["url"], media["ctype"], title=media.get("title", ""),
                              artist=media.get("artist", ""), album=media.get("album", ""),
                              image=media.get("image", ""), duration=media.get("file_duration"),
                              position=position, live=media.get("live", False), autoplay=autoplay)
        self._submit(job)

    def _do_play(self):
        self._client.play()

    def _do_pause(self):
        self._client.pause()

    def _do_seek(self, seconds):
        self._client.seek(seconds)

    def _do_volume(self, level):
        self._client.set_volume(level)

    def _do_stop(self):
        self._client.stop_media()

    def _do_poll(self, gen):
        self._submit(self._client.poll)

    def _do_close(self, stop_device):
        self._client.close(stop_app=stop_device)

    def close(self, stop_device=True):
        super().close(stop_device)
        # the client holds this session's methods as callbacks: let go of them, or the two keep each other alive
        client = self._client
        client.on_media = client.on_receiver = client.on_closed = None

    def plays(self, ctype, track):
        codec = (track.get("codec") or "").lower()
        if ctype not in CHROMECAST_TYPES or codec in UNPLAYABLE_CODECS:
            return False
        rate = track.get("sample_rate") or 0
        return not (isinstance(rate, (int, float)) and rate > CHROMECAST_MAX_RATE)


class UpnpSession(CastSession):
    kind = "upnp"

    def __init__(self, device, server, parent=None, request=upnp.http_request):
        super().__init__(device, server, parent)
        self._renderer = upnp.Renderer(device, request=request)
        self._formats = set()
        self._was_playing = False
        self._last_pos = 0.0
        self._last_seen = time.monotonic()
        self._we_stopped = False

    def connect_device(self):
        self._formats = self._renderer.formats()
        self.volume = self._renderer.volume()

    def _do_load(self, media, position, autoplay, gen):
        def job():
            self._was_playing = False
            self._last_pos = 0.0
            self._last_seen = time.monotonic()
            self._we_stopped = True  # (load stops what was playing first)
            self._renderer.load(media["url"], media["ctype"], title=media.get("title", ""),
                                artist=media.get("artist", ""), album=media.get("album", ""),
                                image=media.get("image", ""), duration=media.get("file_duration"))
            self._we_stopped = False
            if autoplay:
                self._renderer.play()
            if position > 1:
                try:
                    self._renderer.seek(position)
                except upnp.UpnpError:
                    pass  # some devices only seek once playing; the next poll shows where it is
        self._submit(job)

    def _do_play(self):
        self._renderer.play()

    def _do_pause(self):
        self._renderer.pause()

    def _do_seek(self, seconds):
        self._renderer.seek(seconds)

    def _do_volume(self, level):
        self._renderer.set_volume(level)

    def _do_stop(self):
        self._we_stopped = True
        self._renderer.stop()

    def _do_poll(self, gen):
        def job():
            st = self._renderer.status()
            state, pos, dur = st["state"], st["position"], st["duration"]
            if state == "PLAYING":
                self._was_playing = True
                if pos is not None:
                    self._last_pos, self._last_seen = pos, time.monotonic()
                self._status(gen, "PLAYING", pos, dur)
            elif state == "PAUSED":
                self._status(gen, "PAUSED", pos, dur)
            elif state in ("STOPPED", "NO_MEDIA") and self._was_playing and not self._we_stopped:
                # stopped without being asked: at the end it's the song finishing; before it, someone stopped it
                # (it played on since the last answer, up to a poll's worth)
                reached = self._last_pos + min(time.monotonic() - self._last_seen, POLL_MS / 1000 * 2)
                near_end = not self.duration or reached >= max(self.duration - 3, self.duration * 0.9)
                self._was_playing = False
                self._status(gen, "IDLE", finished=near_end, lost_media=not near_end)
            elif state == "TRANSITIONING":
                self._status(gen, "BUFFERING", pos, dur)
        self._submit(job, error="")  # a missed poll isn't worth a message; the next one tries again

    def _do_close(self, stop_device):
        if stop_device:
            self._we_stopped = True
            self._renderer.stop()

    def plays(self, ctype, track):
        codec = (track.get("codec") or "").lower()
        if codec in UNPLAYABLE_CODECS:
            return False
        return ctype in (self._formats or UPNP_ASSUMED)


PHONE_FORMATS = {"audio/mpeg", "audio/flac", "audio/mp4", "audio/aac", "audio/ogg", "audio/wav", "audio/webm"}


class PhoneSession(CastSession):
    """The phone remote playing the music itself, through the phone's speaker or headphones.

    Nothing to connect to: the phone's page already has its live updates open. What it should do goes out in the
    remote's state ("phone": see `command`), and the page reports back what it's doing (Casting.phone_report).
    Songs come from the web remote's own server, under links only that paired device can use."""

    kind = "phone"

    def __init__(self, device_id, name, session_id, formats, links, notify, parent=None):
        super().__init__({"id": "phone:" + device_id, "name": name, "model": "", "kind": "phone", "host": "",
                          "device_id": device_id}, None, parent)
        self.device_id, self.session_id = device_id, session_id
        self._links, self._notify = links, notify
        self._formats = {f for f in formats if f in PHONE_FORMATS} or {"audio/mpeg"}
        self._seeks = 0
        self.command = {"session": session_id, "gen": 0, "src": "", "start": 0.0, "playing": False,
                        "seek": {"n": 0, "to": 0.0}, "volume": None, "title": "", "artist": "", "album": "",
                        "image": "", "live": False}
        self.volume = 1.0

    def connect_device(self):
        pass

    def share(self, **what):
        return self._links.share(self.device_id, **what)

    def url(self, link):
        return link  # (on the remote's own server: the page asks for it as it is)

    def plays(self, ctype, track):
        codec = (track.get("codec") or "").lower()
        return ctype in self._formats and codec not in UNPLAYABLE_CODECS

    def _send(self, **changes):
        self.command = dict(self.command, **changes)
        self._later(self._notify)

    def _do_load(self, media, position, autoplay, gen):
        self._send(gen=gen, src=media["url"], start=float(position), playing=bool(autoplay),
                   title=media.get("title", ""), artist=media.get("artist", ""), album=media.get("album", ""),
                   image=media.get("image", ""), live=bool(media.get("live")))

    def _do_play(self):
        self._send(playing=True)

    def _do_pause(self):
        self._send(playing=False)

    def _do_seek(self, seconds):
        self._seeks += 1
        self._send(seek={"n": self._seeks, "to": float(seconds)})

    def _do_volume(self, level):
        self._send(volume=float(level))

    def _do_stop(self):
        self._send(playing=False, src="")

    def _do_close(self, stop_device):
        self._send(src="", playing=False, stopped=True)

    def close(self, stop_device=True):
        super().close(stop_device)
        self._notify = lambda: None  # (it reaches back into Casting: let go, so neither keeps the other alive)

    def report(self, gen, state, position, duration):
        """What the phone says it's doing (on the window's thread)."""
        if state == "ended":
            self._status(gen, "IDLE", finished=True)
        elif state == "error":
            self._status(gen, "IDLE", error=True)
        elif state in ("playing", "paused", "buffering"):
            self._status(gen, state.upper(), position, duration)

    def _not_started(self):
        return fill(translate("Casting", "%1 couldn't play this song."), self.name), True


class Casting(QObject):
    """Finding devices, connecting and handing the player a session. Settings live under "cast/"."""

    changed = Signal()
    devicesChanged = Signal()
    notice = Signal(str)
    _found = Signal(object)
    _connected = Signal(object, object)  # (session, error)

    def __init__(self, player=None, parent=None, cover_for=None):
        super().__init__(parent)
        self._settings = QSettings()
        self._player = player
        self._cover_for = cover_for
        self._devices = []
        self._searching = False
        self._connecting = ""
        self._session = None
        self._error = ""
        port = self._settings.value("cast/port", mediaserver.DEFAULT_PORT)
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = mediaserver.DEFAULT_PORT
        self._server = mediaserver.MediaServer(port if 1024 <= port < 65536 else mediaserver.DEFAULT_PORT)
        self._found.connect(self._on_found, Qt.ConnectionType.QueuedConnection)
        self._connected.connect(self._on_connected, Qt.ConnectionType.QueuedConnection)
        self.session_factories = {"chromecast": ChromecastSession, "upnp": UpnpSession}  # (tests swap these)
        self.discover = _discover
        self.phone_links = mediaserver.Links()  # songs for a phone playing them, served by the web remote
        self.notify_remote = lambda: None  # tells the web remote its state changed (set by the app)
        self._analyser = None  # the decoding helper that prepares songs (made when first needed)
        self._render_dir = None
        self._renders = {}  # key -> {"file", "seconds"} (done) or {"waiting": [callbacks]} (in progress)

    # --- settings -------------------------------------------------------------------------------------------
    @Property(str, notify=changed)
    def sending(self):
        value = str(self._settings.value("cast/sending", "original"))
        return value if value in SENDING else "original"

    @Slot(str)
    def setSending(self, value):
        if value in SENDING and value != self.sending:
            self._settings.setValue("cast/sending", value)
            self.changed.emit()

    @Property(int, notify=changed)
    def port(self):
        return int(self._settings.value("cast/port", mediaserver.DEFAULT_PORT) or mediaserver.DEFAULT_PORT)

    @Slot(int)
    def setPort(self, port):
        port = int(port)
        if 1024 <= port < 65536 and port != self.port:
            self._settings.setValue("cast/port", port)
            if not self._server.running:
                self._server.port = port
            self.changed.emit()

    @Property(int, notify=changed)
    def portInUse(self):
        return self._server.port if self._server.running else self.port

    # --- devices --------------------------------------------------------------------------------------------
    @Property("QVariantList", notify=devicesChanged)
    def devices(self):
        return [{"id": d["id"], "name": d["name"], "model": d.get("model", ""), "kind": d.get("kind", ""),
                 "active": bool(self._session and self._session.device["id"] == d["id"])} for d in self._devices]

    @Property(bool, notify=devicesChanged)
    def searching(self):
        return self._searching

    @Slot()
    def refresh(self):
        """Looks for devices (a few seconds, on threads)."""
        if self._searching:
            return
        if net.is_offline():
            self._error = translate("Casting", "Offline mode is on, so devices on your network can't be found")
            self.changed.emit()
            return
        self._searching = True
        self.devicesChanged.emit()

        def run():
            found = []
            try:
                found = self.discover()
            except Exception as e:  # noqa: BLE001
                logger.info("Looking for cast devices failed: %s", e)
            self._found.emit(found)
        threading.Thread(target=run, name="cast-discovery", daemon=True).start()

    def _on_found(self, found):
        self._searching = False
        current = self._session.device if self._session and self._session.kind != "phone" else None
        if current and all(d["id"] != current["id"] for d in found):
            found = [current] + list(found)  # still connected, even if it didn't answer this time
        self._devices = sorted(found, key=lambda d: d["name"].casefold())
        self.devicesChanged.emit()

    # --- the session ----------------------------------------------------------------------------------------
    @Property(bool, notify=changed)
    def active(self):
        return self._session is not None

    @Property(str, notify=changed)
    def deviceName(self):
        return self._session.name if self._session else ""

    @Property(str, notify=changed)
    def deviceKind(self):
        return self._session.kind if self._session else ""

    @Property(str, notify=changed)
    def connecting(self):
        return self._connecting

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Slot()
    def clearError(self):
        if self._error:
            self._error = ""
            self.changed.emit()

    @Slot(str)
    def castTo(self, device_id):
        device = next((d for d in self._devices if d["id"] == device_id), None)
        if device is None or self._connecting:
            return
        if self._session and self._session.device["id"] == device_id:
            return
        # Listen only where the device is: on the network interface that reaches it (a laptop on another network
        # at the same time has nothing open there)
        try:
            bind = mediaserver.address_towards(device["host"])
        except OSError:
            bind = ""
        if self._server.running and self._server.bound != bind:
            self._server.stop()
        if not self._server.running and not self._server.start(bind):
            self._error = fill(translate("Casting", "Couldn't start casting: %1"), self._server.error)
            self.changed.emit()
            return
        if self._session is not None:
            self.stopCasting(resume_here=False)
        self._connecting = device["name"]
        self._error = ""
        self.changed.emit()
        session = self.session_factories[device["kind"]](device, self._server)

        def run():
            try:
                session.connect_device()
                self._connected.emit(session, "")
            except Exception as e:  # noqa: BLE001
                logger.info("Couldn't connect to %s: %s", device["name"], e)
                self._connected.emit(session, str(e) or type(e).__name__)
        threading.Thread(target=run, name="cast-connect", daemon=True).start()

    def _on_connected(self, session, error):
        if self._connecting != session.name:
            session.close(stop_device=False)  # (given up on while it connected)
            return
        self._connecting = ""
        if error:
            session.close(stop_device=False)
            self._error = fill(translate("Casting", "Couldn't connect to %1: %2"), session.name, error)
            self.changed.emit()
            self.notice.emit(self._error)
            return
        self._on_connected_session(session)

    def _on_connected_session(self, session):
        self._session = session
        session.setParent(self)
        session.lost.connect(self._on_lost)
        session.failed.connect(self._on_failed)
        if self._player is not None:
            self._player.attachCast(session, self.media_for, self.prepare)
        self.changed.emit()
        self.devicesChanged.emit()
        self.notice.emit(fill(translate("Casting", "Playing on %1"), session.name))

    @Slot()
    def cancelConnecting(self):
        if self._connecting:
            self._connecting = ""
            self.changed.emit()

    @Slot()
    def stopCasting(self, resume_here=True):
        session, self._session = self._session, None
        if session is None:
            return
        if self._player is not None:
            self._player.detachCast(resume_here)
        session.close(stop_device=True)
        self._server.stop()
        self.phone_links.clear()
        self._clear_renders()
        self.changed.emit()
        self.devicesChanged.emit()

    def _on_lost(self, message):
        if self._session is None:
            return
        self._session = None
        if self._player is not None:
            self._player.detachCast(False)  # the device is gone: hold here, paused, rather than blast the room
        self._server.stop()
        self._clear_renders()
        self._error = message
        self.changed.emit()
        self.devicesChanged.emit()
        self.notice.emit(message)

    def _on_failed(self, message, _skippable=False):
        if message:
            self._error = message
            self.changed.emit()

    # --- the phone remote as the player ---------------------------------------------------------------------
    def phone_start(self, device_id, name, session_id, formats):
        """A paired phone asked to play the music itself (the web remote calls this on the window's thread)."""
        if self._session is not None:
            self.stopCasting(resume_here=False)
        self._connecting = ""
        session = PhoneSession(device_id, name, session_id, formats, self.phone_links,
                               lambda: self.notify_remote())
        self._on_connected_session(session)
        return {"ok": True}

    def phone_report(self, device_id, session_id, gen, state, position, duration):
        session = self._session
        if not isinstance(session, PhoneSession) or session.device_id != device_id or session.session_id != session_id:
            return {"ok": False}  # (a phone that was taken over: it stops on the next state it hears)
        session.report(gen, state, position, duration)
        return {"ok": True}

    def phone_stop(self, device_id):
        if isinstance(self._session, PhoneSession) and self._session.device_id == device_id:
            self.stopCasting()
        return {"ok": True}

    def phone_command(self):
        """What the phone playing the music should be doing, for the remote's state (None when no phone is)."""
        return dict(self._session.command) if isinstance(self._session, PhoneSession) else None

    # --- what's sent ----------------------------------------------------------------------------------------
    def media_for(self, track, session, ready=None):
        """How a queue entry reaches the device: {"link", "url", "ctype", "title", …}; {"error": why} when it
        can't be played there; or {"pending": True} while it's being got ready (a song in Hallucinate's sound,
        a format the device doesn't play, a CUE sheet song), and `ready(media)` is called with the answer."""
        from .player import track_file, track_window

        path = track_file(track)
        title, artist = track.get("title") or "", track.get("artist") or ""
        if track_kind(track) == "station":
            title, artist = track.get("station") or title, ""
        out = {"title": title, "artist": artist, "album": track.get("album") or "",
               "file_duration": float(track.get("duration") or 0) or None}
        start, end = track_window(track)
        if start or end:
            out.update(start=start / 1000, end=end / 1000, file_duration=None)
        if remote.is_remote(path) and remote.local_copy(path):
            path = remote.local_copy(path)
        if remote.is_remote(path) or is_url(path):
            url = remote.stream_url(path) if remote.is_remote(path) else path
            if not url:
                return {"error": translate("Casting", "The music server can't be reached")}
            ctype = mediaserver.content_type(track.get("path") or url.split("?", 1)[0])
            if ctype == "application/octet-stream":
                ctype = "audio/mpeg"
            live = track_kind(track) == "station"

            def relay(rng, url=url):
                import urllib.request
                req = urllib.request.Request(url, headers={"Range": rng} if rng else {})
                return net.urlopen(req, timeout=15, limit=RELAY_LIMIT)
            out.update(link=session.share(relay=relay, ctype=ctype, name="song" + os.path.splitext(
                url.split("?", 1)[0])[1][:6]), ctype=ctype, live=live)
        else:
            ctype = mediaserver.content_type(path)
            processed = self.sending == "processed" and self._player is not None
            if processed or start or end or not session.plays(ctype, track):
                return self._prepare(track, path, session, out, processed, ready)
            out.update(link=session.share(path=path, ctype=ctype), ctype=ctype)
        return self._finish_media(track, session, out)

    def _finish_media(self, track, session, out):
        out["url"] = session.url(out["link"])
        image = self._cover(track)
        if image:
            out["image"] = session.url(session.share(data=image, ctype="image/jpeg",
                                                                      name="cover.jpg"))
        return out

    def _render_options(self, track, processed):
        from .analysis import render_options
        from .player import track_window

        start, end = track_window(track)
        rate = track.get("sample_rate") or 0
        rate = min(int(rate) if isinstance(rate, (int, float)) and rate > 0 else 44100, RENDER_MAX_RATE)
        sound = self._player.cast_sound(track) if processed else {}
        return render_options(start=start / 1000, end=end / 1000, rate=rate, **sound)

    def _prepare(self, track, path, session, out, processed, ready):
        """Renders the song (on the decoding helper) and hands `ready` the media once it's written."""
        options = self._render_options(track, processed)
        key = hashlib.sha256(repr((path, sorted(options.items(), key=str))).encode()).hexdigest()[:32]

        def deliver(done):
            if done is None:
                return {"error": fill(translate("Casting", "Couldn't get this song ready for %1."), session.name),
                        "skippable": True}
            media = dict(out, start=0.0, end=0.0, file_duration=done["seconds"] or None, ctype="audio/wav",
                         sent="processed" if processed else "converted",
                         link=session.share(path=done["file"], ctype="audio/wav"))
            return self._finish_media(track, session, media)

        entry = self._renders.get(key)
        if entry and "file" in entry and os.path.isfile(entry["file"]):
            return deliver(entry)
        waiting = entry["waiting"] if entry and "waiting" in entry else None
        if waiting is not None:
            if ready is not None:
                waiting.append(lambda done: ready(deliver(done)))
            return {"pending": True}
        self._renders[key] = {"waiting": [lambda done: ready(deliver(done))] if ready is not None else []}
        target = self._render_path(key)

        def rendered(result):
            entry = self._renders.pop(key, None)
            done = None
            if result and result.get("frames") and os.path.isfile(target):
                done = {"file": target, "seconds": float(result.get("seconds") or 0)}
                self._renders[key] = done
                self._trim_renders()
            for callback in (entry or {}).get("waiting", []):
                callback(done)
        self._ensure_analyser().submit(path, "render", rendered, first=ready is not None,
                                       extra={"out": target, "options": options})
        return {"pending": True}

    def prepare(self, track, session):
        """Gets the next song ready ahead of time when it will need it (so moving on doesn't wait)."""
        try:
            self.media_for(track, session, None)
        except Exception as e:  # noqa: BLE001 - only a head start: the real request will say what's wrong
            logger.info("Couldn't get the next song ready for %s: %s", session.name, e)

    def _ensure_analyser(self):
        if self._analyser is None:
            from .analysis import Analyser

            self._analyser = Analyser(self)
        return self._analyser

    def _render_path(self, key):
        if self._render_dir is None:
            from .core import paths

            self._render_dir = paths.cache_dir() / "cast"
            self._render_dir.mkdir(parents=True, exist_ok=True)
        return str(self._render_dir / f"{key}.wav")

    def _trim_renders(self):
        done = [(k, v) for k, v in self._renders.items() if "file" in v]
        for k, v in done[:-KEEP_RENDERS]:
            self._renders.pop(k, None)
            try:
                os.remove(v["file"])
            except OSError:
                pass

    def _clear_renders(self):
        if self._analyser is not None:
            self._analyser.cancel()
        self._renders.clear()
        if self._render_dir is not None:
            shutil.rmtree(self._render_dir, ignore_errors=True)

    def _cover(self, track):
        art = track.get("art") or ""
        if not art and self._cover_for is not None:
            try:
                art = self._cover_for(track) or ""
            except Exception:  # noqa: BLE001
                art = ""
        if not art or not os.path.isfile(art):
            return b""
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QImage

        image = QImage(art)
        if image.isNull():
            return b""
        if max(image.width(), image.height()) > 800:
            image = image.scaled(800, 800, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "JPG", 88)
        buf.close()
        return bytes(data)

    def shutdown(self):
        if self._session is not None:
            self._session.close(stop_device=True)
            self._session = None
        self._server.stop()
        self._clear_renders()
        if self._analyser is not None:
            self._analyser.shutdown()


def _discover():
    """Chromecasts and DLNA renderers on the network, each a device dict with "kind". Both searches run at once.
    A machine that is both (some TVs) is listed once, as a Chromecast (the better connection)."""
    interfaces = upnp.local_interfaces()
    results = {}

    def cast():
        results["cast"] = mdns.browse(DISCOVERY_S, interfaces)

    def dlna():
        results["dlna"] = upnp.discover(DISCOVERY_S, interfaces)

    threads = [threading.Thread(target=f, daemon=True) for f in (cast, dlna)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(DISCOVERY_S + 10)
    out, hosts = [], set()
    for dev in (results.get("cast") or {}).values():
        out.append(dict(dev, kind="chromecast"))
        hosts.add(dev["host"])
    for dev in (results.get("dlna") or {}).values():
        if dev["host"] not in hosts:
            out.append(dict(dev, kind="upnp"))
    return out
