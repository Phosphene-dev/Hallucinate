"""Casting from the player's side: handing a playing queue to a (fake) Chromecast or DLNA renderer, controlling it
from the app, moving on when the device finishes a song, and coming back to this computer."""
import http.client
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from audio import FFMPEG, encode
from conftest import wait_for
from test_cast_protocols import FakeChromecast, plain_connect

from hallucinate.core.cast import castv2, upnp

pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")


def track(path, i=0, dur=3.0, **extra):
    return dict({"id": i, "path": str(path), "title": f"T{i}", "artist": "A", "album": "B", "duration": dur,
                 "artUrl": ""}, **extra)


@pytest.fixture(scope="module")
def songs(tmp_path_factory):
    d = tmp_path_factory.mktemp("castsongs")
    return [track(encode(d / f"s{i}.flac", "flac", seconds=3.0, title=f"S{i}"), i, 3.0) for i in range(3)]


class Device(FakeChromecast):
    """The fake Chromecast, plus: remembers the volume, can finish the song, counts loads, and keeps a queue
    (QUEUE_INSERT/QUEUE_REMOVE) it can go straight on through (go_on)."""

    def __init__(self, fetch=True):
        self.loads = []
        self.volume = 0.5
        self.fetch = fetch
        self.items = []  # [(item id, address)]
        self.current = ""
        self.inserted = []
        self._ids = 0
        super().__init__()

    def _item(self, url):
        self._ids += 1
        return (self._ids, url)

    def media_status(self, rid=0, idle_reason=None):
        st = {"mediaSessionId": 1, "playerState": self.state["player"], "currentTime": self.state["time"],
              "media": {"duration": 200.0, "contentId": self.current},
              "items": [{"itemId": i, "media": {"contentId": u}} for i, u in self.items]}
        if idle_reason:
            st["idleReason"] = idle_reason
        self.send(castv2.NS_MEDIA, {"type": "MEDIA_STATUS", "requestId": rid, "status": [st]}, src="web-5")

    def go_on(self):
        """The song ends and the next in its queue starts, as a real device does it: no load from the sender."""
        urls = [u for _i, u in self.items]
        nxt = urls.index(self.current) + 1 if self.current in urls else len(urls)
        if nxt >= len(urls):
            self.finish()
            return False
        self.current, self.state["time"], self.state["player"] = urls[nxt], 0.0, "PLAYING"
        self.media_status()
        return True

    def handle(self, ns, dst, p):
        kind, rid = p.get("type"), p.get("requestId", 0)
        if ns == castv2.NS_MEDIA and kind == "QUEUE_INSERT":
            for item in p["items"]:
                self.items.append(self._item(item["media"]["contentId"]))
                self.inserted.append(item["media"]["contentId"])
            self.media_status(rid)
            return
        if ns == castv2.NS_MEDIA and kind == "QUEUE_REMOVE":
            self.items = [(i, u) for i, u in self.items if i not in p["itemIds"]]
            self.media_status(rid)
            return
        if ns == castv2.NS_MEDIA and kind == "LOAD":
            self.loads.append((p["media"]["contentId"], p["currentTime"], p["autoplay"], p["media"]["metadata"]))
            self.current = p["media"]["contentId"]
            self.items = [self._item(self.current)]
            if not self.fetch:
                return  # a device that can't reach us: never fetches, never starts
        if ns == castv2.NS_RECEIVER and kind == "SET_VOLUME":
            self.volume = p["volume"].get("level", self.volume)
            self.send(castv2.NS_RECEIVER, {"type": "RECEIVER_STATUS", "requestId": rid, "status": {
                "applications": [{"appId": castv2.DEFAULT_MEDIA_RECEIVER, "transportId": "web-5",
                                  "sessionId": "S1"}], "volume": {"level": self.volume, "muted": False}}})
            return
        if ns == castv2.NS_MEDIA and kind == "PLAY":
            self.state["player"] = "PLAYING"
            self.media_status(rid)
            return
        if ns == castv2.NS_MEDIA and kind == "GET_STATUS":
            self.media_status(rid)
            return
        super().handle(ns, dst, p)
        if ns == castv2.NS_MEDIA and kind == "LOAD":
            self.state["time"] = p["currentTime"]
            self.state["player"] = "PLAYING" if p["autoplay"] else "PAUSED"
            self.media_status(rid)

    def finish(self):
        self.state["player"] = "IDLE"
        self.media_status(idle_reason="FINISHED")


