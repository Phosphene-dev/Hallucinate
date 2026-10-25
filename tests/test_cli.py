"""The command line (`hallucinate cmd`), the terminal version's logic (`hallucinate tui`), the control socket's
web-remote commands, and running without a window (`hallucinate --headless`)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hallucinate import cli, tui
from hallucinate.control import ControlServer

ROOT = Path(__file__).resolve().parents[1]


class FakeApi:
    """Answers like the running app's API, and remembers what it was asked."""

    def __init__(self):
        self.calls = []
        self.state = {"playing": True, "song": {"id": 7, "title": "Blue in Green", "artist": "Miles Davis",
                                                "album": "Kind of Blue", "year": 1959, "liked": False, "rating": None},
                      "position": 61000, "duration": 337000, "volume": 0.5, "muted": False, "shuffle": False,
                      "repeat": 0, "radio": False, "index": 2, "queueLength": 5, "upcoming": 2,
                      "sleepRemaining": -1, "sleepAfterTrack": False, "sleepAfterAlbum": False, "error": ""}

    def __call__(self, method, **params):
        self.calls.append((method, params))
        if method == "state":
            return self.state
        if method == "search":
            return {"songs": [{"id": 9, "title": "So What", "artist": "Miles Davis", "album": "Kind of Blue",
                               "duration": 562}], "albums": [{"title": "Kind of Blue", "artist": "Miles Davis",
                                                                 "key": "miles|kind of blue", "year": 1959}],
                    "artists": [], "corrected": ""}
        if method == "queue":
            return {"index": 1, "total": 3, "songs": [{"id": i, "title": f"Song {i}", "artist": "A", "duration": 60,
                                                       "kind": "music"} for i in (1, 2, 3)]}
        if method == "album":
            return {"title": "Kind of Blue", "artist": "Miles Davis", "year": 1959,
                    "songs": [{"id": i, "title": f"Track {i}", "artist": "Miles Davis", "duration": 300}
                              for i in (11, 12)]}
        if method == "albums":
            return {"total": 1, "albums": [{"title": "Kind of Blue", "artist": "Miles Davis", "year": 1959,
                                            "key": "miles|kind of blue"}]}
        if method == "volume":
            v = params.get("volume", self.state["volume"] + params.get("change", 0))
            self.state["volume"] = max(0, min(1, v))
            return {"volume": self.state["volume"]}
        if method == "like":
            return {"liked": params.get("liked", True)}
        if method == "queue.add":
            return {"added": len(params["ids"])}
        if method == "repeat":
            return {"repeat": params.get("mode", 1)}
        if method == "queue.undo":
            return {"undone": True}
        return {"ok": True}


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(cli, "call", fake)
    return fake


def run(*argv):
    args = cli.parser().parse_args(list(argv))
    return cli.run(args)


def test_times_read_and_written_as_people_do():
    assert cli.parse_time("90") == 90_000
    assert cli.parse_time("1:30") == 90_000
    assert cli.parse_time("1:02:03") == 3_723_000
    for bad in ("abc", "1:2:3:4", "-5"):
        with pytest.raises(cli.CommandError):
            cli.parse_time(bad)
    assert cli.clock(61000) == "1:01" and cli.clock(3_723_000) == "1:02:03"


def test_status_says_what_is_playing(api):
    _, text = run("status")
    assert "Playing: Blue in Green" in text and "Miles Davis · Kind of Blue · 1959" in text
    assert "1:01 / 5:37" in text and "song 3 of 5" in text and "volume 50%" in text


def test_playback_commands_reach_the_app(api):
    run("next")
    run("prev")
    run("seek", "+30")
    assert ("seek", {"position": 91000}) in api.calls
    run("seek", "99:00")  # past the end: the end
    assert api.calls[-1] == ("seek", {"position": 337000})
    _, text = run("volume", "+10")
    assert text == "Volume 60%"
    run("volume", "20")
    assert api.calls[-1] == ("volume", {"volume": 0.2})
    run("repeat", "one")
    assert api.calls[-1] == ("repeat", {"mode": 2})
    run("sleep", "album")
    assert api.calls[-1] == ("sleep", {"end": "album"})


def test_play_by_name_and_queue_by_id(api):
    _, text = run("play-album", "kind", "of", "blue", "--shuffle")
    assert ("play.album", {"key": "miles|kind of blue", "shuffle": True}) in api.calls
    assert text.startswith("Playing Blue in Green")
    _, text = run("add", "9", "12", "--next")
    assert ("queue.add", {"ids": [9, 12], "next": True}) in api.calls
    run("queue", "move", "5", "2")  # numbered from 1 for people
    assert api.calls[-1] == ("queue.move", {"src": 4, "dst": 1})
    run("like")  # the playing song
    assert api.calls[-1] == ("like", {"id": 7, "liked": True})
    _, text = run("search", "so", "what")
    assert "[9] So What — Miles Davis" in text


def test_no_running_app_is_explained(monkeypatch, capsys):
    monkeypatch.setattr(cli, "send_control", lambda *a, **k: None)
    assert cli.main(["status"]) == 1
    assert "isn't running" in capsys.readouterr().err


