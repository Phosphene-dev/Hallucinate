"""Playing the queue on a Snapcast server's room, from the player's side, against a real snapserver and snapclient
(skipped where they aren't installed): the songs are heard, each goes straight on into the next, the queue ends,
the room's volume follows, and stopping puts the room back on what it was playing."""
import array
import shutil
import subprocess
import time

import pytest
from audio import FFMPEG, encode
from conftest import wait_for

from hallucinate.core.cast import snapcast

needs_snapserver = pytest.mark.skipif(not (FFMPEG and shutil.which("snapserver") and shutil.which("snapclient")),
                                      reason="needs ffmpeg, snapserver and snapclient")


def plain(host, port, timeout):
    import socket

    return socket.create_connection((host, port), timeout)


@pytest.fixture
def snapserver(tmp_path):
    port = 18050 + (int(time.time() * 7) % 400) * 2
    conf = tmp_path / "snapserver.conf"
    conf.write_text(f"[server]\ndatadir = {tmp_path}\n[stream]\nsource = pipe://{tmp_path}/fifo?name=default\n"
                    f"port = {port + 1}\n[tcp]\nport = {port}\n[http]\nenabled = false\n")
    out = tmp_path / "speaker.raw"
    server = subprocess.Popen(["snapserver", "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    client = subprocess.Popen(["snapclient", "-h", "127.0.0.1", "-p", str(port + 1), "--player", f"file:filename={out}"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ctl = snapcast.Control("127.0.0.1", port, connect=plain)
    deadline = time.monotonic() + 10
    while not any(c["connected"] for g in snapcast.groups(ctl.status()) for c in g["clients"]):
        assert time.monotonic() < deadline, "the speaker didn't join"
        time.sleep(0.2)
    yield port, ctl, out
    ctl.close()
    for p in (client, server):
        p.terminate()
        p.wait(5)


def heard(out, seconds=1.0):
    """The loudest sample the speaker played in its last `seconds` (its file is written afresh when the room
    changes stream, so it's the end of it that counts)."""
    data = out.read_bytes() if out.exists() else b""
    data = data[-int(seconds * 48000 * 4):]
    a = array.array("h", data[: len(data) // 4 * 4])
    return max((abs(v) for v in a), default=0)


@needs_snapserver
def test_the_queue_plays_on_a_snapcast_room(qapp, tmp_path, snapserver, monkeypatch):
    from hallucinate.cast import Casting, SnapcastSession
    from hallucinate.player import Player

    monkeypatch.setattr(snapcast, "SERVER_BUFFER_S", 0.3)
    port, ctl, out = snapserver
    songs = [{"id": i, "path": str(encode(tmp_path / f"s{i}.flac", "flac", seconds=2.0, title=f"S{i}")),
              "title": f"T{i}", "artist": "A", "album": "B", "duration": 2.0, "artUrl": ""} for i in range(3)]
    player = Player(session_file=tmp_path / "session.json")
    casting = Casting(player)
    casting._server.port = 0
    casting.session_factories["snapcast"] = lambda d, s: SnapcastSession(d, s, connect=plain)
    casting.discover = lambda servers: list(snapcast.devices("127.0.0.1", port, connect=plain).values())
    try:
        player.playList(songs, 0)
        player.pause()
        casting.refresh()
        assert wait_for(lambda: casting.devices, timeout=10)
        room = casting.devices[0]
        assert room["kind"] == "snapcast"
        casting.castTo(room["id"])
        assert wait_for(lambda: casting.active, timeout=15), casting.error
        assert casting.deviceKind == "snapcast"
        assert any(s["id"] == snapcast.STREAM_NAME for s in ctl.status()["streams"])
        player.play()
        assert wait_for(lambda: player.playing, timeout=15), player.error
        assert wait_for(lambda: heard(out) > 2000, timeout=10), (out.stat().st_size, player.state, player.position)
        player.setVolume(0.3)
        assert wait_for(lambda: snapcast.groups(ctl.status())[0]["clients"][0]["volume"] == 30, timeout=5)
        assert wait_for(lambda: player.currentIndex == 1, timeout=10)  # straight on into the next
        assert wait_for(lambda: player.currentIndex == 2, timeout=10)
        assert wait_for(lambda: not player.playing, timeout=10)  # and the queue ends
        casting.stopCasting()
        assert wait_for(lambda: snapcast.groups(ctl.status())[0]["stream"] == "default", timeout=10)
        assert wait_for(lambda: not any(s["id"] == snapcast.STREAM_NAME for s in ctl.status()["streams"]), timeout=10)
    finally:
        casting.shutdown()
        player.shutdown()


def test_typed_snapcast_servers_are_kept_tidy(qapp, tmp_path):
    from hallucinate.cast import Casting
    from hallucinate.player import Player

    player = Player(session_file=tmp_path / "session.json")
    casting = Casting(player)
    try:
        casting.setSnapcastServers("192.168.1.20, snap.local:1705  http://x/y  ;rm  host:99999x " + " h".join("abcdefghij"))
        kept = casting.snapcastServers.split()
        assert kept[:2] == ["192.168.1.20", "snap.local:1705"]
        assert not any("/" in s or ";" in s or "99999x" in s for s in kept)
        assert len(kept) <= 8
        seen = []
        casting.discover = lambda servers: seen.append(servers) or []
        casting.refresh()
        assert wait_for(lambda: seen, timeout=5)
        assert seen[0][:2] == ["192.168.1.20", "snap.local:1705"]
    finally:
        casting.shutdown()
        player.shutdown()