@pytest.fixture
def setup(qapp, tmp_path):
    from hallucinate.cast import Casting, ChromecastSession
    from hallucinate.player import Player

    made = []

    def make(device_kind="chromecast", **device_args):
        player = Player(session_file=tmp_path / "session.json")
        casting = Casting(player)
        casting._server.port = 0  # any free port
        if device_kind == "chromecast":
            dev = Device(**device_args)
            info = {"id": "cc1", "name": "Living Room", "model": "Chromecast", "host": "127.0.0.1",
                    "port": dev.port, "kind": "chromecast"}
            casting.session_factories["chromecast"] = lambda d, s: ChromecastSession(d, s, connect=plain_connect)
        else:
            dev = Renderer(**device_args)
            info = dict(upnp.describe(dev.location, "127.0.0.1"), kind="upnp")
        casting.discover = lambda servers: [info]
        made.append((player, casting, dev))
        return player, casting, dev

    yield make
    for player, casting, dev in made:
        casting.shutdown()
        player.shutdown()
        if isinstance(dev, Renderer):
            dev.close()


def connect(casting):
    casting.refresh()
    assert wait_for(lambda: casting.devices)
    casting.castTo(casting.devices[0]["id"])
    assert wait_for(lambda: casting.active), casting.error


def test_a_playing_queue_moves_to_a_chromecast_and_back(setup, songs):
    player, casting, dev = setup()
    player.playList(songs, 0)
    assert wait_for(lambda: player.state == "Playing" and player.position > 300)
    connect(casting)
    assert player.casting and casting.deviceName == "Living Room"
    assert wait_for(lambda: dev.loads)
    url, start, autoplay, meta = dev.loads[0]
    assert autoplay and 0.2 < start < 2.5 and meta["title"] == "T0"  # carried on from where it was
    assert wait_for(lambda: dev.fetched)
    assert dev.fetched[0] == 200 and dev.fetched[2] == open(songs[0]["path"], "rb").read()
    assert all(v.player.playbackState().name != "PlayingState" for v in player._voices)  # this computer is quiet
    assert wait_for(lambda: player.state == "Playing")
    path = player.signalPath
    assert path["untouched"] and path["stages"][-1]["detail"] == "Living Room (casting)"
    assert [st["key"] for st in path["stages"]] == ["source", "convert", "output"]  # nothing done here on the way

    player.pause()
    assert player.state == "Paused"
    assert wait_for(lambda: ("urn:x-cast:com.google.cast.media", "web-5", "PAUSE") in dev.seen)
    player.seek(1500)
    assert wait_for(lambda: dev.state["time"] == 1.5)
    player.setVolume(0.3)
    assert wait_for(lambda: dev.volume == 0.3 and abs(player.volume - 0.3) < 1e-6)

    player.play()
    assert wait_for(lambda: player.state == "Playing")
    dev.finish()  # the device reached the end of the song: the next one goes to it
    assert wait_for(lambda: len(dev.loads) == 2 and player.currentIndex == 1)
    assert dev.loads[1][3]["title"] == "T1" and dev.loads[1][1] == 0

    dev.state["time"] = 1.0
    dev.media_status()
    assert wait_for(lambda: player.position >= 900)
    casting.stopCasting()  # back here, from the device's place, still playing
    assert not player.casting
    assert wait_for(lambda: player.state == "Playing" and player.currentIndex == 1)
    assert wait_for(lambda: ("urn:x-cast:com.google.cast.receiver", "receiver-0", "STOP") in dev.seen)
    assert player.volume != 0.3  # this computer's own volume was never touched


