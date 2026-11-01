"""Casting's network side, against fake devices: finding Chromecasts (mDNS) and DLNA renderers (SSDP), talking to
each, and the media server they fetch songs from. Everything a device sends is treated as hostile."""
import http.client
import os
import random
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from hallucinate.core.cast import castv2, mdns, mediaserver, upnp


def wait(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


# --- mDNS ---------------------------------------------------------------------------------------------------
def rr(name, rtype, rdata):
    return mdns.encode_name(name) + struct.pack("!HHIH", rtype, 0x8001, 120, len(rdata)) + rdata


def cast_reply(address="192.168.1.50", fn="Living Room speaker", port=8009):
    inst = "Google-Home-abc123._googlecast._tcp.local"
    txt = b"".join(bytes([len(x)]) + x for x in (b"id=abc123", f"fn={fn}".encode(), b"md=Google Home"))
    srv = struct.pack("!HHH", 0, 0, port) + mdns.encode_name("abc123.local")
    records = [rr(mdns.CHROMECAST, mdns.T_PTR, mdns.encode_name(inst)), rr(inst, mdns.T_SRV, srv),
               rr(inst, mdns.T_TXT, txt), rr("abc123.local", mdns.T_A, socket.inet_aton(address))]
    return struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 3) + b"".join(records)


def test_a_chromecast_answer_is_read():
    devices = mdns.services(mdns.parse(cast_reply()), sender="192.168.1.50")
    (dev,) = devices.values()
    assert dev == {"name": "Living Room speaker", "model": "Google Home", "id": "abc123",
                   "host": "192.168.1.50", "port": 8009}


def test_a_device_cant_point_us_at_another_machine():
    devices = mdns.services(mdns.parse(cast_reply(address="10.0.0.1")), sender="192.168.1.50")
    assert next(iter(devices.values()))["host"] == "192.168.1.50"


def test_the_question_is_well_formed():
    q = mdns.query()
    assert q[4:6] == b"\0\1" and q.endswith(struct.pack("!HH", mdns.T_PTR, 0x8001))


@pytest.mark.parametrize("packet", [
    b"",  # nothing
    struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + b"\xc0\x0c",  # a name pointing at itself
    struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + b"\xc0\x40",  # a pointer forwards
    struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0) + b"\x3fabc",  # a label running off the end
    struct.pack("!HHHHHH", 0, 0x8400, 0, 60000, 0, 0),  # far too many records
    struct.pack("!HHHHHH", 0, 0x0000, 0, 1, 0, 0),  # a question, not an answer
])
def test_broken_answers_are_refused(packet):
    with pytest.raises(mdns.Malformed):
        mdns.parse(packet)


def test_random_and_mangled_answers_never_do_worse_than_refuse():
    rnd = random.Random(1234)
    good = cast_reply()
    for i in range(3000):
        if i % 2:
            data = bytes(rnd.getrandbits(8) for _ in range(rnd.randrange(0, 300)))
        else:
            data = bytearray(good)
            for _ in range(rnd.randrange(1, 8)):
                data[rnd.randrange(len(data))] = rnd.getrandbits(8)
            data = bytes(data[:rnd.randrange(len(data) + 1)])
        try:
            mdns.services(mdns.parse(data), sender="192.168.1.50")
        except (mdns.Malformed, struct.error):
            pass


# --- Cast v2 ------------------------------------------------------------------------------------------------
def test_cast_messages_round_trip():
    framed = castv2.encode(castv2.NS_MEDIA, {"type": "PLAY", "requestId": 7}, destination="web-5")
    size = struct.unpack("!I", framed[:4])[0]
    assert size == len(framed) - 4
    ns, src, dst, payload = castv2.decode(framed[4:])
    assert (ns, src, dst, payload) == (castv2.NS_MEDIA, castv2.SENDER, "web-5", {"type": "PLAY", "requestId": 7})


def test_statuses_are_checked():
    assert castv2.media_status({"status": [{"mediaSessionId": True, "playerState": "EXPLODE",
                                            "currentTime": -5, "media": {"duration": "long"}}]}) == {
        "session": None, "state": "", "idle_reason": "", "position": None, "duration": None}
    assert castv2.media_status({"status": "nope"}) is None
    assert castv2.receiver_status({"status": {"volume": {"level": 7}}})["volume"] is None


