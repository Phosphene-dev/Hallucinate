"""The Subsonic client: logging in without sending the password, reading every song a page at a time, and
treating what a server sends as data to check, not to trust."""
import hashlib
import http.server
import json
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
