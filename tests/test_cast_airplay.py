"""Playing the queue on an AirPlay speaker, from the player's side, against a real one (shairport-sync, skipped
where it or the avahi daemon it announces itself through isn't there): the songs are heard, each goes straight
on into the next, the queue ends, and pause answers at once."""
import array
import shutil
import socket
import subprocess
import time

import pytest
from audio import FFMPEG, encode
from conftest import wait_for

from hallucinate.core.cast import airplay


def _avahi():
    try:
        return subprocess.run(["avahi-daemon", "--check"], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not (FFMPEG and shutil.which("shairport-sync") and _avahi()),
                                reason="needs ffmpeg, shairport-sync and a running avahi-daemon")


def plain(host, port, timeout):
    return socket.create_connection((host, port), timeout)


@pytest.fixture
def receiver(tmp_path):
    port = 15000 + (int(time.time() * 7) % 400) * 20
    conf = tmp_path / "sps.conf"
    conf.write_text(f"general = {{ port = {port}; udp_port_base = {port + 1}; udp_port_range = 10; }};\n")
    out = tmp_path / "speaker.raw"
    with open(out, "wb") as sink:
        proc = subprocess.Popen(["shairport-sync", "-c", str(conf), "-a", f"Test{port}", "-u", "-o", "stdout"],
                                stdout=sink, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 10
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), 1).close()
            break
        except OSError:
            assert time.monotonic() < deadline, "shairport-sync didn't start"
            time.sleep(0.2)
    yield port, out
    proc.terminate()
    proc.wait(5)


def heard(out, seconds=0.5):
    data = out.read_bytes() if out.exists() else b""
    data = data[-int(seconds * 44100 * 4):]
    a = array.array("h", data[: len(data) // 4 * 4])
    return max((abs(v) for v in a), default=0)


def test_the_queue_plays_on_an_airplay_speaker(qapp, tmp_path, receiver):
    from hallucinate.cast import AirplaySession, Casting
    from hallucinate.player import Player

    port, out = receiver
    songs = [{"id": i, "path": str(encode(tmp_path / f"s{i}.flac", "flac", seconds=2.0, title=f"S{i}")),
              "title": f"T{i}", "artist": "A", "album": "B", "duration": 2.0, "artUrl": ""} for i in range(3)]
    player = Player(session_file=tmp_path / "session.json")
    casting = Casting(player)
    casting._server.port = 0
    casting.session_factories["airplay"] = lambda d, s: AirplaySession(d, s, connect=plain)
    speaker = {"id": "airplay:TEST", "kind": "airplay", "name": "Test speaker", "model": "ShairportSync",
               "host": "127.0.0.1", "port": port}
    casting.discover = lambda servers: [speaker]
    try:
        player.playList(songs, 0)
        player.pause()
        casting.refresh()
        assert wait_for(lambda: casting.devices, timeout=10)
        casting.castTo(speaker["id"])
        assert wait_for(lambda: casting.active, timeout=15), casting.error
        assert casting.deviceKind == "airplay"
        assert player.volume == 0.5  # (a speaker can't be asked: half way the first time)
        player.setVolume(1.0)
        player.play()
        assert wait_for(lambda: player.playing, timeout=15), player.error
        assert wait_for(lambda: heard(out) > 2000, timeout=10), (player.state, player.position)
        assert wait_for(lambda: player.currentIndex == 1, timeout=10)  # straight on into the next
        assert wait_for(lambda: 300 < player.position < 1500, timeout=5), player.position  # (in step with it)
        player.pause()
        size = out.stat().st_size
        time.sleep(1.5)
        assert heard(out, 0.3) < 100 or out.stat().st_size == size  # quiet within a moment, not two seconds on
        player.play()
        assert wait_for(lambda: player.currentIndex == 2, timeout=10)
        assert wait_for(lambda: not player.playing, timeout=10)  # and the queue ends
        casting.stopCasting()
        assert wait_for(lambda: not casting.active, timeout=10)
        again = AirplaySession(speaker, None)
        assert again.volume == 1.0  # (remembered for next time)
        again.deleteLater()
    finally:
        casting.shutdown()
        player.shutdown()
    assert airplay.RATE == 44100
