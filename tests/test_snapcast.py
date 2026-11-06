"""Snapcast: the server's controls (JSON-RPC, answers it can't be trusted with), its rooms as cast devices, and the
stream: songs one after another with no gap, at the pace they're heard, pause and seek, and only the server
taking it. With snapserver and snapclient installed, a real server plays a song end to end."""
import array
import json
import math
import shutil
import socket
import socketserver
import subprocess
import threading
import time

import pytest

from hallucinate.core.cast import snapcast as sc

STATUS = {"server": {"host": {"name": "nas"}, "groups": [
    {"id": "g1", "name": "", "stream_id": "default", "clients": [
        {"id": "c1", "connected": True, "host": {"name": "kitchen"}, "config": {"name": "", "volume": {"percent": 40, "muted": False}}},
        {"id": "c2", "connected": True, "host": {"name": "hall"}, "config": {"name": "Hall", "volume": {"percent": 70, "muted": True}}}]},
    {"id": "g2", "name": "Garage", "stream_id": "default", "clients": [
        {"id": "c3", "connected": False, "host": {"name": "garage"}, "config": {}}]},
    "junk", {"no": "id"}], "streams": [{"id": "default"}]}}


class FakeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.calls = []
        super().__init__(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.serve_forever, daemon=True).start()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        for line in self.rfile:
            req = json.loads(line)
            self.server.calls.append((req["method"], req["params"]))
            self.wfile.write(b'{"jsonrpc":"2.0","method":"Client.OnVolumeChanged","params":{}}\n')  # (noise first)
            if req["method"] == "Server.GetStatus":
                out = {"id": req["id"], "jsonrpc": "2.0", "result": STATUS}
            elif req["method"] == "Broken":
                out = {"id": req["id"], "jsonrpc": "2.0", "error": {"code": -1, "message": "nope"}}
            elif req["method"] == "Huge":
                self.wfile.write(b"x" * (sc.MAX_LINE + 10))
                return
            else:
                out = {"id": req["id"], "jsonrpc": "2.0", "result": {"id": "Hallucinate"}}
            self.wfile.write(json.dumps(out).encode() + b"\n")


def plain(host, port, timeout):
    return socket.create_connection((host, port), timeout)


@pytest.fixture
def server():
    s = FakeServer()
    yield s
    s.shutdown()
    s.server_close()


def test_the_controls(server):
    ctl = sc.Control("127.0.0.1", server.server_address[1], connect=plain)
    try:
        assert ctl.call("Stream.AddStream", {"streamUri": "tcp://x"}) == {"id": "Hallucinate"}
        rooms = sc.groups(ctl.status())
        assert [r["name"] for r in rooms] == ["kitchen, Hall", "Garage"]
        assert rooms[0]["clients"][1] == {"id": "c2", "name": "Hall", "connected": True, "volume": 70, "muted": True}
        with pytest.raises(sc.SnapcastError, match="nope"):
            ctl.call("Broken")
        with pytest.raises(sc.SnapcastError):
            ctl.call("Huge")
    finally:
        ctl.close()


def test_rooms_with_speakers_on_become_devices(server):
    found = sc.devices("127.0.0.1", server.server_address[1], connect=plain)
    assert [d["name"] for d in found.values()] == ["kitchen, Hall"]  # (the garage's speaker is off)
    d = next(iter(found.values()))
    assert d["kind"] == "snapcast" and d["group"] == "g1" and d["model"] == "Snapcast · nas"


def test_the_server_must_be_on_this_network():
    with pytest.raises(OSError):
        sc.Control("8.8.8.8", 1705)  # (net.connect_local refuses an address out on the internet)


def tone(freq, channel, seconds):
    a = array.array("h")
    for i in range(int(sc.RATE * seconds)):
        v = int(8000 * math.sin(2 * math.pi * freq * i / sc.RATE))
        a.extend((v, 0) if channel == 0 else (0, v))
    return a.tobytes()


def read_for(conn, seconds):
    out, end = b"", time.monotonic() + seconds
    conn.settimeout(0.5)
    while time.monotonic() < end:
        try:
            more = conn.recv(65536)
        except socket.timeout:
            continue
        if not more:
            break
        out += more
    return out


