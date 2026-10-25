"""The web interface and phone remote: off until switched on, only for paired devices, safe from other web pages,
and able to do what a remote should (and nothing more)."""
import http.client
import json
import socket
import threading

import pytest
from conftest import wait_for

from hallucinate import webserver
from hallucinate.api import Api, ApiError


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def remote(qapp, tmp_path, music):
    from PySide6.QtCore import QSettings

    from hallucinate.library import Library
    from hallucinate.player import Player
    from hallucinate.userlib import UserLibrary

    lib = Library(tmp_path / "lib.db", tmp_path / "art")
    lib.addFolder(str(music))
    assert wait_for(lambda: lib.trackCount >= 3 and not lib.scanning, timeout=10)
    player = Player()
    lib.setPlayer(player)
    user = UserLibrary(tmp_path / "lib.db", player)
    settings = QSettings("hallucinate", "hallucinate")
    settings.setValue("remote/port", free_port())
    settings.setValue("remote/lan", False)
    settings.setValue("remote/enabled", False)
    server = webserver.WebRemote(tmp_path / "data", tmp_path / "thumbs", player, lib, user)
    yield server, lib, player
    server.shutdown()
    settings.remove("remote")
    user.shutdown()
    player.shutdown()
    lib.shutdown()


def request(server, method, path, body=None, headers=None, host=None):
    """An HTTP request from another thread (the server runs commands on this one, so it must keep spinning)."""
    out = {}

    def go():
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
            h = {"Host": host or f"127.0.0.1:{server.port}", **(headers or {})}
            data = json.dumps(body).encode() if body is not None else None
            if data is not None:
                h.setdefault("Content-Type", "application/json")
            conn.request(method, path, body=data, headers=h)
            r = conn.getresponse()
            out["status"], out["headers"], out["body"] = r.status, dict(r.getheaders()), r.read()
            conn.close()
        except Exception as exc:  # noqa: BLE001
            out["error"] = exc

    t = threading.Thread(target=go)
    t.start()
    assert wait_for(lambda: not t.is_alive(), timeout=15)
    if "error" in out:
        raise out["error"]
    return out


def js(r):
    return json.loads(r["body"] or b"{}")


APP = {"X-Hallucinate": "1"}