def test_losing_the_device_holds_playback_here_paused(setup, songs):
    player, casting, dev = setup()
    player.playList(songs, 0)
    connect(casting)
    assert wait_for(lambda: player.state == "Playing")
    dev.conn.close()  # the device went away (unplugged, out of range)
    assert wait_for(lambda: not casting.active)
    assert not player.casting and player.state != "Playing"  # not suddenly blasting from this computer
    assert "Living Room" in casting.error


def test_a_device_that_cant_reach_us_says_so(setup, songs, monkeypatch):
    import hallucinate.cast as cast_mod

    monkeypatch.setattr(cast_mod, "START_TIMEOUT_S", 1)
    player, casting, dev = setup(fetch=False)
    player.playList(songs, 0)
    connect(casting)
    assert wait_for(lambda: "firewall" in player.error, timeout=10), player.error
    assert str(casting.portInUse) in player.error
    assert player.currentIndex == 0 and len(dev.loads) == 1  # not run through the whole queue


def test_a_format_the_device_cant_play_is_converted(setup, songs, tmp_path):
    player, casting, dev = setup()
    wv = encode(tmp_path / "x.wv", "wv", seconds=2.0)
    player.playList([track(wv, 9, dur=2.0, codec="WavPack")] + songs, 0)
    connect(casting)
    assert wait_for(lambda: dev.loads, timeout=30)
    assert wait_for(lambda: dev.fetched)
    status, ctype, body = dev.fetched
    assert status == 200 and ctype == "audio/wav" and body[:4] == b"RIFF"  # converted (at once: WAV), so it plays
    assert player.currentIndex == 0 and player.error == ""


def test_a_song_that_cant_be_got_ready_is_passed_over(setup, songs, tmp_path):
    player, casting, dev = setup()
    ape = tmp_path / "x.ape"
    ape.write_bytes(b"MAC " + b"\0" * 100)  # can't be decoded at all
    player.playList([track(ape, 9, codec="APE")] + songs, 0)
    connect(casting)
    assert wait_for(lambda: player.currentIndex == 1, timeout=30), player.error
    assert wait_for(lambda: dev.loads and dev.loads[0][3]["title"] == "T0")


def test_hallucinates_own_sound(setup, songs):
    player, casting, dev = setup()
    casting.setSending("processed")
    try:
        player.setEqEnabled(True)
        player.setEqBand(0, 6)
        player.playList(songs, 0)
        connect(casting)
        assert wait_for(lambda: dev.fetched, timeout=30)
        status, ctype, body = dev.fetched
        assert ctype == "audio/wav" and body[:4] == b"RIFF"  # (the first song, waited on: WAV, ready at once)
        url, start, autoplay, meta = dev.loads[0]
        assert meta["title"] == "T0" and autoplay
        keys = [st["key"] for st in player.signalPath["stages"]]
        assert "eq" in keys and "convert" in keys and not player.signalPath["untouched"]
        assert len(casting._renders) >= 1
        assert wait_for(lambda: len([r for r in casting._renders.values() if "file" in r]) >= 2, timeout=30)  # the next song got ready too
        assert any(r["file"].endswith(".flac") for r in casting._renders.values() if "file" in r)  # (ahead: FLAC)
    finally:
        casting.setSending("original")
        player.setEqEnabled(False)
        player.setEqBand(0, 0)
    casting.stopCasting()
    assert not (casting._render_dir and casting._render_dir.exists())  # nothing left behind


def test_a_cue_song_is_cut_out_for_the_device(setup, songs):
    player, casting, dev = setup()
    album = songs[0]["path"]
    cue = {"id": 50, "path": album + "#2", "file": album, "cue_start": 1.0, "cue_end": 2.5, "title": "Middle",
           "artist": "A", "album": "B", "duration": 1.5, "artUrl": ""}
    player.playList([cue], 0)
    connect(casting)
    assert wait_for(lambda: dev.fetched, timeout=30)
    import io
    import wave
    with wave.open(io.BytesIO(dev.fetched[2])) as w:  # (waited on: WAV)
        assert abs(w.getnframes() / w.getframerate() - 1.5) < 0.05  # just that song, not the whole album
    assert dev.loads[0][3]["title"] == "Middle"


