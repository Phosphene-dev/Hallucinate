"""Several speakers playing together: two stand-in AirPlay speakers start at the same moment and get the same sound
(and a pause and a play keep them together), a member dropping out leaves the others playing; and from the
player's side, against real ones where they're installed (two shairport-syncs and a Snapcast room)."""
import shutil
import socket
import struct
import subprocess
import time

import numpy as np
import pytest
from audio import FFMPEG, encode
from conftest import wait_for
from test_airplay import FakeSpeaker, plain, wav

from hallucinate.core.cast import airplay, group, snapcast


def first_sync_ntp(speaker, after=0):
    syncs = [d for d, _a in speaker.syncs[after:] if d[1] == 0xD4 and d[0] == 0x90]
    return struct.unpack("!Q", syncs[0][8:16])[0] / 2**32 if syncs else None


def test_speakers_start_together_and_get_the_same_sound(tmp_path, monkeypatch):
    monkeypatch.setattr(airplay, "LATENCY_FRAMES", 4410)
    fakes = [FakeSpeaker(), FakeSpeaker()]
    events = []
    g = group.GroupFeeder(on_event=lambda kind, tag, member=None: events.append((kind, tag, member)))
    speakers = []
    try:
        for i, f in enumerate(fakes):
            sp = airplay.Speaker("127.0.0.1", f.port, connect=plain)
            sp.connect()
            speakers.append(sp)
            g.add(f"Speaker {i}", sp)
        g.load(wav(tmp_path / "a.wav", 0.6, 1234), tag="a")
        assert wait_for_plain(lambda: ("ended", "a", None) in events, 5)
        assert events == [("ended", "a", None)]  # (the leader's, once)
        starts = [first_sync_ntp(f) for f in fakes]
        assert None not in starts and abs(starts[0] - starts[1]) < 0.015  # (the same moment, within a few ms)
        sounds = [[d[12:] for d, _a in f.audio] for f in fakes]
        assert sounds[0] == sounds[1] and len(sounds[0]) > 50
        # a pause and a play: they start again together
        n = [len(f.syncs) for f in fakes]
        g.load(wav(tmp_path / "b.wav", 3.0, 999), tag="b")
        time.sleep(0.6)
        g.pause()
        assert all(f.methods()[-1] == "FLUSH" for f in fakes)
        time.sleep(0.2)
        n = [len(f.syncs) for f in fakes]
        g.play()
        time.sleep(0.6)
        starts = [first_sync_ntp(f, k) for f, k in zip(fakes, n)]
        assert None not in starts and abs(starts[0] - starts[1]) < 0.015
        # one drops out: the other plays on
        fakes[1].conn.shutdown(socket.SHUT_RDWR)
        assert wait_for_plain(lambda: any(e[0] == "lost" for e in events), 3)
        assert ("lost", None, "Speaker 1") in events and [name for name, _f in g.members] == ["Speaker 0"]
    finally:
        g.close()
        for f in fakes:
            f.close()