def pair(server):
    code = server.new_code()
    r = request(server, "POST", "/api/pair", {"code": code, "name": "Test phone", "token": True}, APP)
    assert r["status"] == 200, r
    cookie = r["headers"]["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    return js(r)["key"]


def test_off_until_switched_on_and_only_on_this_computer_by_default(remote):
    server, *_ = remote
    assert not server.running
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", server.port), timeout=1)
    server.configure(enabled=True)
    assert server.running
    assert server._httpd.server_address[0] == "127.0.0.1"  # not on the network unless you allow it
    assert server.addresses() == [f"http://localhost:{server.port}/"]


def test_nothing_without_pairing_and_a_code_works_once(remote):
    server, *_ = remote
    server.configure(enabled=True)
    page = request(server, "GET", "/")
    assert page["status"] == 200 and b"Connect to Hallucinate" in page["body"]
    assert "default-src 'self'" in page["headers"]["Content-Security-Policy"]
    assert js(request(server, "GET", "/api/hello")) == {"app": "Hallucinate", "paired": False}
    assert request(server, "POST", "/api/call", {"method": "state"}, APP)["status"] == 401
    assert request(server, "GET", "/api/events")["status"] == 401
    assert request(server, "GET", "/art/x")["status"] == 401
    assert request(server, "POST", "/api/pair", {"code": "000000"}, APP)["status"] == 403  # no code made yet
    key = pair(server)
    auth = {**APP, "Authorization": f"Bearer {key}"}
    state = request(server, "POST", "/api/call", {"method": "state"}, auth)
    assert state["status"] == 200 and "playing" in js(state)["result"]
    cookie = {**APP, "Cookie": f"{webserver.COOKIE}={key}"}
    assert request(server, "POST", "/api/call", {"method": "state"}, cookie)["status"] == 200
    # the code was used up
    assert request(server, "POST", "/api/pair", {"code": "000000"}, APP)["status"] == 403
    devices = server.devices.listing()
    assert [d["name"] for d in devices] == ["Test phone"]
    assert key not in (server.devices._path.read_text())  # only a hash of the key is kept
    server.devices.remove(devices[0]["id"])
    assert request(server, "POST", "/api/call", {"method": "state"}, auth)["status"] == 401


def test_wrong_codes_end_the_code_and_attempts_are_limited(remote):
    server, *_ = remote
    server.configure(enabled=True)
    code = server.new_code()
    wrong = "111111" if code != "111111" else "222222"
    for _ in range(webserver.CODE_TRIES):
        assert request(server, "POST", "/api/pair", {"code": wrong}, APP)["status"] == 403
    assert request(server, "POST", "/api/pair", {"code": code}, APP)["status"] == 403  # too late: it's gone
    for _ in range(10):
        request(server, "POST", "/api/pair", {"code": wrong}, APP)
    assert request(server, "POST", "/api/pair", {"code": wrong}, APP)["status"] == 429


def test_other_web_pages_cant_use_it(remote):
    server, *_ = remote
    server.configure(enabled=True)
    key = pair(server)
    auth = {**APP, "Cookie": f"{webserver.COOKIE}={key}"}
    # a name that resolves to this computer from someone else's site ("DNS rebinding")
    assert request(server, "GET", "/", host="evil.example").get("status") == 421
    assert request(server, "POST", "/api/call", {"method": "toggle"}, auth, host="evil.example")["status"] == 421
    # a form or script on another site: no app header, or another origin
    no_header = {"Cookie": f"{webserver.COOKIE}={key}"}
    assert request(server, "POST", "/api/call", {"method": "toggle"}, no_header)["status"] == 403
    other = {**auth, "Origin": "http://evil.example"}
    assert request(server, "POST", "/api/call", {"method": "toggle"}, other)["status"] == 403
    big = {"method": "search", "params": {"query": "x" * (webserver.MAX_BODY + 10)}}
    assert request(server, "POST", "/api/call", big, auth)["status"] == 400
    assert request(server, "GET", "/../../etc/passwd")["status"] in (401, 404)
    assert request(server, "GET", "/hallucinate/api.py")["status"] in (401, 404)


def test_a_remote_can_browse_and_play_but_never_sees_paths(remote):
    server, lib, player = remote
    server.configure(enabled=True)
    key = pair(server)
    auth = {**APP, "Authorization": f"Bearer {key}"}

    def call(method, **params):
        r = request(server, "POST", "/api/call", {"method": method, "params": params}, auth)
        assert r["status"] == 200, r
        assert b"/Music/" not in r["body"] and b".mp3" not in r["body"]  # no file paths, ever
        return js(r)["result"]

    albums = call("albums")["albums"]
    northern = next(a for a in albums if a["title"] == "Northern Lights")
    album = call("album", key=northern["key"])
    assert [s["title"] for s in album["songs"]] == ["Echoes of Dawn", "Midnight Rain"]
    call("play.album", key=northern["key"], index=1)
    assert wait_for(lambda: player.hasTrack and player.current.get("title") == "Midnight Rain")
    assert call("state")["song"]["title"] == "Midnight Rain"
    found = call("search", query="midnight")
    assert [s["title"] for s in found["songs"]] == ["Midnight Rain"]
    lib.speller()  # made off the window's thread (the first search with no match starts it)
    assert wait_for(lambda: lib._speller is not None, timeout=10)
    assert call("search", query="midnigt")["corrected"] == "midnight"
    first = album["songs"][0]["id"]
    assert call("queue.add", ids=[first])["added"] == 1
    assert call("queue")["total"] == 3
    assert call("like", id=first)["liked"] is True
    from PySide6.QtGui import QColor, QImage

    cover = QImage(300, 300, QImage.Format.Format_RGB32)
    cover.fill(QColor("#8844cc"))
    cover_path = str(lib._db.conn.execute("SELECT art FROM tracks WHERE album_key=?", (northern["key"],)).fetchone()[0]
                     or "") or str(server.thumb_dir.parent / "cover.png")
    cover.save(cover_path, "PNG")
    lib._db.conn.execute("UPDATE tracks SET art=? WHERE album_key=?", (cover_path, northern["key"]))
    lib._db.commit()
    art = request(server, "GET", "/art/" + northern["key"].replace("|", "%7C") + "?s=128", headers=auth)
    assert art["status"] == 200 and art["headers"]["Content-Type"] == "image/jpeg" and art["body"][:2] == b"\xff\xd8"
    # not something a remote can do
    r = request(server, "POST", "/api/call", {"method": "_play"}, auth)
    assert r["status"] == 400


def test_live_updates_arrive_as_events(remote):
    server, lib, player = remote
    server.configure(enabled=True)
    key = pair(server)
    got = []

    def listen():
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
        conn.request("GET", "/api/events", headers={"Host": f"127.0.0.1:{server.port}", "Authorization": f"Bearer {key}"})
        r = conn.getresponse()
        while len(got) < 2:
            line = r.fp.readline()
            if not line:
                break
            if line.startswith(b"data: {") and b'"playing"' in line:
                got.append(json.loads(line[6:]))
        conn.close()

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    assert wait_for(lambda: len(got) >= 1, timeout=10)
    lib.playAlbum(lib.albums.get(0)["album_key"], 0)
    assert wait_for(lambda: len(got) >= 2 and got[-1]["song"], timeout=10)


def test_the_api_has_no_way_to_touch_files_or_settings():
    api = Api()
    names = set(api.methods)
    for word in ("delete", "remove.file", "trash", "tag", "setting", "folder", "path", "eval"):
        assert not any(word in n for n in names), (word, names)
    assert api.methods["state"] == "read" and api.methods["toggle"] == "control"
    with pytest.raises(ApiError):
        api.call("toggle", allowed=("read",))
    with pytest.raises(ApiError):
        api.call("art_file")  # helpers aren't commands


def test_a_browser_never_sees_its_key_and_a_removed_device_stops_hearing(remote):
    server, *_ = remote
    server.configure(enabled=True)
    code = server.new_code()
    r = request(server, "POST", "/api/pair", {"code": code, "name": "Browser"}, APP)
    assert r["status"] == 200 and "key" not in js(r)  # only in the HttpOnly cookie, away from scripts
    key = r["headers"]["Set-Cookie"].split(";")[0].split("=", 1)[1]
    ended = threading.Event()

    def listen():
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
        conn.request("GET", "/api/events", headers={"Host": f"127.0.0.1:{server.port}",
                                                    "Cookie": f"{webserver.COOKIE}={key}"})
        resp = conn.getresponse()
        while resp.fp.readline():
            pass
        conn.close()
        ended.set()

    threading.Thread(target=listen, daemon=True).start()
    assert wait_for(lambda: server._streams == 1, timeout=10)
    server.forgetAllDevices()
    assert wait_for(ended.is_set, timeout=10)


def test_requests_without_a_plain_length_are_refused(remote):
    server, *_ = remote
    server.configure(enabled=True)
    key = pair(server)
    out = {}

    def go():
        with socket.create_connection(("127.0.0.1", server.port), timeout=10) as s:
            s.sendall(f"POST /api/call HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\nX-Hallucinate: 1\r\n"
                      f"Authorization: Bearer {key}\r\nTransfer-Encoding: chunked\r\n\r\n"
                      "10\r\n{\"method\":\"next\"}\r\n0\r\n\r\n".encode())
            out["reply"] = s.recv(200)

    t = threading.Thread(target=go)
    t.start()
    assert wait_for(lambda: not t.is_alive(), timeout=15)
    assert out["reply"].startswith(b"HTTP/1.1 400")


def test_a_flood_of_connections_is_turned_away(remote):
    server, *_ = remote
    server.configure(enabled=True)
    held = [socket.create_connection(("127.0.0.1", server.port), timeout=5) for _ in range(webserver.MAX_CONNECTIONS)]
    try:
        extra = socket.create_connection(("127.0.0.1", server.port), timeout=5)
        extra.settimeout(5)
        assert extra.recv(10) == b""  # closed at once
        extra.close()
    finally:
        for s in held:
            s.close()
    assert wait_for(lambda: request(server, "GET", "/api/hello").get("status") == 200, timeout=10)


def test_odd_numbers_dont_reach_the_player(remote):
    server, _lib, player = remote
    api = server.api
    for bad in ("nan", "inf", float("nan")):
        with pytest.raises(ApiError):
            api.call("volume", {"volume": bad})
    api.call("volume", {"volume": 7})
    assert player.volume <= 1.0
