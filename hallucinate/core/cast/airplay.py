"""AirPlay speakers (RAOP, the first AirPlay: AirPort Express, shairport-sync, and the many speakers, receivers
and TVs that take it): Hallucinate streams the sound to the speaker itself.

The talk is RTSP over TCP (ANNOUNCE what's coming, SETUP the UDP ports, RECORD, and FLUSH, SET_PARAMETER for
the volume, TEARDOWN). The audio goes as RTP packets over UDP, 352 frames of 44.1 kHz 16-bit stereo each,
packed as ALAC frames that are stored rather than compressed (every receiver decodes those, and they're lossless).
The speaker plays each packet `LATENCY_FRAMES` after the moment the sender's sync packets say it belongs to, so
everything it's sent is heard about two seconds later; pause, seek and skipping FLUSH what it holds, so those
answer at once (what had been sent but not heard is sent again).

Alongside: the speaker asks this computer for the time (timing packets, answered on the timing port) and for
packets that went missing (resend requests, answered from the last few seconds kept on hand). Both its ports are
first sent to from ours, so a firewall that lets replies in lets them in too.

Only speakers that take the stream unencrypted and without a password are offered (most do). Ones that need
AirPlay 2's pairing (recent Apple TVs and HomePods, when set to) answer the setup with a refusal, said so.

The speaker is only ever reached on the local network (net.connect_local), its answers are size-checked, and
the UDP ports only take packets from its own address."""
import os
import random
import re
import select
import socket
import struct
import threading
import time

import numpy as np

from .. import net
from . import pcm

SERVICE = "_raop._tcp.local"
RATE, CHANNELS, WIDTH = 44100, 2, 2
FRAME = CHANNELS * WIDTH
PACKET_FRAMES = 352
LATENCY_FRAMES = 88200  # 2 s: what speakers expect from a sender (iTunes' own)
LEAD_S = 0.3  # how far ahead of real time packets are sent (well inside the speaker's latency)
KEEP_PACKETS = 512  # about 4 s of packets kept to resend
KEEPALIVE_S = 15.0
MAX_HEADERS = 64 * 1024
MAX_BODY = 256 * 1024
NTP_EPOCH = 2208988800  # 1900 to 1970


class AirplayError(OSError):
    pass


class Refused(AirplayError):
    """The speaker said no: `status` is its answer (401 a password, 403/470 pairing, 453 busy)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


# --- finding speakers -------------------------------------------------------------------------------------------
def _flags(txt, key):
    return {p.strip() for p in str(txt.get(key, "")).split(",") if p.strip()}


def describe(service):
    """A speaker from its mDNS answer (mdns.services). One that can't play this stream has "unsupported": why
    ("password": it needs one; "encrypted": it only takes encrypted audio; "format": not ALAC at 44.1 kHz 16-bit
    stereo), so it can be listed but not picked."""
    txt = service.get("txt") or {}
    # the service is called "MAC@Name" (mdns.services gives that as the name, or as the id when it has no id of its own)
    label = next((v for v in (service.get("name", ""), service.get("id", "")) if "@" in v), service.get("name", ""))
    mac, _, name = label.partition("@")
    if not name:
        mac, name = "", label
    et, cn = _flags(txt, "et"), _flags(txt, "cn")
    why = ""
    if str(txt.get("pw", "")).lower() == "true":
        why = "password"
    elif et and "0" not in et:
        why = "encrypted"
    elif (cn and "1" not in cn) or txt.get("sr", "44100") != "44100" or txt.get("ss", "16") != "16" \
            or txt.get("ch", "2") != "2":
        why = "format"
    device = {"id": "airplay:" + (mac or name)[:64], "kind": "airplay", "name": name[:100] or "AirPlay",
              "model": (txt.get("am") or "AirPlay")[:100], "host": service["host"], "port": service["port"]}
    return dict(device, unsupported=why) if why else device


def discover(timeout=2.0, interfaces=("",), browse=None):
    """AirPlay speakers announced on the network: {device id: device}."""
    from . import mdns

    found = {}
    for service in (browse or mdns.browse)(timeout=timeout, interfaces=interfaces, service=SERVICE).values():
        device = describe(service)
        found[device["id"]] = device
    return found


# --- the sound, as packets -------------------------------------------------------------------------------------
def alac_frame(data):
    """`data` (PACKET_FRAMES of 16-bit little-endian stereo PCM) as one ALAC frame, stored uncompressed: a 23-bit
    header (a channel pair, no size given, not compressed), the samples big-endian, then the end tag (7)."""
    s = np.frombuffer(data, "<i2").astype(">i2").view(np.uint8)
    s = np.concatenate([s, np.array([0xE0], np.uint8)])  # 111 (end) then padding
    out = np.empty(len(s) + 3, np.uint8)
    out[0], out[1] = 0x20, 0x00
    out[2] = 0x02 | (s[0] >> 7)
    out[3:-1] = ((s[:-1] & 0x7F) << 1) | (s[1:] >> 7)
    out[-1] = (s[-1] & 0x7F) << 1
    return out.tobytes()


def ntp(now=None):
    """`now` (time.time()) as a 64-bit NTP timestamp."""
    now = time.time() if now is None else now
    seconds = int(now) + NTP_EPOCH
    return (seconds << 32) | int((now % 1) * (1 << 32))


def rtp_packet(seq, timestamp, ssrc, payload, first=False):
    return struct.pack("!BBHII", 0x80, 0xE0 if first else 0x60, seq & 0xFFFF, timestamp & 0xFFFFFFFF, ssrc) + payload


def sync_packet(now_rtp, first=False, now=None):
    """Tells the speaker that frame `now_rtp - LATENCY_FRAMES` is to be heard at this moment."""
    return struct.pack("!BBHIQI", 0x90 if first else 0x80, 0xD4, 7, (now_rtp - LATENCY_FRAMES) & 0xFFFFFFFF,
                       ntp(now), now_rtp & 0xFFFFFFFF)


def timing_reply(request, now=None):
    """The answer to a speaker's timing request: its own send time back, and ours (received, sent)."""
    if len(request) < 32 or request[1] & 0x7F != 0x52:
        return None
    stamp = ntp(now)
    return struct.pack("!BBHI", 0x80, 0xD3, 7, 0) + request[24:32] + struct.pack("!QQ", stamp, stamp)


