"""Handing what's playing from one computer to another: two whole Hallucinates (library, player, web remote) in
one process. A pairs with B using B's code, then hands over its queue; B plays the songs it has from its own
library and streams the one it hasn't from A, which pauses."""
import shutil

import pytest
from audio import FFMPEG, encode
from conftest import wait_for

pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")


class FakeKeyring:
    def __init__(self):
        self.kept = {}

    def set_password(self, service, key, value):
        self.kept[(service, key)] = value

    def get_password(self, service, key):
        return self.kept.get((service, key))

    def delete_password(self, service, key):
        self.kept.pop((service, key), None)


def free_port():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def two_computers(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    from hallucinate import handoff as handoff_mod
    from hallucinate.handoff import Handoff
    from hallucinate.library import Library
    from hallucinate.player import Player
    from hallucinate.webserver import WebRemote

    keyring = FakeKeyring()
    monkeypatch.setattr(handoff_mod, "_keyring", lambda: keyring)
    # the same songs in both libraries, except that B lacks "Only on A"
    shared = tmp_path / "shared"
    shared.mkdir()
    a_dir, b_dir = tmp_path / "A", tmp_path / "B"
    a_dir.mkdir()
    b_dir.mkdir()
    for name in ("Morning", "Evening"):
        f = encode(shared / f"{name}.flac", "flac", seconds=4.0, title=name, artist="The Band", album="Days")
        shutil.copy(f, a_dir / f.name)
        shutil.copy(f, b_dir / f.name)
    encode(a_dir / "only.flac", "flac", seconds=4.0, title="Only on A", artist="The Band", album="Days")

    made = []
    settings = QSettings("hallucinate", "hallucinate")

    def computer(name, folder, count):
        lib = Library(tmp_path / f"{name}.db", tmp_path / f"{name}-art")
        lib.addFolder(str(folder))
        assert wait_for(lambda: lib.trackCount >= count and not lib.scanning, timeout=20)
        player = Player()
        lib.setPlayer(player)
        settings.setValue("remote/enabled", False)
        remote = WebRemote(tmp_path / f"{name}-data", tmp_path / f"{name}-thumbs", player, lib, None)
        remote._settings = QSettings(str(tmp_path / f"{name}.ini"), QSettings.Format.IniFormat)  # (each its own)
        remote._settings.setValue("remote/port", free_port())
        remote.configure(enabled=True, lan=True)
        assert wait_for(lambda: remote.isRunning, timeout=5)
        h = Handoff(player, lib, remote)
        h._settings = remote._settings  # (each computer its own paired computers)
        h._peers = []
        h._id = f"computer-{name}-0000"
        remote.handoff = h
        made.append((lib, player, remote, h))
        return lib, player, remote, h

    a = computer("A", a_dir, 3)
    b = computer("B", b_dir, 2)
    yield a, b
    for lib, player, remote, h in made:
        h.shutdown()
        remote.shutdown()
        player.shutdown()
        lib.shutdown()
    settings.remove("remote")
    settings.remove("handoff")


def test_handing_a_queue_to_another_computer(two_computers):
    (a_lib, a_player, a_remote, a), (b_lib, b_player, b_remote, b) = two_computers
    songs = sorted(a_lib.allTracks(), key=lambda t: t["title"])  # Evening, Morning, Only on A
    a_player.playList(songs, 2)  # "Only on A" first: B doesn't have it, so it streams from A
    assert wait_for(lambda: a_player.state == "Playing" and a_player.position > 600, timeout=15)

    a.pair("127.0.0.1", b_remote.port, b_remote.new_code(), "B")
    assert wait_for(lambda: a.computers and a.computers[0]["paired"], timeout=15), a.error
    peer = a.computers[0]
    a.handTo(peer["id"])
    assert wait_for(lambda: b_player.hasTrack and b_player.state == "Playing", timeout=20), a.error
    assert wait_for(lambda: not a_player.playing, timeout=10)  # A paused once B took it
    assert b_player.currentIndex == 2 and b_player.current["title"] == "Only on A"
    assert b_player.current["path"].startswith(f"http://127.0.0.1:{a_remote.port}/h/")  # streamed from A
    assert wait_for(lambda: b_player.position > 1000, timeout=15)  # carried on from about where A was
    titles = [t["title"] for t in b_player.queue]
    assert titles == ["Evening", "Morning", "Only on A"]
    own = {t["path"] for t in b_lib.allTracks()}
    assert b_player.queue[0]["path"] in own and b_player.queue[1]["path"] in own  # its own copies
    b_player.previous()
    b_player.previous()  # back to Morning, B's own file
    assert wait_for(lambda: b_player.current["title"] in ("Morning", "Evening") and b_player.state == "Playing")


def test_streaming_only_from_the_computer_that_sent_it(two_computers):
    (a_lib, a_player, a_remote, a), (b_lib, b_player, b_remote, b) = two_computers
    payload = {"songs": [{"kind": "music", "title": "Nowhere", "artist": "X"}], "index": 0, "position": 0,
               "playing": True, "streamable": [True], "stream": "http://10.9.9.9:8483/h/" + "A" * 32 + "/"}
    from hallucinate.api import ApiError

    with pytest.raises(ApiError):
        b_remote.handoff_receive(payload, "127.0.0.1")  # the link points elsewhere: nothing to play
    assert not b_player.hasTrack


def test_a_handoff_link_only_serves_the_computer_it_was_made_for(two_computers):
    import http.client

    from hallucinate.core.handoff import HandoffLink

    (a_lib, a_player, a_remote, a), _b = two_computers
    path = a_lib.allTracks()[0]["path"]
    link = HandoffLink("127.0.0.2", [path])
    a._links[link.token] = link

    def get(source):
        c = http.client.HTTPConnection("127.0.0.1", a_remote.port, timeout=5, source_address=(source, 0))
        c.request("GET", f"/h/{link.token}/0", headers={"Host": f"127.0.0.1:{a_remote.port}"})
        r = c.getresponse()
        r.read()
        c.close()
        return r.status

    assert get("127.0.0.1") == 404  # not the computer it was handed to
    assert get("127.0.0.2") == 200
    link.revoke()
    assert get("127.0.0.2") == 404


def test_pairing_with_a_wrong_code_says_so(two_computers):
    (_al, _ap, _ar, a), (_bl, _bp, b_remote, _b) = two_computers
    b_remote.new_code()
    a.pair("127.0.0.1", b_remote.port, "000000", "B")
    assert wait_for(lambda: a.error, timeout=15)
    assert not any(c["paired"] for c in a.computers)
    a.pair("8.8.8.8", 8483, "123456", "elsewhere")
    assert "address" in a.error


def test_received_stations_are_only_internet_ones(two_computers):
    _a, (_bl, _bp, _br, b) = two_computers
    assert b._station_ok("https://stream.radio.example/live.mp3")
    assert b._station_ok("http://203.0.113.9:8000/stream") is False  # (a documentation range: not global)
    assert b._station_ok("http://8.8.8.8:8000/stream")
    for local in ("http://192.168.1.1/admin", "http://127.0.0.1:8483/api/call", "http://localhost:631/",
                  "http://router.local/", "http://[::1]:8000/", "http://10.0.0.5/x", "file:///etc/passwd"):
        assert not b._station_ok(local), local


def test_a_long_queue_is_cut_to_fit_and_keeps_the_playing_song(two_computers):
    (a_lib, a_player, _ar, a), _b = two_computers
    one = a_lib.allTracks()[0]
    queue = [dict(one, title=f"Song {i} " + "x" * 120, id=i) for i in range(5000)]
    a_player.playList(queue, 4000, autoplay=False)
    payload, paths = a._describe_queue()
    import json
    assert len(json.dumps(payload).encode()) < 64 * 1024
    assert payload["songs"][payload["index"]]["title"].startswith("Song 4000 ")
    assert len(payload["songs"]) == len(paths) == len(payload["streamable"]) > 100
