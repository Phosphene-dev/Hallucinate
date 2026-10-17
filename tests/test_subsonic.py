"""The Subsonic client: logging in without sending the password, reading every song a page at a time, and
treating what a server sends as data to check, not to trust."""
import hashlib
import http.server
import json
import os
import threading
import urllib.parse

import pytest

from hallucinate.core import subsonic


class FakeServer:
    """A tiny Subsonic server: `songs` are what it has; `seen` is every query it got."""

    def __init__(self, songs=(), password="secret", search_works=True, raw=None):
        self.songs, self.password, self.search_works, self.raw = list(songs), password, search_works, raw
        self.seen = []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                url = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(url.query))
                fake.seen.append((url.path, q))
                body = fake.answer(url.path.rsplit("/", 1)[-1], q)
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def ok(self, **inner):
        return {"subsonic-response": {"status": "ok", "version": "1.16.1", "type": "navidrome", **inner}}

    def answer(self, endpoint, q):
        if self.raw is not None:
            return self.raw
        expected = hashlib.md5((self.password + q.get("s", "")).encode(), usedforsecurity=False).hexdigest()
        if q.get("t") != expected or "p" in q:
            return {"subsonic-response": {"status": "failed", "error": {"code": 40, "message": "Wrong"}}}
        if endpoint == "ping":
            return self.ok(serverVersion="0.53")
        if endpoint == "search3":
            if not self.search_works:
                return self.ok(searchResult3={})
            off, n = int(q["songOffset"]), int(q["songCount"])
            return self.ok(searchResult3={"song": self.songs[off:off + n]})
        if endpoint == "getAlbumList2":
            albums = sorted({s["albumId"] for s in self.songs})
            off, n = int(q["offset"]), int(q["size"])
            return self.ok(albumList2={"album": [{"id": a} for a in albums[off:off + n]]})
        if endpoint == "getAlbum":
            return self.ok(album={"id": q["id"], "song": [s for s in self.songs if s["albumId"] == q["id"]]})
        if endpoint == "getCoverArt":
            return b"\xff\xd8\xff" + b"0" * 20
        return {"subsonic-response": {"status": "failed", "error": {"code": 70}}}

    def close(self):
        self.httpd.shutdown()


def song(i, album="A1", **extra):
    return {"id": f"s{i}", "title": f"Song {i}", "artist": "Artist", "album": "Album", "albumId": album,
            "track": i, "duration": 200, "suffix": "flac", "coverArt": f"al-{album}", **extra}


@pytest.fixture
def server():
    fake = FakeServer([song(i, album="A1" if i < 700 else "A2") for i in range(1, 1201)])
    yield fake
    fake.close()


def test_login_never_sends_the_password(server):
    s = subsonic.Server(server.base, "me", "secret")
    assert s.ping()["server_version"] == "0.53"
    path, q = server.seen[-1]
    assert "secret" not in json.dumps(q) and "p" not in q and len(q["s"]) == 16
    salts = {q["s"]}
    s.ping()
    assert server.seen[-1][1]["s"] not in salts  # a fresh salt every request


def test_a_wrong_password_says_so(server):
    with pytest.raises(subsonic.SubsonicError) as err:
        subsonic.Server(server.base, "me", "nope").ping()
    assert err.value.code == 40 and "password is wrong" in str(err.value)


def test_every_song_is_read_a_page_at_a_time(server):
    songs = list(subsonic.Server(server.base, "me", "secret").songs(page=500))
    assert [s["id"] for s in songs] == [f"s{i}" for i in range(1, 1201)]
    assert sum(1 for p, _ in server.seen if p.endswith("search3")) == 3


def test_servers_without_an_empty_search_are_read_album_by_album():
    fake = FakeServer([song(1, "A1"), song(2, "A1"), song(3, "A2")], search_works=False)
    try:
        ids = [s["id"] for s in subsonic.Server(fake.base, "me", "secret").songs()]
        assert sorted(ids) == ["s1", "s2", "s3"]
    finally:
        fake.close()