class FakeChromecast:
    """Speaks just enough Cast v2 over a plain socket: launch, load (fetching the song like a device does),
    play/pause/seek, volume, pings."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.seen = []
        self.fetched = None
        self.conn = None
        self.state = {"app": False, "session": 0, "time": 0.0, "player": "IDLE"}
        threading.Thread(target=self.run, daemon=True).start()

    def send(self, ns, payload, src="receiver-0", dst=castv2.SENDER):
        self.conn.sendall(castv2.encode(ns, payload, source=src, destination=dst))

    def receiver_status(self, rid=0):
        apps = [{"appId": castv2.DEFAULT_MEDIA_RECEIVER, "transportId": "web-5", "sessionId": "S1"}] \
            if self.state["app"] else []
        self.send(castv2.NS_RECEIVER, {"type": "RECEIVER_STATUS", "requestId": rid,
                                       "status": {"applications": apps, "volume": {"level": 0.4, "muted": False}}})

    def media_status(self, rid=0, idle_reason=None):
        st = {"mediaSessionId": 1, "playerState": self.state["player"], "currentTime": self.state["time"],
              "media": {"duration": 200.0}}
        if idle_reason:
            st["idleReason"] = idle_reason
        self.send(castv2.NS_MEDIA, {"type": "MEDIA_STATUS", "requestId": rid, "status": [st]}, src="web-5")

    def run(self):
        self.conn, _ = self.sock.accept()
        buf = b""
        while True:
            try:
                chunk = self.conn.recv(65536)
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            while len(buf) >= 4 and len(buf) >= 4 + struct.unpack("!I", buf[:4])[0]:
                n = struct.unpack("!I", buf[:4])[0]
                ns, _src, dst, p = castv2.decode(buf[4:4 + n])
                buf = buf[4 + n:]
                self.seen.append((ns, dst, p.get("type")))
                try:
                    self.handle(ns, dst, p)
                except OSError:
                    return  # the client hung up

    def handle(self, ns, dst, p):
        kind, rid = p.get("type"), p.get("requestId", 0)
        if ns == castv2.NS_RECEIVER and kind == "GET_STATUS":
            self.receiver_status(rid)
        elif ns == castv2.NS_RECEIVER and kind == "LAUNCH":
            self.state["app"] = True
            self.receiver_status(rid)
        elif ns == castv2.NS_RECEIVER and kind == "SET_VOLUME":
            self.receiver_status(rid)
        elif ns == castv2.NS_MEDIA and kind == "LOAD":
            url = p["media"]["contentId"]
            parts = url.split("/", 3)
            host, port = parts[2].rsplit(":", 1)
            c = http.client.HTTPConnection(host, int(port), timeout=5)
            c.request("GET", "/" + parts[3])
            r = c.getresponse()
            self.fetched = (r.status, r.getheader("Content-Type"), r.read())
            c.close()
            self.state.update(player="PLAYING", time=0.0)
            self.media_status(rid)
        elif ns == castv2.NS_MEDIA and kind == "PAUSE":
            self.state["player"] = "PAUSED"
            self.media_status(rid)
        elif ns == castv2.NS_MEDIA and kind == "SEEK":
            self.state["time"] = p["currentTime"]
            self.media_status(rid)


def plain_connect(host, port, timeout):
    return socket.create_connection((host, port), timeout=timeout)


@pytest.fixture
def media(tmp_path):
    server = mediaserver.MediaServer(port=0)
    assert server.start("127.0.0.1")
    yield server
    server.stop()


def test_casting_to_a_chromecast(media, tmp_path):
    song = tmp_path / "song.flac"
    song.write_bytes(b"fLaC" + os.urandom(5000))
    device = FakeChromecast()
    statuses, receivers, closed = [], [], []
    client = castv2.CastClient("127.0.0.1", device.port, on_media=statuses.append, on_receiver=receivers.append,
                               on_closed=closed.append, connect=plain_connect)
    client.start()
    client.launch(timeout=5)
    url = media.url("127.0.0.1", media.share("127.0.0.1", path=str(song)))
    client.load(url, "audio/flac", title="Song", artist="Someone", album="Record", duration=200)
    assert wait(lambda: statuses and statuses[-1]["state"] == "PLAYING")
    assert device.fetched == (200, "audio/flac", song.read_bytes())  # the device got the file as it is
    client.pause()
    assert wait(lambda: statuses[-1]["state"] == "PAUSED")
    client.seek(42)
    assert wait(lambda: statuses[-1]["position"] == 42)
    client.set_volume(0.4)
    assert wait(lambda: any(r["volume"] == 0.4 for r in receivers))
    assert ("urn:x-cast:com.google.cast.tp.connection", "web-5", "CONNECT") in device.seen  # joined the app
    client.close()
    assert wait(lambda: closed)
    assert not client.connected


def test_a_chromecast_that_sends_too_much_is_dropped():
    device = FakeChromecast()
    closed = []
    client = castv2.CastClient("127.0.0.1", device.port, on_closed=closed.append, connect=plain_connect)
    client.start()
    assert wait(lambda: device.conn is not None)
    device.conn.sendall(struct.pack("!I", castv2.MAX_MESSAGE + 1) + b"x" * 100)
    assert wait(lambda: closed)
    assert "too big" in closed[0]


def test_the_player_app_closing_isnt_the_device_going_away():
    device = FakeChromecast()
    statuses, closed = [], []
    client = castv2.CastClient("127.0.0.1", device.port, on_media=statuses.append, on_closed=closed.append,
                               connect=plain_connect)
    client.start()
    client.launch(timeout=5)
    device.send(castv2.NS_CONNECTION, {"type": "CLOSE"}, src="web-5")
    assert wait(lambda: statuses and statuses[-1]["idle_reason"] == "INTERRUPTED")
    assert not closed and client.connected
    client.close()


def test_pings_are_answered():
    device = FakeChromecast()
    client = castv2.CastClient("127.0.0.1", device.port, connect=plain_connect)
    client.start()
    assert wait(lambda: device.conn is not None)
    device.send(castv2.NS_HEARTBEAT, {"type": "PING"})
    assert wait(lambda: (castv2.NS_HEARTBEAT, "receiver-0", "PONG") in device.seen)
    client.close()


# --- UPnP ---------------------------------------------------------------------------------------------------
DESCRIPTION = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><device>
  <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
  <friendlyName>Kitchen &amp; Dining</friendlyName><manufacturer>Acme</manufacturer><modelName>Speaker 2</modelName>
  <UDN>uuid:1234</UDN>
  <serviceList>
    <service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
      <controlURL>/av</controlURL></service>
    <service><serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
      <controlURL>/rc</controlURL></service>
    <service><serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType>
      <controlURL>http://10.9.9.9/cm</controlURL></service>
  </serviceList></device></root>"""