def volume_db(level):
    """0..1 as the speaker's scale: -30 dB (quietest) to 0 dB, and -144 for silence."""
    level = min(1.0, max(0.0, float(level)))
    return -144.0 if level <= 0 else -30.0 + 30.0 * level


# --- RTSP ------------------------------------------------------------------------------------------------------
class Rtsp:
    """One RTSP conversation with a speaker (requests one at a time, answers size-checked)."""

    def __init__(self, sock, local_ip):
        self._sock = sock
        self._buf = b""
        self._lock = threading.Lock()
        self.cseq = 0
        self.session = ""
        self.sid = random.randint(1, 2**31 - 1)
        self.url = f"rtsp://{local_ip}/{self.sid}"
        self.instance = os.urandom(8).hex().upper()
        self.dacp = os.urandom(8).hex().upper()
        self.remote = str(random.randint(1, 2**31 - 1))

    def _readline(self, limit):
        while b"\r\n" not in self._buf:
            if len(self._buf) > limit:
                raise AirplayError("the speaker's answer was too long")
            chunk = self._sock.recv(4096)
            if not chunk:
                raise AirplayError("the speaker closed the connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\r\n", 1)
        return line.decode("latin-1")

    def _read(self, n):
        while len(self._buf) < n:
            chunk = self._sock.recv(min(65536, n - len(self._buf)))
            if not chunk:
                raise AirplayError("the speaker closed the connection")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def request(self, method, url=None, headers=None, body=b"", content_type=""):
        """(status, headers, body). Raises Refused for anything but 2xx."""
        with self._lock:
            self.cseq += 1
            lines = [f"{method} {url or self.url} RTSP/1.0", f"CSeq: {self.cseq}", "User-Agent: AirPlay/381.13",
                     f"Client-Instance: {self.instance}", f"DACP-ID: {self.dacp}", f"Active-Remote: {self.remote}"]
            if self.session:
                lines.append(f"Session: {self.session}")
            for k, v in (headers or {}).items():
                lines.append(f"{k}: {v}")
            if body:
                lines += [f"Content-Type: {content_type}", f"Content-Length: {len(body)}"]
            self._sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body)
            status_line = self._readline(MAX_HEADERS)
            m = re.match(r"RTSP/1\.0 (\d{3})", status_line)
            if not m:
                raise AirplayError("the speaker answered something that isn't RTSP")
            status = int(m.group(1))
            answer, size = {}, 0
            while True:
                line = self._readline(MAX_HEADERS)
                size += len(line)
                if size > MAX_HEADERS:
                    raise AirplayError("the speaker's answer was too long")
                if not line:
                    break
                k, _, v = line.partition(":")
                answer[k.strip().lower()] = v.strip()
            length = int(answer.get("content-length", "0") or 0)
            if not 0 <= length <= MAX_BODY:
                raise AirplayError("the speaker's answer was too long")
            data = self._read(length) if length else b""
        if not 200 <= status < 300:
            raise Refused(status, f"{method}: {status_line[9:].strip()[:100]}")
        return status, answer, data