# --- a DLNA renderer ----------------------------------------------------------------------------------------
class Renderer:
    """A stateful fake DLNA renderer: fetches what it's given, plays, pauses, seeks and can finish."""

    def __init__(self, sink="audio/flac,audio/mpeg", gapless=True):
        self.gapless = gapless  # takes SetNextAVTransportURI
        self.next_uri = ""
        self.calls = []
        self.state, self.pos, self.uri, self.volume = "NO_MEDIA_PRESENT", 0.0, "", 40
        self.fetched = []
        self.got = []  # (content type, the first bytes) of what it fetched
        self.sink = sink
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):  # noqa: N802
                body = DESCRIPTION.encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802
                import re
                body = self.rfile.read(int(self.headers["Content-Length"])).decode()
                action = self.headers["SOAPACTION"].strip('"').split("#")[1]
                outer.calls.append(action)
                args = dict(re.findall(r"<(\w+)>([^<]*)</\1>", body))
                if action == "SetNextAVTransportURI" and not outer.gapless:
                    fault = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault>'
                             '<detail><UPnPError><errorCode>401</errorCode></UPnPError></detail>'
                             '</s:Fault></s:Body></s:Envelope>').encode()
                    self.send_response(500)
                    self.send_header("Content-Length", str(len(fault)))
                    self.end_headers()
                    self.wfile.write(fault)
                    return
                out = outer.act(action, args)
                resp = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                        f'<u:{action}Response xmlns:u="x">{out}</u:{action}Response></s:Body></s:Envelope>').encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.location = f"http://127.0.0.1:{self.server.server_address[1]}/d.xml"

    def act(self, action, args):
        import html
        if action == "SetAVTransportURI":
            self.uri, self.state, self.pos = html.unescape(args["CurrentURI"]), "STOPPED", 0.0
            self.next_uri = ""
        elif action == "SetNextAVTransportURI":
            self.next_uri = html.unescape(args["NextURI"])
        elif action == "Play":
            parts = self.uri.split("/", 3)
            host, port = parts[2].rsplit(":", 1)
            c = http.client.HTTPConnection(host, int(port), timeout=5)
            c.request("GET", "/" + parts[3])
            r = c.getresponse()
            self.fetched.append(r.status)
            self.got.append((r.getheader("Content-Type"), r.read(4)))
            c.close()
            self.state = "PLAYING"
        elif action == "Pause":
            self.state = "PAUSED_PLAYBACK"
        elif action == "Stop":
            self.state = "STOPPED"
        elif action == "Seek":
            self.pos = upnp.seconds(args["Target"])
        elif action == "SetVolume":
            self.volume = int(args["DesiredVolume"])
        elif action == "GetVolume":
            return f"<CurrentVolume>{self.volume}</CurrentVolume>"
        elif action == "GetTransportInfo":
            return f"<CurrentTransportState>{self.state}</CurrentTransportState>"
        elif action == "GetPositionInfo":
            return (f"<RelTime>0:00:{self.pos:06.3f}</RelTime><TrackDuration>0:00:03</TrackDuration>"
                    f"<TrackURI>{html.escape(self.uri)}</TrackURI>")
        elif action == "GetProtocolInfo":
            return "<Sink>" + ",".join(f"http-get:*:{t}:*" for t in self.sink.split(",")) + "</Sink>"
        return ""

    def go_on(self):
        """The song ends and, given a next one, the TV goes straight into it (fetching it) by itself."""
        if not self.next_uri:
            self.state = "STOPPED"
            return False
        self.uri, self.next_uri, self.pos = self.next_uri, "", 0.0
        self.act("Play", {})
        return True

    def close(self):
        self.server.shutdown()
        self.server.server_close()


DESCRIPTION = """<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<friendlyName>Kitchen TV</friendlyName><UDN>uuid:tv</UDN><serviceList>
<service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType><controlURL>/av</controlURL></service>
<service><serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType><controlURL>/rc</controlURL></service>
<service><serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType><controlURL>/cm</controlURL></service>
</serviceList></device></root>"""