class FakeRenderer(BaseHTTPRequestHandler):
    calls = []
    description = DESCRIPTION.encode()

    def log_message(self, *a):
        pass

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.description)))
        self.end_headers()
        self.wfile.write(self.description)

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        action = self.headers["SOAPACTION"].strip('"').split("#")[1]
        type(self).calls.append((self.path, action, body))
        out = {"GetTransportInfo": "<CurrentTransportState>PAUSED_PLAYBACK</CurrentTransportState>",
               "GetPositionInfo": "<RelTime>0:01:05</RelTime><TrackDuration>0:03:20.500</TrackDuration>",
               "GetVolume": "<CurrentVolume>35</CurrentVolume>"}.get(action, "")
        if action == "Seek":
            resp = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault><detail>'
                    '<UPnPError><errorCode>710</errorCode><errorDescription>Seek mode not supported</errorDescription>'
                    '</UPnPError></detail></s:Fault></s:Body></s:Envelope>').encode()
            self.send_response(500)
        else:
            resp = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                    f'<u:{action}Response xmlns:u="x">{out}</u:{action}Response></s:Body></s:Envelope>').encode()
            self.send_response(200)
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


@pytest.fixture
def renderer():
    FakeRenderer.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeRenderer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/desc.xml"
    server.shutdown()
    server.server_close()


def test_a_renderer_is_described_and_kept_to_its_own_machine(renderer):
    dev = upnp.describe(renderer, "127.0.0.1")
    assert dev["name"] == "Kitchen & Dining" and dev["model"] == "Speaker 2" and dev["id"] == "uuid:1234"
    assert dev["controls"][upnp.AVTRANSPORT].endswith("/av")
    assert upnp.CONNECTION not in dev["controls"]  # it pointed at another machine
    with pytest.raises(upnp.UpnpError):
        upnp.describe(renderer, "127.0.0.2")  # the description isn't on the machine that answered


def test_controlling_a_renderer(renderer):
    r = upnp.Renderer(upnp.describe(renderer, "127.0.0.1"))
    r.load("http://127.0.0.1:1/m/x.flac", "audio/flac", title="A <b> & C", artist="D", album="E", duration=200)
    r.play()
    assert [c[1] for c in FakeRenderer.calls] == ["Stop", "SetAVTransportURI", "Play"]
    body = FakeRenderer.calls[1][2]
    assert "A &amp;lt;b&amp;gt; &amp;amp; C" in body  # escaped in the metadata, and again in the SOAP
    assert r.status() == {"state": "PAUSED", "position": 65.0, "duration": 200.5, "uri": ""}
    assert r.volume() == 0.35
    r.set_volume(0.8)
    assert "<DesiredVolume>80</DesiredVolume>" in FakeRenderer.calls[-1][2]
    with pytest.raises(upnp.UpnpError) as err:
        r.seek(30)
    assert err.value.code == "710" and "Seek mode not supported" in str(err.value)