def sdp(local_ip, remote_ip, sid):
    return ("v=0\r\n"
            f"o=iTunes {sid} 0 IN IP4 {local_ip}\r\n"
            "s=iTunes\r\n"
            f"c=IN IP4 {remote_ip}\r\n"
            "t=0 0\r\n"
            "m=audio 0 RTP/AVP 96\r\n"
            "a=rtpmap:96 AppleLossless\r\n"
            f"a=fmtp:96 {PACKET_FRAMES} 0 16 40 10 14 2 255 0 0 {RATE}\r\n").encode("ascii")


def _transport(value):
    out = {}
    for part in value.split(";"):
        k, _, v = part.partition("=")
        if v.isdigit() and 0 < int(v) < 65536:
            out[k.strip().lower()] = int(v)
    return out


# --- the speaker -----------------------------------------------------------------------------------------------
class Speaker:
    """Plays a pcm.Queue's songs on one AirPlay speaker, from connect() to close().

    on_event(kind, tag): "advanced", "ended" (as pcm.Queue's, once heard) and "lost" (the speaker went away).
    Called on the sender's threads."""

    def __init__(self, host, port, on_event=None, connect=None, clock=time.monotonic):
        self.host, self.port = host, int(port)
        self.on_event = on_event or (lambda kind, tag: None)
        self._connect = connect or net.connect_local
        self._clock = clock
        self.queue = pcm.Queue(RATE, clock, CHANNELS, WIDTH)
        self._rtsp = None
        self._sock = None
        self._audio = self._control = self._timing = None
        self._ports = {}
        self._remote = host
        self._ssrc = random.getrandbits(32)
        self._seq = random.getrandbits(16)
        self._rtp = random.getrandbits(32)
        self._kept = {}
        self._lock = threading.RLock()  # the anchor below, and the order of FLUSH and packets
        self._anchor = None  # (clock, rtp time) the packets are timed from, or None: start afresh
        self._sent = 0  # frames sent since the anchor
        self._first = True
        self._last_sync = 0
        self._pending = []  # [(when heard, kind, tag)]
        self._closed = False
        self._lost = False
        self.taken = False  # the speaker hung up: another device took it over
        self._wake = threading.Event()  # (paused, the sender sleeps until there's something to send)
        self._threads = []
        self._last_talk = clock()

    # --- connecting ------------------------------------------------------------------------------------------
    def connect(self, timeout=8.0):
        sock = self._connect(self.host, self.port, timeout)
        try:
            sock.settimeout(timeout)
            self._remote = sock.getpeername()[0]
            local = sock.getsockname()[0]
            self._sock = sock
            self._rtsp = Rtsp(sock, local)
            self._rtsp.request("OPTIONS", "*")
            self._rtsp.request("ANNOUNCE", body=sdp(local, self._remote, self._rtsp.sid),
                               content_type="application/sdp")
            self._audio = self._udp(local)
            self._control = self._udp(local)
            self._timing = self._udp(local)
            transport = ("RTP/AVP/UDP;unicast;interleaved=0-1;mode=record;"
                         f"control_port={self._control.getsockname()[1]};timing_port={self._timing.getsockname()[1]}")
            _, answer, _ = self._rtsp.request("SETUP", headers={"Transport": transport})
            self._rtsp.session = answer.get("session", "").split(";")[0][:64]
            self._ports = _transport(answer.get("transport", ""))
            if "server_port" not in self._ports:
                raise AirplayError("the speaker didn't say where to send the sound")
            with self._lock:
                self._rtsp.request("RECORD", headers={"Range": "npt=0-",
                                                      "RTP-Info": f"seq={self._seq};rtptime={self._rtp}"})
            # (our ports speak first, so a firewall lets the speaker's answers back in)
            if "timing_port" in self._ports:
                self._timing.sendto(struct.pack("!BBHI", 0x80, 0xD2, 7, 0) + bytes(16) + struct.pack("!Q", ntp()),
                                    (self._remote, self._ports["timing_port"]))
            self._sync(first=True)
        except Exception:
            self.close()
            raise
        for target, name in ((self._send_loop, "airplay-audio"), (self._listen_loop, "airplay-control")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def _udp(self, local):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind((local, 0))
        except OSError:
            s.close()
            raise
        return s

    # --- commands --------------------------------------------------------------------------------------------
    def load(self, path, start_s=0.0, end_s=0.0, tag=None, play=True):
        with self._lock:
            self._flush(heard=False)  # (what was coming is replaced)
            try:
                self.queue.load(path, start_s, end_s, tag, play)
            except pcm.FormatError as e:
                raise AirplayError(str(e)) from None
        self._wake.set()

    def queue_next(self, path, tag=None):
        try:
            self.queue.queue_next(path, tag)
        except pcm.FormatError as e:
            raise AirplayError(str(e)) from None

    def pause(self):
        with self._lock:
            self.queue.pause()
            self._back_to_heard()

    def _back_to_heard(self):
        """The speaker drops what it holds, and the queue goes back to what was being heard, to send it again."""
        undone = self.queue.rewind(self._unheard())
        self._flush(heard=not undone)

    def play(self):
        with self._lock:
            self.queue.play()
        self._wake.set()

    def seek(self, seconds):
        with self._lock:
            self._back_to_heard()  # (the song being heard is the one seeked in)
            self.queue.seek(seconds)
        self._wake.set()

    def stop(self):
        with self._lock:
            self.queue.stop()
            self._flush(heard=False)

    def set_volume(self, level):
        self._rtsp.request("SET_PARAMETER", body=f"volume: {volume_db(level):.6f}\r\n".encode("ascii"),
                           content_type="text/parameters")
        self._last_talk = self._clock()

    def position(self):
        """(tag, seconds) of what the speaker is playing now, as near as can be told."""
        with self._lock:
            return self.queue.position(self._unheard())

    def close(self):
        self._closed = True
        self._wake.set()
        try:
            self.queue.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._rtsp is not None and not self._lost:
            try:
                self._rtsp.request("TEARDOWN")
            except (OSError, ValueError):
                pass
        for s in (self._sock, self._audio, self._control, self._timing):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass

    # --- time ------------------------------------------------------------------------------------------------
    def _unheard(self):
        """Seconds of what's been sent that the speaker hasn't played yet."""
        if self._anchor is None or not self._sent:
            return 0.0
        elapsed = self._clock() - self._anchor[0]
        ahead = self._sent / RATE - elapsed
        return max(0.0, min(self._sent / RATE, ahead + LATENCY_FRAMES / RATE))

    def _flush(self, heard=True):
        """Drops what the speaker holds (it's been sent but not heard), and starts the timing afresh. Events
        about what was dropped happen now if `heard` (it still counts), else not at all."""
        due, self._pending = self._pending, []
        for _when, kind, tag in (due if heard else ()):
            self.on_event(kind, tag)
        if self._anchor is None or not self._sent:
            self._anchor = None
            return
        self._anchor = None
        self._sent = 0
        try:
            self._rtsp.request("FLUSH", headers={"RTP-Info": f"seq={self._seq};rtptime={self._rtp}"})
            self._last_talk = self._clock()
        except (OSError, ValueError):
            self._gone()

    def _sync(self, first=False):
        if self._control is None or "control_port" not in self._ports:
            return
        if self._anchor is None:
            now_rtp = self._rtp
        else:
            now_rtp = self._anchor[1] + int((self._clock() - self._anchor[0]) * RATE)
        try:
            self._control.sendto(sync_packet(now_rtp, first), (self._remote, self._ports["control_port"]))
        except OSError:
            pass

    def _gone(self):
        if not self._lost and not self._closed:
            self._lost = True
            self.on_event("lost", None)

    # --- the sender's threads --------------------------------------------------------------------------------
    def _send_loop(self):
        try:
            while not self._closed and not self._lost:
                self._fire_due()
                if not self.queue.playing and self._clock() - self._last_talk > KEEPALIVE_S:
                    self._keepalive()  # (paused; while it plays, the sound itself keeps the speaker with us)
                with self._lock:
                    if not self.queue.playing:
                        idle = True
                    else:
                        idle = False
                        if self._anchor is None:
                            self._anchor = (self._clock(), self._rtp)
                            self._sent, self._first = 0, True
                            self._last_sync = self._rtp
                            self._sync(first=True)
                        ahead = self._sent / RATE - (self._clock() - self._anchor[0])
                        if ahead <= LEAD_S:
                            self._packet(ahead)
                            continue
                if idle:  # (until played, or the next event or keep-alive is due)
                    self._wake.wait(0.05 if self._pending else 1.0)
                    self._wake.clear()
                else:
                    time.sleep(min(0.01, max(0.001, ahead - LEAD_S)))
        except OSError:
            self._gone()

    def _packet(self, ahead):
        heard_in = max(0.0, ahead) + LATENCY_FRAMES / RATE
        data, events = self.queue.pull(PACKET_FRAMES, heard_in)
        if data is None:
            return
        packet = rtp_packet(self._seq, self._rtp, self._ssrc, alac_frame(data), self._first)
        self._audio.sendto(packet, (self._remote, self._ports["server_port"]))
        self._kept[self._seq] = packet
        self._kept.pop((self._seq - KEEP_PACKETS) & 0xFFFF, None)
        self._seq = (self._seq + 1) & 0xFFFF
        self._rtp = (self._rtp + PACKET_FRAMES) & 0xFFFFFFFF
        self._sent += PACKET_FRAMES
        self._first = False
        if (self._rtp - self._last_sync) & 0xFFFFFFFF >= RATE:
            self._last_sync = self._rtp
            self._sync()
        when = self._clock() + heard_in
        self._pending += [(when, kind, tag) for kind, tag in events]

    def _fire_due(self):
        with self._lock:
            now = self._clock()
            due = [p for p in self._pending if p[0] <= now]
            self._pending = [p for p in self._pending if p[0] > now]
        for _when, kind, tag in due:
            self.on_event(kind, tag)

    def _keepalive(self):
        self._last_talk = self._clock()
        try:
            self._rtsp.request("OPTIONS", "*")
        except (OSError, ValueError):
            self._gone()

    def _taken(self):
        """Whether the speaker has hung up on us (it closes the RTSP connection when another device takes it
        over). Only looked at between requests: an answer to one is read by that request."""
        if self._closed or not self._rtsp._lock.acquire(blocking=False):
            return False
        try:
            if self._rtsp._buf:
                return False
            try:
                self._sock.setblocking(False)
                try:
                    return self._sock.recv(1, socket.MSG_PEEK) == b""
                finally:
                    self._sock.settimeout(8.0)
            except (BlockingIOError, InterruptedError):
                return False
            except OSError:
                return not self._closed  # (closed here: not taken, just done)
        finally:
            self._rtsp._lock.release()

    def _listen_loop(self):
        socks = [s for s in (self._control, self._timing) if s is not None]
        while not self._closed and not self._lost:
            try:
                ready, _, _ = select.select(socks + ([self._sock] if self._sock is not None else []), [], [], 0.5)
            except (OSError, ValueError):
                return
            if self._sock in ready:
                if self._taken():
                    self.taken = True
                    self._gone()
                    return
                ready = [s for s in ready if s is not self._sock]
                if not ready:
                    time.sleep(0.05)  # (an answer waiting for its request to read it)
            for s in ready:
                try:
                    data, (ip, port) = s.recvfrom(2048)
                except OSError:
                    continue
                if ip != self._remote:
                    continue  # only the speaker may ask
                if len(data) < 2:
                    continue
                kind = data[1] & 0x7F
                try:
                    if kind == 0x52 and s is self._timing:
                        reply = timing_reply(data)
                        if reply:
                            s.sendto(reply, (ip, port))
                    elif kind == 0x55 and s is self._control and len(data) >= 8:
                        first, count = struct.unpack("!HH", data[4:8])
                        with self._lock:
                            packets = [self._kept.get((first + i) & 0xFFFF) for i in range(min(count, 64))]
                        for packet in packets:
                            if packet is not None:
                                s.sendto(struct.pack("!BBH", 0x80, 0xD6, 1) + packet[:1] + bytes([0x60]) + packet[2:],
                                         (ip, self._ports.get("control_port", port)))
                except OSError:
                    continue