# --- the terminal version ---------------------------------------------------------------------------------------
def test_text_fits_the_terminal_wide_characters_too():
    assert tui.fit("abc", 5) == "abc  "
    assert tui.fit("abcdef", 4) == "abc…"
    assert tui.width(tui.fit("日本語の歌のタイトル", 9)) == 9
    assert "\x1b" not in tui.fit("evil\x1b[31mred", 20)  # no escape codes from a tag


def test_terminal_browsing_and_playing():
    api = FakeApi()
    b = tui.Browser(api)
    assert b.poll()
    b.show("queue")
    assert [r.text for r in b.rows][1].startswith("Song 2") and b.rows[1].current and b.cursor == 1
    b.key("KEY_DOWN")
    b.key("\n")
    assert api.calls[-1] == ("queue.jump", {"index": 2})
    b.key("2")  # albums
    assert b.view == "albums" and b.rows[0].text.startswith("Kind of Blue")
    b.key("\n")  # open it
    assert b.view == "album" and [r.song_id for r in b.rows] == [11, 12]
    b.key("KEY_DOWN")
    b.key("\n")
    assert api.calls[-1] == ("play.album", {"key": "miles|kind of blue", "index": 1})
    b.key("A")
    assert api.calls[-1] == ("queue.add", {"ids": [12], "next": True})
    b.key("KEY_BACKSPACE")
    assert b.view == "albums"
    b.search("so what")
    assert any(r.song_id == 9 for r in b.rows)
    b.key("+")
    assert api.calls[-1] == ("volume", {"change": 0.05})
    b.key("KEY_RIGHT")
    assert api.calls[-1] == ("seek", {"position": 71000})
    b.key("l")
    assert api.calls[-1] == ("like", {"id": 7})
    b.key("?")
    assert b.help
    assert b.key("x") and not b.help  # any key closes the help
    assert b.key("q") is False


# --- the control socket ----------------------------------------------------------------------------------------
class FakeWeb:
    def __init__(self):
        self.enabled, self.lan, self.port, self.running, self.error = True, False, 8483, True, ""
        self.names = []
        self.forgot = []
        self.devices = type("D", (), {"listing": lambda s: [{"id": "abc", "name": "Phone"}]})()

    def new_code(self):
        return "123456"

    def addresses(self):
        return ["http://localhost:8483/"]

    def configure(self, enabled=None, lan=None, port=None):
        self.lan = self.lan if lan is None else lan
        self.port = self.port if port is None else port

    def extra_host_names(self):
        return self.names

    def set_host_names(self, names):
        self.names = names

    def forgetDevice(self, device_id):  # noqa: N802
        self.forgot.append(device_id)

    def forgetAllDevices(self):  # noqa: N802
        self.forgot.append("all")

    def _soon(self):
        pass


def test_control_socket_carries_the_remote_commands(qapp):
    from hallucinate.api import Api

    server = ControlServer(server_name="hallucinate-test-unused")
    assert server._dispatch("api", {"method": "state"})["error"] == "Hallucinate is still starting"
    server.setApi(Api())
    assert "isn't ready" in server._dispatch("api", {"method": "toggle"})["error"]
    assert server._dispatch("api", {"method": "nope"}) == {"ok": False, "error": "No such command"}
    web = FakeWeb()
    server.setWebRemote(web)
    assert server._dispatch("pair", {})["code"] == "123456"
    r = server._dispatch("remote", {"lan": True, "port": 9000, "hostNames": ["Music.Example.LAN"]})["remote"]
    assert r["lan"] and r["port"] == 9000 and r["hostNames"] == ["music.example.lan"]
    assert not server._dispatch("remote", {"port": 80})["ok"]
    assert not server._dispatch("remote", {"hostNames": ["bad name/../"]})["ok"]
    assert not server._dispatch("remote", {"forget": "nobody"})["ok"]
    server._dispatch("remote", {"forget": "abc"})
    assert web.forgot == ["abc"]
    web.running = False
    assert "off" in server._dispatch("pair", {})["error"]


# --- without a window --------------------------------------------------------------------------------------------
def test_headless_starts_plays_its_part_and_stops(tmp_path):
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "c"), "XDG_DATA_HOME": str(tmp_path / "d"),
           "XDG_CACHE_HOME": str(tmp_path / "x"), "HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen",
           "HALLUCINATE_CONTROL_SOCKET": str(tmp_path / "ctl"), "HALLUCINATE_DISABLE_LEGACY_MIGRATION": "1",
           "PYTHONPATH": str(ROOT)}
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    proc = subprocess.run([sys.executable, "-m", "hallucinate", "--headless", "--port", "18999", "--quit-after", "6000",
                           str(ROOT / "packaging" / "testclips")], env=env, capture_output=True, text=True,
                          timeout=90, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = proc.stdout
    assert "running without a window" in out and "http://localhost:18999/" in out and "Stopping" in out
    assert (tmp_path / "d" / "hallucinate" / "library.db").exists()