def test_xml_with_a_doctype_is_refused(renderer):
    FakeRenderer.description = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><root>&a;</root>'
    try:
        with pytest.raises(upnp.UpnpError):
            upnp.describe(renderer, "127.0.0.1")
    finally:
        FakeRenderer.description = DESCRIPTION.encode()


@pytest.mark.parametrize("url,ok", [
    ("http://192.168.1.9:1400/d.xml", True),
    ("http://192.168.1.10/d.xml", False),
    ("https://192.168.1.9/d.xml", False),
    ("file:///etc/passwd", False),
    ("http://router.local/d.xml", False),
    ("http://192.168.1.9:99999/d.xml", False),
])
def test_only_the_device_that_answered(url, ok):
    assert bool(upnp.same_machine(url, "192.168.1.9")) is ok


def test_times_and_answers():
    assert upnp.hms(3725.9) == "1:02:05"
    assert upnp.seconds("0:03:20.500") == 200.5 and upnp.seconds("NOT_IMPLEMENTED") is None
    headers = upnp.parse_answer(b"HTTP/1.1 200 OK\r\nLOCATION: http://1.2.3.4/x\r\nST: a\r\n\r\n")
    assert headers == {"location": "http://1.2.3.4/x", "st": "a"}
    assert upnp.parse_answer(b"GET / HTTP/1.1\r\n\r\n") is None


# --- the media server ---------------------------------------------------------------------------------------
def get(server, path, source="127.0.0.1", method="GET", headers=None):
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5, source_address=(source, 0))
    c.request(method, path, headers=headers or {})
    r = c.getresponse()
    out = (r.status, dict(r.getheaders()), r.read())
    c.close()
    return out


def test_a_link_works_for_its_device_only(media, tmp_path):
    song = tmp_path / "a.mp3"
    song.write_bytes(bytes(range(256)) * 40)
    link = media.share("127.0.0.1", path=str(song))
    status, headers, body = get(media, link)
    assert status == 200 and body == song.read_bytes() and headers["Content-Type"] == "audio/mpeg"
    assert headers["Accept-Ranges"] == "bytes"
    assert get(media, link, source="127.0.0.2")[0] == 404  # another machine
    assert get(media, "/m/" + "A" * 32)[0] == 404  # a guess
    assert get(media, "/etc/passwd")[0] == 404
    assert get(media, link, method="POST")[0] == 405


def test_seeking_by_byte_ranges(media, tmp_path):
    song = tmp_path / "a.flac"
    data = os.urandom(10_000)
    song.write_bytes(data)
    link = media.share("127.0.0.1", path=str(song))
    status, headers, body = get(media, link, headers={"Range": "bytes=100-199"})
    assert status == 206 and body == data[100:200] and headers["Content-Range"] == "bytes 100-199/10000"
    assert get(media, link, headers={"Range": "bytes=9000-"})[2] == data[9000:]
    assert get(media, link, headers={"Range": "bytes=-50"})[2] == data[-50:]
    assert get(media, link, headers={"Range": "bytes=20000-"})[0] == 416
    status, headers, body = get(media, link, method="HEAD")
    assert status == 200 and headers["Content-Length"] == "10000" and body == b""


def test_old_links_stop_working(media, tmp_path):
    song = tmp_path / "a.ogg"
    song.write_bytes(b"x")
    first = media.share("127.0.0.1", path=str(song))
    for _ in range(mediaserver.KEEP_LINKS):
        media.share("127.0.0.1", path=str(song))
    assert get(media, first)[0] == 404
    later = media.share("127.0.0.1", path=str(song))
    media.forget(later)
    assert get(media, later)[0] == 404


def test_a_live_stream(media):
    link = media.share("127.0.0.1", live=lambda: iter([b"RIFF", b"1234", b"data"]), ctype="audio/wav",
                       name="live.wav")
    status, headers, body = get(media, link)
    assert status == 200 and body == b"RIFF1234data" and "Content-Length" not in headers
    assert headers["contentFeatures.dlna.org"].startswith("DLNA.ORG_OP=00")


def test_an_address_is_required(media):
    with pytest.raises(ValueError):
        media.share("not-an-address", data=b"x")