def wait_for_plain(cond, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


# --- against real speakers ---------------------------------------------------------------------------------------
def _avahi():
    try:
        return subprocess.run(["avahi-daemon", "--check"], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


needs_real = pytest.mark.skipif(not (FFMPEG and shutil.which("shairport-sync") and _avahi()
                                     and shutil.which("snapserver") and shutil.which("snapclient")),
                                reason="needs ffmpeg, shairport-sync with avahi, snapserver and snapclient")


@pytest.fixture
def rooms(tmp_path):
    base = 16000 + (int(time.time() * 7) % 300) * 20
    procs, outs, ports = [], [], []
    for i in range(2):
        port = base + i * 10
        conf = tmp_path / f"sps{i}.conf"
        conf.write_text(f"general = {{ port = {port}; udp_port_base = {port + 1}; udp_port_range = 8; }};\n")
        out = tmp_path / f"air{i}.raw"
        with open(out, "wb") as sink:
            procs.append(subprocess.Popen(["shairport-sync", "-c", str(conf), "-a", f"G{port}", "-u", "-o", "stdout"],
                                          stdout=sink, stderr=subprocess.DEVNULL))
        outs.append(out)
        ports.append(port)
    snap_port = base + 40
    conf = tmp_path / "snapserver.conf"
    conf.write_text(f"[server]\ndatadir = {tmp_path}\n[stream]\nsource = pipe://{tmp_path}/fifo?name=default\n"
                    f"port = {snap_port + 1}\n[tcp]\nport = {snap_port}\n[http]\nenabled = false\n")
    procs.append(subprocess.Popen(["snapserver", "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(1.5)
    snap_out = tmp_path / "snap.raw"
    procs.append(subprocess.Popen(["snapclient", "-h", "127.0.0.1", "-p", str(snap_port + 1), "--player",
                                   f"file:filename={snap_out}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    ctl = snapcast.Control("127.0.0.1", snap_port, connect=plain)
    deadline = time.monotonic() + 10
    while not any(c["connected"] for g in snapcast.groups(ctl.status()) for c in g["clients"]):
        assert time.monotonic() < deadline
        time.sleep(0.2)
    for p in ports:
        deadline = time.monotonic() + 10
        while True:
            try:
                socket.create_connection(("127.0.0.1", p), 1).close()
                break
            except OSError:
                assert time.monotonic() < deadline
                time.sleep(0.2)
    yield ports, outs, snap_port, snap_out, ctl
    ctl.close()
    for p in procs:
        p.terminate()
        p.wait(5)


def loud(path, seconds=0.5, rate=44100):
    data = path.read_bytes() if path.exists() else b""
    a = np.frombuffer(data[-int(seconds * rate * 4):][: len(data[-int(seconds * rate * 4):]) // 4 * 4], "<i2")
    return int(np.abs(a).max()) if len(a) else 0


@needs_real
def test_the_queue_plays_on_speakers_together(qapp, tmp_path, rooms):
    from hallucinate.cast import Casting, GroupSession
    from hallucinate.player import Player

    ports, outs, snap_port, snap_out, ctl = rooms
    songs = [{"id": i, "path": str(encode(tmp_path / f"s{i}.flac", "flac", seconds=3.0, title=f"S{i}")),
              "title": f"T{i}", "artist": "A", "album": "B", "duration": 3.0, "artUrl": ""} for i in range(2)]
    player = Player(session_file=tmp_path / "session.json")
    casting = Casting(player)
    casting._server.port = 0
    casting.session_factories["group"] = lambda d, s: GroupSession(d, s, connect=plain)
    devices = [{"id": f"airplay:{p}", "kind": "airplay", "name": f"Speaker {p}", "model": "", "host": "127.0.0.1",
                "port": p} for p in ports]
    devices += list(snapcast.devices("127.0.0.1", snap_port, connect=plain).values())
    casting.discover = lambda servers: devices
    try:
        player.playList(songs, 0)
        player.pause()
        casting.refresh()
        assert wait_for(lambda: len(casting.devices) == 3, timeout=10)
        assert all(d["groupable"] for d in casting.devices)
        casting.castToGroup([d["id"] for d in casting.devices])
        assert wait_for(lambda: casting.active, timeout=20), casting.error
        assert casting.deviceKind == "group" and casting.deviceName.count(" + ") == 2
        assert all(d["active"] for d in casting.devices)
        player.setVolume(1.0)
        player.play()
        assert wait_for(lambda: all(loud(o) > 1000 for o in outs) and loud(snap_out, rate=44100) > 1000, timeout=12)
        assert wait_for(lambda: player.currentIndex == 1, timeout=10)  # straight on into the next, all together
        assert wait_for(lambda: not player.playing, timeout=12)
        casting.stopCasting()
        assert wait_for(lambda: snapcast.groups(ctl.status())[0]["stream"] == "default", timeout=10)
    finally:
        casting.shutdown()
        player.shutdown()