def test_songs_play_one_after_another_at_the_pace_theyre_heard(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "SERVER_BUFFER_S", 0.1)
    sc.write_wav(str(tmp_path / "a.wav"), tone(440, 0, 0.5))
    sc.write_wav(str(tmp_path / "b.wav"), tone(880, 1, 0.5))
    events = []
    feeder = sc.Feeder("127.0.0.1", "127.0.0.1", on_event=lambda kind, tag: events.append((kind, tag)))
    try:
        feeder.load(str(tmp_path / "a.wav"), tag="A")
        feeder.queue_next(str(tmp_path / "b.wav"), tag="B")
        conn = socket.create_connection(("127.0.0.1", feeder.port))
        t0 = time.monotonic()
        data = read_for(conn, 1.6)
        took = time.monotonic() - t0
        conn.close()
        assert len(data) / sc.FRAME / sc.RATE <= took + sc.LEAD_S + 0.05  # (never far ahead of real time)
        a = array.array("h", data[: len(data) // 4 * 4])
        left, right = a[0::2], a[1::2]
        loud_l = [i for i, v in enumerate(left) if abs(v) > 4000]
        loud_r = [i for i, v in enumerate(right) if abs(v) > 4000]
        assert loud_l and loud_r and loud_l[0] < loud_r[0]
        gap = loud_r[0] - loud_l[-1]
        assert gap < sc.RATE * 0.002  # (straight on: no gap between the songs)
        time.sleep(0.6)
        assert events == [("advanced", "B"), ("ended", "B")]
    finally:
        feeder.close()


def test_pause_seek_and_who_may_take_the_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "SERVER_BUFFER_S", 0.0)
    sc.write_wav(str(tmp_path / "a.wav"), tone(440, 0, 3.0))
    feeder = sc.Feeder("127.0.0.1", "10.1.2.3")  # (only that address may take it)
    try:
        intruder = socket.create_connection(("127.0.0.1", feeder.port))
        assert read_for(intruder, 0.8) == b""  # (turned away)
        intruder.close()
    finally:
        feeder.close()
    feeder = sc.Feeder("127.0.0.1", "127.0.0.1")
    try:
        feeder.load(str(tmp_path / "a.wav"), tag="A", play=False)
        conn = socket.create_connection(("127.0.0.1", feeder.port))
        paused = read_for(conn, 0.5)
        assert paused and not any(paused)  # (paused: silence keeps the stream going)
        feeder.seek(2.0)
        feeder.play()
        playing = read_for(conn, 0.5)
        assert any(playing)
        tag, at = feeder.position()
        assert tag == "A" and 2.0 <= at <= 2.0 + 0.6
        conn.close()
    finally:
        feeder.close()


@pytest.mark.skipif(not (shutil.which("snapserver") and shutil.which("snapclient")), reason="needs snapserver and snapclient")
def test_a_real_snapcast_server_plays_it(tmp_path):
    conf = tmp_path / "snapserver.conf"
    port = 17050 + (int(time.time()) % 500)
    conf.write_text(f"[server]\ndatadir = {tmp_path}\n[stream]\nsource = pipe://{tmp_path}/fifo?name=default\n"
                    f"port = {port + 1}\n[tcp]\nport = {port}\n[http]\nenabled = false\n")
    out = tmp_path / "out.raw"
    server = subprocess.Popen(["snapserver", "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = None
    try:
        time.sleep(1.5)
        client = subprocess.Popen(["snapclient", "-h", "127.0.0.1", "-p", str(port + 1), "--player",
                                   f"file:filename={out}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        sc.write_wav(str(tmp_path / "a.wav"), tone(440, 0, 2.0))
        feeder = sc.Feeder("127.0.0.1", "127.0.0.1")
        ctl = sc.Control("127.0.0.1", port, connect=plain)
        sid = ctl.call("Stream.AddStream", {"streamUri": feeder.uri("127.0.0.1")})["id"]
        deadline = time.monotonic() + 10
        while not sc.groups(ctl.status()) and time.monotonic() < deadline:  # (the speaker joining)
            time.sleep(0.2)
        room = sc.groups(ctl.status())[0]
        ctl.call("Group.SetStream", {"id": room["id"], "stream_id": sid})
        assert feeder.connected.wait(10)
        time.sleep(1.0)
        before = out.stat().st_size if out.exists() else 0
        feeder.load(str(tmp_path / "a.wav"), tag="A")
        time.sleep(3.5)
        heard = array.array("h", out.read_bytes()[before:][: (out.stat().st_size - before) // 4 * 4])
        ctl.call("Group.SetStream", {"id": room["id"], "stream_id": room["stream"]})
        ctl.call("Stream.RemoveStream", {"id": sid})
        ctl.close()
        feeder.close()
        assert max(heard[0::2], default=0) > 7000 and max(heard[1::2], default=0) < 100  # (the left channel's tone)
    finally:
        for p in (client, server):
            if p is not None:
                p.terminate()
                p.wait(5)
