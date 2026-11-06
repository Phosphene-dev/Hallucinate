"""Libraries shared between computers: song links are signed and run out, the listing holds no paths (and leaves out
music servers' songs and CUE sheet songs), and against the real web server, a paired computer can list, play and
see covers only while sharing is on, while nothing unpaired or unsigned gets anything."""
import hashlib
import threading
import time

import pytest
from conftest import wait_for
from test_webremote import remote, request  # noqa: F401 - the fixture

from hallucinate.core import peerlib


def test_links_are_signed_and_run_out():
    secret = peerlib.key_secret("the-key")
    assert secret == hashlib.sha256(b"the-key").hexdigest()  # (what the sharing computer keeps)
    now = 1_000_000
    s = peerlib.sign(secret, "dev1", "a" * 24, now + 600)
    assert peerlib.check(secret, "dev1", "a" * 24, now + 600, s, now=now)
    assert not peerlib.check(secret, "dev2", "a" * 24, now + 600, s, now=now)  # (another device's)
    assert not peerlib.check(secret, "dev1", "b" * 24, now + 600, s, now=now)  # (another song)
    assert not peerlib.check(peerlib.key_secret("other"), "dev1", "a" * 24, now + 600, s, now=now)
    assert not peerlib.check(secret, "dev1", "a" * 24, now + 600, s, now=now + 601)  # (run out)
    far = now + peerlib.LINK_S * 10
    assert not peerlib.check(secret, "dev1", "a" * 24, far, peerlib.sign(secret, "dev1", "a" * 24, far), now=now)
    assert not peerlib.check(secret, "dev1", "a" * 24, "soon", s, now=now)
    server = peerlib.Server("http://192.168.1.5:8483", "the-key", "dev1")
    url = server.stream_url("c" * 24, now=now)
    assert "the-key" not in url and url.startswith("http://192.168.1.5:8483/lib/s/dev1/" + "c" * 24 + "?e=")