def test_what_a_server_sends_is_checked():
    assert subsonic.song_from({"id": "x", "isDir": True}) is None
    assert subsonic.song_from({"title": "no id"}) is None
    s = subsonic.song_from({"id": "x", "title": "t" * 5000, "track": "7", "year": -5, "duration": float("nan"),
                            "bitRate": True, "replayGain": {"trackGain": 999, "albumGain": -6.5}})
    assert len(s["title"]) == subsonic.MAX_TEXT and s["track_no"] == 7 and s["year"] == 0
    assert s["duration"] == 0 and s["bitrate"] == 0 and s["rg_track"] is None and s["rg_album"] == -6.5


def test_an_answer_that_isnt_subsonic_is_refused():
    fake = FakeServer(raw=b"<html>login page</html>")
    try:
        with pytest.raises(ValueError):
            subsonic.Server(fake.base, "me", "secret").ping()
    finally:
        fake.close()


def test_links_are_checked_and_tidied():
    assert subsonic.normalise_base("music.example.com/") == "https://music.example.com"
    assert subsonic.normalise_base("https://h.example/rest/") == "https://h.example"
    assert subsonic.normalise_base("nas.local:4533") == "https://nas.local:4533"
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "https://me:pw@h.example", ""):
        with pytest.raises(ValueError):
            subsonic.normalise_base(bad)
    assert subsonic.is_private_link("https://h.example")
    assert subsonic.is_private_link("http://192.168.1.5:4533") and subsonic.is_private_link("http://nas.local")
    assert not subsonic.is_private_link("http://music.example.com")


def test_offline_mode_stops_it(server):
    from hallucinate.core import net

    net.set_offline(True)
    try:
        with pytest.raises(net.OfflineError):
            subsonic.Server(server.base, "me", "secret").ping()
    finally:
        net.set_offline(False)


def test_covers_and_stream_links(server):
    s = subsonic.Server(server.base, "me", "secret")
    assert s.cover("al-A1")[:3] == b"\xff\xd8\xff"
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(s.stream_url("s5")).query))
    assert q["id"] == "s5" and q["format"] == "raw" and "secret" not in s.stream_url("s5")


# --- in the app: the Servers service and the player ----------------------------------------------------------

class FakeKeyring:
    def __init__(self):
        self.kept = {}

    def get_password(self, service, user):
        return self.kept.get((service, user))

    def set_password(self, service, user, password):
        self.kept[(service, user)] = password

    def delete_password(self, service, user):
        self.kept.pop((service, user), None)