def test_playing_on_a_dlna_renderer(setup, songs):
    player, casting, dev = setup("upnp")
    player.playList(songs, 0)
    connect(casting)
    assert casting.deviceName == "Kitchen TV" and casting.deviceKind == "upnp"
    assert wait_for(lambda: dev.state == "PLAYING" and dev.fetched == [200])
    assert wait_for(lambda: player.state == "Playing")
    assert abs(player.volume - 0.4) < 1e-6  # the TV's own volume

    player.pause()
    assert wait_for(lambda: dev.state == "PAUSED_PLAYBACK")
    player.play()
    assert wait_for(lambda: dev.state == "PLAYING")
    player.setVolume(0.7)
    assert wait_for(lambda: dev.volume == 70)

    dev.pos = 2.9  # near the end … and then the TV stops by itself: the song finished
    assert wait_for(lambda: player._cast._last_pos >= 2.8)  # the TV said so
    dev.state = "STOPPED"
    assert wait_for(lambda: player.currentIndex == 1, timeout=10)
    assert wait_for(lambda: dev.state == "PLAYING" and dev.calls.count("SetAVTransportURI") == 2)

    dev.pos = 0.5
    assert wait_for(lambda: 400 <= player.position < 1500)
    dev.state = "STOPPED"  # stopped early, with the TV's remote: hold there rather than skip
    assert wait_for(lambda: player.state == "Paused", timeout=10), (player.state, player._cast.state, player.currentIndex, dev.state, dev.calls[-6:], player.error)
    assert player.currentIndex == 1


def test_the_phone_remote_can_choose_where_it_plays(setup, songs):
    from hallucinate.api import Api, ApiError

    player, casting, dev = setup()
    api = Api(player)
    api.casting = casting
    player.playList(songs, 0)
    assert api.call("features")["casting"] is True
    api.call("cast.search")
    assert wait_for(lambda: api.call("cast.devices")["devices"])
    listed = api.call("cast.devices")["devices"]
    assert listed == [{"id": "cc1", "name": "Living Room", "model": "Chromecast", "kind": "chromecast", "active": False}]
    with pytest.raises(ApiError):
        api.call("cast.to", {"id": "nope"})
    api.call("cast.to", {"id": "cc1"})
    assert wait_for(lambda: api.call("state")["castingOn"] == "Living Room")
    api.call("cast.stop")
    assert api.call("state")["castingOn"] == "" and not player.casting
    api.casting_on = lambda: False  # switched off in Settings → Features
    assert api.call("features")["casting"] is False
    with pytest.raises(ApiError):
        api.call("cast.devices")
    with pytest.raises(ApiError):
        api.call("cast.stop", allowed=("read",))  # (a read-only key can't change where it plays)


@pytest.mark.parametrize("sink,kind", [("audio/flac,audio/mpeg", "flac"), ("audio/mpeg,audio/wav", "wav"), ("", "wav")])
def test_converted_songs_go_as_flac_only_where_the_device_says_it_plays_it(setup, tmp_path, sink, kind):
    """The song waited on goes as WAV (ready at once); the next one, got ready while the first plays, as FLAC
    where the device says it plays it."""
    player, casting, dev = setup("upnp", sink=sink)
    wv = [encode(tmp_path / f"x{i}.wv", "wv", seconds=2.0) for i in range(2)]
    player.playList([track(w, 9 + i, dur=2.0, codec="WavPack") for i, w in enumerate(wv)], 0)
    connect(casting)
    assert wait_for(lambda: dev.got, timeout=30)
    assert dev.got[0] == ("audio/wav", b"RIFF")
    assert wait_for(lambda: dev.next_uri, timeout=30)  # the next one, handed over ahead
    assert dev.next_uri.endswith("." + kind)