def test_the_listing_holds_no_paths_and_only_this_computers_own_songs(tmp_path):
    from hallucinate.core.db import Database

    db = Database(tmp_path / "lib.db")
    base = {"mtime": 1_700_000_000, "size": 10, "artist": "A", "album_artist": "A", "aa_tag": 1, "album": "B",
            "album_key": "a|b", "track_no": 1, "disc_no": 1, "year": 2020, "genre": "", "duration": 100.0,
            "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 44100}
    db.upsert_track(dict(base, path="/home/me/Music/secret-folder/one.flac", title="One"))
    db.upsert_track(dict(base, path="subsonic://abc/123", title="From a server"))
    db.upsert_track(dict(base, path="/home/me/Music/album.flac#2", title="CUE song", file="/home/me/Music/album.flac",
                         cue_start=60.0, cue_end=120.0))
    db.commit()
    page = peerlib.listing(db, 0, 50)
    assert page["total"] == 1 and [s["title"] for s in page["songs"]] == ["One"]
    song = page["songs"][0]
    assert "secret-folder" not in repr(song) and song["id"] == peerlib.song_id("/home/me/Music/secret-folder/one.flac")
    assert song["changed"].startswith("2023-11-14")
    index = peerlib.Index()
    assert index.path(db, song["id"]) == "/home/me/Music/secret-folder/one.flac"
    assert index.path(db, "f" * 24) is None
    parsed = peerlib._song(song)
    assert parsed["title"] == "One" and parsed["suffix"] == "flac"
    assert peerlib._song({"id": "../../etc"}) is None
    db.close()


def in_thread(fn):
    out = {}

    def go():
        try:
            out["v"] = fn()
        except Exception as exc:  # noqa: BLE001
            out["e"] = exc
    t = threading.Thread(target=go)
    t.start()
    assert wait_for(lambda: not t.is_alive(), timeout=20)
    if "e" in out:
        raise out["e"]
    return out["v"]


def test_a_paired_computer_lists_and_plays_the_shared_library(remote, music):  # noqa: F811
    from hallucinate.core import net

    server, lib, _player = remote
    server.configure(enabled=True)
    assert wait_for(lambda: server.running)
    key = server.devices.add("Laptop")
    peer = peerlib.Server(f"http://127.0.0.1:{server.port}", key)
    with pytest.raises(OSError):
        in_thread(peer.ping)  # (sharing is off until it's switched on)
    server.set_share_library(True)
    info = in_thread(peer.ping)
    assert info["songs"] == lib.trackCount and peer.device_id
    songs = [s for page in in_thread(lambda: list(peer.pages(page=2))) for s in page]
    assert len(songs) == lib.trackCount and all(len(s["id"]) == 24 for s in songs)
    assert not any(str(music) in repr(s) for s in songs)  # (no paths)
    url = peer.stream_url(songs[0]["id"])
    path = lib._db.conn.execute("SELECT path FROM tracks").fetchall()
    wanted = next(p[0] for p in path if peerlib.song_id(p[0]) == songs[0]["id"])

    def fetch(u, **h):
        import urllib.request

        req = urllib.request.Request(u, headers={"Host": f"127.0.0.1:{server.port}", **h})
        with net.urlopen(req, timeout=10) as resp:
            return resp.read()
    assert in_thread(lambda: fetch(url)) == open(wanted, "rb").read()
    import urllib.error

    tampered = url.replace("?e=", "?e=1").replace("&s=", "&s=0")
    with pytest.raises(urllib.error.HTTPError):
        in_thread(lambda: fetch(tampered))
    expired = peer.stream_url(songs[0]["id"], now=time.time() - peerlib.LINK_S - 10)
    with pytest.raises(urllib.error.HTTPError):
        in_thread(lambda: fetch(expired))
    stranger = peerlib.Server(f"http://127.0.0.1:{server.port}", "not-a-key")
    with pytest.raises(OSError):
        in_thread(stranger.ping)
    server.set_share_library(False)  # (switched off: even a signed link stops working)
    with pytest.raises(urllib.error.HTTPError):
        in_thread(lambda: fetch(url))
    assert request(server, "GET", "/lib/songs", headers={"Authorization": f"Bearer {key}"})["status"] == 403


def test_another_computers_library_joins_this_one(remote, tmp_path, monkeypatch):  # noqa: F811
    from PySide6.QtCore import QSettings
    from test_subsonic import FakeKeyring

    from hallucinate import servers as servers_mod
    from hallucinate.core import remote as remote_songs
    from hallucinate.core.db import Database

    server, lib, _player = remote
    server.configure(enabled=True)
    assert wait_for(lambda: server.running)
    server.set_share_library(True)
    key = server.devices.add("Laptop")

    class FakeHandoff:
        computers = [{"id": "peer1", "name": "Desk", "host": "127.0.0.1", "port": server.port, "paired": True}]

        def _read_key(self, peer_id):
            assert peer_id == "peer1"
            return key

    keyring = FakeKeyring()
    monkeypatch.setattr(servers_mod, "_keyring", lambda: keyring)
    settings = QSettings("hallucinate", "hallucinate")
    settings.remove("servers/list")
    (tmp_path / "other").mkdir()
    Database(tmp_path / "other" / "lib.db").close()
    svc = servers_mod.Servers(tmp_path / "other" / "lib.db", tmp_path / "other" / "art")
    svc.handoff = FakeHandoff()
    try:
        svc.setEnabled(True)
        svc.addComputer("peer1")
        assert wait_for(lambda: svc.servers and svc.servers[0]["songs"] == lib.trackCount, timeout=30), svc.servers
        entry = svc.servers[0]
        assert entry["kind"] == "hallucinate" and entry["name"] == "Desk"
        assert key not in str(settings.value("servers/list"))  # (the key is in the keyring only)
        db = Database(tmp_path / "other" / "lib.db")
        paths = [r[0] for r in db.conn.execute("SELECT path FROM tracks")]
        db.close()
        assert paths and all(p.startswith(f"hallucinate://{entry['id']}/") for p in paths)
        url = remote_songs.stream_url(paths[0])
        assert url.startswith(f"http://127.0.0.1:{server.port}/lib/s/") and key not in url
        svc.addComputer("peer1")  # (already added: nothing more)
        assert len(svc.servers) == 1
    finally:
        svc.setEnabled(False)
        svc.shutdown()
        settings.remove("servers/list")