@pytest.fixture
def service(qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    from hallucinate import servers as servers_mod
    from hallucinate.core.db import Database

    keyring = FakeKeyring()
    monkeypatch.setattr(servers_mod, "_keyring", lambda: keyring)
    settings = QSettings("hallucinate", "hallucinate")
    before = settings.value("servers/list")
    settings.remove("servers/list")
    Database(tmp_path / "lib.db").close()
    svc = servers_mod.Servers(tmp_path / "lib.db", tmp_path / "art")
    svc.keyring = keyring
    yield svc
    svc.setEnabled(False)
    svc.shutdown()
    settings.remove("servers/list") if before is None else settings.setValue("servers/list", before)


def _rows(tmp_path):
    from hallucinate.core.db import Database

    db = Database(tmp_path / "lib.db")
    try:
        return {r["path"]: r for r in db._rows("SELECT * FROM tracks")}
    finally:
        db.close()


def test_a_server_is_added_and_its_songs_join_the_library(service, server, tmp_path):
    from conftest import wait_for

    from hallucinate.core import remote

    service.setEnabled(True)
    service.addServer(server.base, "me", "secret", "Home")
    assert wait_for(lambda: service.servers and service.servers[0]["songs"] == 1200, timeout=30)
    entry = service.servers[0]
    assert entry["name"] == "Home" and entry["status"] == "ok"
    assert service.keyring.kept[("Hallucinate Music servers", entry["id"])] == "secret"
    from PySide6.QtCore import QSettings

    assert "secret" not in str(QSettings("hallucinate", "hallucinate").value("servers/list"))  # keyring only
    rows = _rows(tmp_path)
    song = rows[remote.make_path("subsonic", entry["id"], "s5")]
    assert song["title"] == "Song 5" and song["fmt"] == "FLAC" and song["art"] and os.path.isfile(song["art"])
    assert "secret" not in json.dumps(list(rows))  # no login in any path
    assert remote.available(song["path"]) and remote.stream_url(song["path"]).startswith(server.base)


def test_a_wrong_password_adds_nothing(service, server):
    from conftest import wait_for

    messages = []
    service.message.connect(messages.append)
    service.setEnabled(True)
    service.addServer(server.base, "me", "wrong", "")
    assert wait_for(lambda: messages, timeout=10)
    assert "password is wrong" in messages[-1] and service.servers == [] and service.keyring.kept == {}


def test_a_sync_follows_the_server_and_respects_what_you_removed(service, server, tmp_path):
    from conftest import wait_for

    from hallucinate.core import remote
    from hallucinate.core.db import Database

    service.setEnabled(True)
    service.addServer(server.base, "me", "secret", "")
    assert wait_for(lambda: service.servers and service.servers[0]["songs"] == 1200, timeout=30)
    sid = service.servers[0]["id"]
    db = Database(tmp_path / "lib.db")
    db.hide_paths([remote.make_path("subsonic", sid, "s7")])  # you removed it from the library
    db.commit()
    db.close()
    server.songs = server.songs[:100]  # the server lost most of its songs
    service.sync(sid)
    assert wait_for(lambda: service.servers[0]["songs"] == 99, timeout=30)
    paths = set(_rows(tmp_path))
    assert remote.make_path("subsonic", sid, "s7") not in paths and remote.make_path("subsonic", sid, "s50") in paths
    assert remote.make_path("subsonic", sid, "s500") not in paths


def test_switching_servers_off_takes_their_songs_out(service, server, tmp_path):
    from conftest import wait_for

    service.setEnabled(True)
    service.addServer(server.base, "me", "secret", "")
    assert wait_for(lambda: service.servers and service.servers[0]["songs"] == 1200, timeout=30)
    service.setEnabled(False)
    assert wait_for(lambda: not any("://" in p for p in _rows(tmp_path)), timeout=10)


def test_a_server_that_cant_be_reached_makes_its_songs_unavailable(service, server):
    from conftest import wait_for

    from hallucinate.core import remote
    from hallucinate.player import _playable

    service.setEnabled(True)
    service.addServer(server.base, "me", "secret", "")
    assert wait_for(lambda: service.servers and service.servers[0]["songs"] == 1200, timeout=30)
    path = remote.make_path("subsonic", service.servers[0]["id"], "s1")
    assert _playable(path)
    server.close()
    service.sync(service.servers[0]["id"])
    assert wait_for(lambda: service.servers[0]["status"] == "down", timeout=30)
    assert not _playable(path) and remote.stream_url(path) == ""


def test_server_songs_stay_out_of_trash_and_file_only_work(qapp, tmp_path):
    from hallucinate.core import remote, tagedit
    from hallucinate.core.db import Database
    from hallucinate.core.lyrics import read_embedded, sidecar_path
    from hallucinate.metaedit import save_folder_cover
    from hallucinate.servers import track_row

    row = track_row("1", subsonic.song_from(song(1)))
    db = Database(tmp_path / "lib.db")
    db.upsert_track(row)
    db.commit()
    with pytest.raises(tagedit.TagWriteError, match="music server"):
        tagedit.write_tags(row["path"], {"title": "x"})
    assert read_embedded(row["path"]) == "" and sidecar_path(row["path"]) is None
    assert save_folder_cover(db, row["album_key"], [row["path"]], b"\xff\xd8\xff" + b"0" * 20) == ""
    assert not (tmp_path / "subsonic:").exists()  # nothing written beside the working folder
    local = {**row, "path": str(tmp_path / "a.flac"), "fmt": "MP3"}
    assert remote.is_remote(row["path"]) and not remote.is_remote(local["path"])
    db.close()