# --- gapless on the device ----------------------------------------------------------------------------------
def test_a_chromecast_goes_straight_on_through_the_queue(setup, songs):
    player, casting, dev = setup()
    player.playList(songs, 0)
    connect(casting)
    assert wait_for(lambda: len(dev.loads) == 1 and dev.inserted, timeout=15)  # the next song handed over too
    assert dev.inserted[0].split("/")[-1] != dev.loads[0][0].split("/")[-1]
    assert dev.go_on()  # the device goes into it by itself
    assert wait_for(lambda: player.currentIndex == 1, timeout=10)
    assert len(dev.loads) == 1 and player.current["title"] == "T1"  # followed, not loaded again
    assert wait_for(lambda: len(dev.inserted) == 2, timeout=10)  # and the one after that handed over
    assert dev.go_on()
    assert wait_for(lambda: player.currentIndex == 2, timeout=10)
    assert len(dev.loads) == 1
    assert not dev.go_on()  # the end of the queue: it finishes
    assert wait_for(lambda: not player.playing, timeout=10)


def test_the_handed_over_song_follows_changes_to_the_queue(setup, songs):
    player, casting, dev = setup()
    player.playList(songs, 0)
    connect(casting)
    assert wait_for(lambda: len(dev.inserted) == 1, timeout=15)
    first = dev.inserted[0]
    player.moveItem(2, 1)  # the third song is next now
    assert wait_for(lambda: len(dev.inserted) == 2, timeout=10)
    assert first not in [u for _i, u in dev.items]  # the old one taken back
    assert dev.go_on()
    assert wait_for(lambda: player.currentIndex == 1 and player.current["title"] == "T2", timeout=10)
    assert len(dev.loads) == 1


def test_nothing_is_handed_over_when_the_sleep_timer_stops_after_this_song(setup, songs):
    player, casting, dev = setup()
    player.playList(songs, 0)
    connect(casting)
    assert wait_for(lambda: dev.inserted, timeout=15)
    player.setSleepAfterTrack(True)
    assert wait_for(lambda: not [u for _i, u in dev.items if u != dev.current], timeout=10)  # taken back
    player.setSleepAfterTrack(False)


def test_a_dlna_renderer_goes_straight_on_too(setup, songs):
    player, casting, dev = setup("upnp")
    player.playList(songs, 0)
    connect(casting)
    assert wait_for(lambda: dev.state == "PLAYING" and dev.next_uri, timeout=15)
    assert dev.go_on()
    assert wait_for(lambda: player.currentIndex == 1, timeout=10)
    assert dev.calls.count("SetAVTransportURI") == 1  # followed, not loaded again
    assert wait_for(lambda: dev.next_uri, timeout=10)  # the one after handed over


def test_a_renderer_without_it_moves_on_as_before(setup, songs):
    import time

    player, casting, dev = setup("upnp", gapless=False)
    player.playList(songs, 0)
    connect(casting)
    assert wait_for(lambda: dev.state == "PLAYING" and "SetNextAVTransportURI" in dev.calls, timeout=15)
    assert wait_for(lambda: not player._cast.gapless)
    dev.pos = 2.9
    assert wait_for(lambda: player._cast._last_pos >= 2.8)
    dev.state = "STOPPED"
    started = time.monotonic()
    assert wait_for(lambda: player.currentIndex == 1, timeout=10)
    assert time.monotonic() - started < 3  # (no waiting for a next song it was never going to play)
    assert wait_for(lambda: dev.calls.count("SetAVTransportURI") == 2)


def test_a_next_song_that_cant_be_got_ready_isnt_tried_over_and_over(setup, songs, tmp_path):
    player, casting, dev = setup()
    bad = tmp_path / "bad.ape"
    bad.write_bytes(b"MAC " + b"\0" * 100)  # can't be decoded at all
    player.playList([songs[0], track(bad, 9, codec="APE")], 0)
    connect(casting)
    assert wait_for(lambda: casting._analyser is not None, timeout=15)
    tries = []
    submit = casting._analyser.submit
    casting._analyser.submit = lambda *a, **k: (tries.append(a[0]), submit(*a, **k))[1]
    wait_for(lambda: False, timeout=5)  # (five seconds of the device reporting how it's doing)
    assert len(tries) <= 1
    casting._analyser.submit = submit
