import hashlib
import json
import time
from urllib.parse import parse_qs

import pytest
from conftest import wait_for
from PySide6.QtCore import QObject, Signal

import hallucinate.scrobbling as scrobbling


class FakePlayer(QObject):
    trackChanged = Signal()
    stateChanged = Signal()
    positionChanged = Signal()
    seeked = Signal(int)

    def __init__(self):
        super().__init__()
        self.current = {}
        self.position = 0
        self.duration = 0
        self.playing = False

    def set_track(self, track, duration_ms, playing=True):
        self.current = dict(track)
        self.duration = duration_ms
        self.position = 0
        self.playing = playing
        self.trackChanged.emit()
        self.stateChanged.emit()

    def advance(self, ms):
        self.position += ms
        self.positionChanged.emit()

    def set_playing(self, playing):
        self.playing = playing
        self.stateChanged.emit()

    def seek(self, ms):
        self.position = ms
        self.seeked.emit(ms)


@pytest.fixture
def memory_keyring(monkeypatch):
    store = {}
    monkeypatch.setattr(scrobbling.keyring, "get_password", lambda service, name: store.get(name))
    monkeypatch.setattr(scrobbling.keyring, "set_password", lambda service, name, value: store.__setitem__(name, value))
    monkeypatch.setattr(scrobbling.keyring, "delete_password", lambda service, name: store.pop(name, None))
    return store


@pytest.fixture
def make_scrobbler(qapp, tmp_path, memory_keyring, monkeypatch):
    monkeypatch.delenv("HALLUCINATE_LASTFM_API_KEY", raising=False)
    monkeypatch.delenv("HALLUCINATE_LASTFM_API_SECRET", raising=False)
    player = FakePlayer()
    instances = []

    def make():
        result = scrobbling.LastFmScrobbler(player, tmp_path)
        instances.append(result)
        return result

    yield player, make
    for result in instances:
        result.shutdown()


def test_api_signature_is_sorted_and_excludes_format():
    values = {"z": "last", "api_key": "key", "method": "test", "a": "first", "format": "json"}
    expected = hashlib.md5(b"afirstapi_keykeymethodtestzlastsecret").hexdigest()
    assert scrobbling.api_signature(values, "secret") == expected


def test_api_request_posts_signed_utf8_form(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(scrobbling.net, "urlopen", fake_urlopen)
    assert scrobbling.api_request(
        "track.updateNowPlaying", {"track": "Café", "artist": "Björk"},
        "public-key", "private-secret", "session",
    ) == {"ok": True}
    req = captured["request"]
    values = parse_qs(req.data.decode())
    assert values["track"] == ["Café"]
    assert values["sk"] == ["session"] and values["format"] == ["json"]
    fields = {k: values[k][0] for k in values if k not in {"format", "api_sig"}}
    assert values["api_sig"] == [scrobbling.api_signature(fields, "private-secret")]
    assert captured["timeout"] == 15


def test_api_errors_are_not_success_shaped(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"error": 9, "message": "Invalid session key"}'

    monkeypatch.setattr(scrobbling.net, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(RuntimeError, match="Invalid session key"):
        scrobbling.api_request("track.scrobble", {}, "key", "secret", "bad-session")


@pytest.mark.parametrize(
    "duration,expected",
    [(30_000, 15_000), (240_000, 120_000), (600_000, 240_000), (0, 240_000)],
)
def test_lastfm_scrobble_threshold(duration, expected):
    assert scrobbling.scrobble_threshold(duration) == expected


def test_auth_flow_stores_session_only_in_keyring(make_scrobbler, monkeypatch):
    import hallucinate.scrobbling as module

    _player, make = make_scrobbler
    calls = []

    def fake_api(method, *_args, **_kwargs):
        calls.append(method)
        if method == "auth.getToken":
            return {"token": "a-token"}
        if method == "auth.getSession":
            return {"session": {"key": "secure-session", "name": "Ada"}}
        raise AssertionError(method)

    monkeypatch.setattr(module, "api_request", fake_api)
    s = make()
    s.setApiCredentials("app-key", "app-secret")
    assert wait_for(lambda: s.configured, timeout=4)  # once the keyring has them
    s.connectAccount()
    assert wait_for(lambda: s.authorizationUrl != "", timeout=4)
    assert "a-token" in s.authorizationUrl and s.status.startswith("Authorize")
    s.completeAuthorization()
    assert wait_for(lambda: s.connected, timeout=4)
    assert s.status == "Connected to Last.fm as Ada."
    assert scrobbling.keyring.get_password(scrobbling.KEYRING_SERVICE, "session") == "secure-session"
    s.disconnectAccount()
    assert not s.connected
    assert wait_for(lambda: scrobbling.keyring.get_password(scrobbling.KEYRING_SERVICE, "session") is None)
    assert calls == ["auth.getToken", "auth.getSession"]


def test_missing_credentials_are_explained(make_scrobbler):
    _player, make = make_scrobbler
    s = make()
    s.connectAccount()
    assert not s.busy
    assert "API key and secret" in s.status


def test_nowplaying_and_scrobble_at_listen_threshold(make_scrobbler, memory_keyring, monkeypatch):
    player, make = make_scrobbler
    memory_keyring["session"] = "session"
    calls = []

    def fake_api(method, fields, *_args, **_kwargs):
        calls.append((method, dict(fields)))
        if method == "track.scrobble":
            return {"scrobbles": {"@attr": {"accepted": "1"}}}
        return {"nowplaying": {}}

    monkeypatch.setattr(scrobbling, "api_request", fake_api)
    s = make()
    player.set_track(
        {"path": "/music/song.flac", "title": "Song", "artist": "Artist", "album": "Album", "track_no": 4},
        60_000,
    )
    assert wait_for(lambda: any(m == "track.updateNowPlaying" for m, _ in calls))

    player.advance(1500)
    s._last_tick = time.monotonic() - 1.1
    s._last_position = 0
    s._tick()
    assert s._listened_ms >= 1000
    assert s.pendingCount == 0

    s._listened_ms = 29_500  # most of the 30 s that count for a one-minute track
    player.advance(1500)
    s._last_tick = time.monotonic() - 1.1
    s._last_position = 1500
    s._tick()
    assert wait_for(lambda: s.pendingCount == 0 and any(m == "track.scrobble" for m, _ in calls))
    sent = [fields for method, fields in calls if method == "track.scrobble"]
    assert sent[0]["track"] == "Song" and sent[0]["artist"] == "Artist"
    assert sent[0]["trackNumber"] == 4 and sent[0]["timestamp"] > 0


def test_pauses_and_seeks_do_not_count_as_listened_time(make_scrobbler, memory_keyring, monkeypatch):
    player, make = make_scrobbler
    memory_keyring["session"] = "session"
    monkeypatch.setattr(scrobbling, "api_request", lambda *_a, **_k: {"nowplaying": {}})
    s = make()
    player.set_track({"path": "/song", "title": "Song", "artist": "Artist"}, 10_000)
    player.set_playing(False)
    s._listened_ms = 4000
    s._last_tick = time.monotonic() - 2
    player.advance(9000)
    s._tick()
    assert s._listened_ms == 4000
    player.seek(1000)
    assert s._last_position == 1000


def test_failed_scrobbles_remain_queued_and_retry(make_scrobbler, memory_keyring, monkeypatch, tmp_path):
    _player, make = make_scrobbler
    memory_keyring["session"] = "session"
    calls = []

    def flaky_api(method, *_args, **_kwargs):
        calls.append(method)
        if len(calls) == 1:
            raise RuntimeError("offline")
        return {"scrobbles": {"@attr": {"accepted": "1"}}}

    monkeypatch.setattr(scrobbling, "api_request", flaky_api)
    s = make()
    s._queue_scrobble({"title": "Offline", "artist": "Artist", "album": "Album"}, 1234)
    assert wait_for(lambda: "offline" in s.status.lower(), timeout=4)
    assert s.pendingCount == 1
    assert json.loads((tmp_path / "lastfm-scrobbles.json").read_text())[0]["track"] == "Offline"

    s._retry_at = 0
    s._send_pending()
    assert wait_for(lambda: s.pendingCount == 0, timeout=4)
    assert json.loads((tmp_path / "lastfm-scrobbles.json").read_text()) == []


def test_offline_queue_survives_restart(make_scrobbler, memory_keyring, monkeypatch, tmp_path):
    _player, make = make_scrobbler
    memory_keyring["session"] = "session"
    monkeypatch.setattr(scrobbling, "api_request", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("offline")))
    first = make()
    first._queue_scrobble({"title": "Queued", "artist": "Artist"}, 456)
    assert wait_for(lambda: "offline" in first.status.lower(), timeout=4)
    first.shutdown()
    second = make()
    assert second.pendingCount == 1
    assert second._pending[0]["timestamp"] == 456


def test_api_credentials_and_session_never_enter_queue_file(make_scrobbler, memory_keyring, tmp_path):
    _player, make = make_scrobbler
    s = make()
    s.setApiCredentials("secret-app-key", "secret-app-secret")
    assert wait_for(lambda: s.configured)
    s._queue_scrobble({"title": "Song", "artist": "Artist"}, 1)
    content = (tmp_path / "lastfm-scrobbles.json").read_text()
    assert "secret-app" not in content and "session" not in content


def test_loves_follow_likes_and_come_back_as_likes(make_scrobbler, memory_keyring, monkeypatch, qapp, tmp_path):
    memory_keyring.update(api_key="k", api_secret="s", session="sk")
    calls = []

    def fake(method, params, *args, **kwargs):
        calls.append((method, dict(params)))
        if method == "user.getInfo":
            return {"user": {"name": "me"}}
        if method == "user.getLovedTracks":
            return {"lovedtracks": {"track": [{"name": "Song A", "artist": {"name": "Band"}}],
                                    "@attr": {"totalPages": "1"}}}
        return {}

    monkeypatch.setattr(scrobbling, "api_request", fake)
    _player, make = make_scrobbler
    s = make()
    s.love([("Band", "Song A")], True)  # sync is off: nothing goes out
    assert not calls
    s.setSyncLoves(True)
    s.love([("Band", "Song A")], True)
    s.love([("Band", "Song A")], False)
    assert wait_for(lambda: [c[0] for c in calls] == ["track.love", "track.unlove"])
    got = []
    s.lovesImported.connect(got.append)
    s.importLoves()
    assert wait_for(lambda: got)
    assert got[0] == [("Band", "Song A")]
    s.setSyncLoves(False)

    # the library likes what matches
    from hallucinate.core.db import Database
    from hallucinate.userlib import UserLibrary

    db = Database(tmp_path / "lib.db")
    db.upsert_track({"path": "/m/a.flac", "mtime": 0, "size": 1, "title": "Song A", "artist": "Band",
                     "album_artist": "Band", "aa_tag": 1, "album": "X", "album_key": "x", "track_no": 1, "disc_no": 0,
                     "year": 0, "genre": "", "duration": 100.0, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0,
                     "sample_rate": 0})
    db.commit()
    db.close()
    user = UserLibrary(tmp_path / "lib.db", None)
    announced, matched = [], []
    user.likeChanged.connect(lambda pairs, liked: announced.append((pairs, liked)))
    user.lovesMatched.connect(matched.append)
    user.likeLoved([("band", "song a")])
    assert wait_for(lambda: matched == [1])
    assert user.isLiked("/m/a.flac") and not announced  # loved already: not sent back
    user.toggleLike("/m/a.flac")
    assert wait_for(lambda: announced == [([("Band", "Song A")], False)])
    user.shutdown()


def _queue(s, n):
    s._pending = [{"artist": f"Artist {i}", "track": f"Song {i}", "timestamp": 1000 + i} for i in range(n)]
    s._save_queue()


def test_scrobbles_go_in_batches_and_ignored_ones_are_dropped(make_scrobbler, memory_keyring, monkeypatch):
    _player, make = make_scrobbler
    memory_keyring["session"] = "session"
    sent = []

    def fake_api(method, fields, *_args, **_kwargs):
        sent.append(dict(fields))
        n = sum(1 for k in fields if k.startswith("artist["))
        items = [{"ignoredMessage": {"code": "1" if i == 1 else "0", "#text": ""}} for i in range(n)]
        return {"scrobbles": {"@attr": {"accepted": n - 1, "ignored": 1}, "scrobble": items}}

    monkeypatch.setattr(scrobbling, "api_request", fake_api)
    s = make()
    _queue(s, 60)
    s._send_pending()
    assert wait_for(lambda: s.pendingCount == 0, timeout=4)
    assert len(sent) == 2  # 50, then the other 10
    assert sent[0]["artist[0]"] == "Artist 0" and sent[0]["track[49]"] == "Song 49" and "artist[50]" not in sent[0]
    assert sent[1]["artist[0]"] == "Artist 50"
    assert s.rejectedCount == 2 and s.rejected[0]["track"] == "Song 1" and "ignored" in s.rejected[0]["reason"]


def test_a_scrobble_last_fm_refuses_doesnt_block_the_queue(make_scrobbler, memory_keyring, monkeypatch):
    _player, make = make_scrobbler
    memory_keyring["session"] = "session"
    sent = []

    def fake_api(method, fields, *_args, **_kwargs):
        sent.append(dict(fields))
        if any(v == "Song 2" for v in fields.values()):
            raise scrobbling.LastFmError(6, "Last.fm error 6: Invalid parameters")
        return {"scrobbles": {"@attr": {"accepted": "1"}}}

    monkeypatch.setattr(scrobbling, "api_request", fake_api)
    s = make()
    _queue(s, 4)
    s._send_pending()
    assert wait_for(lambda: s.pendingCount == 0 and not s.busy, timeout=4)
    assert s.rejectedCount == 1 and s.rejected[0]["track"] == "Song 2"
    singles = [f["track"] for f in sent if "track" in f]
    assert singles == ["Song 0", "Song 1", "Song 2", "Song 3"]  # the batch was refused: found one at a time
    assert s._retry_at == 0.0


def test_a_revoked_session_signs_out_instead_of_retrying(make_scrobbler, memory_keyring, monkeypatch):
    _player, make = make_scrobbler
    memory_keyring["session"] = "session"
    calls = []

    def fake_api(method, *_args, **_kwargs):
        calls.append(method)
        raise scrobbling.LastFmError(9, "Last.fm error 9: Invalid session key")

    monkeypatch.setattr(scrobbling, "api_request", fake_api)
    s = make()
    _queue(s, 2)
    s._send_pending()
    assert wait_for(lambda: not s.connected, timeout=4)
    assert "connect Last.fm again" in s.status and "Invalid session" in s.lastError
    assert s.pendingCount == 2  # kept for when you sign in again
    assert wait_for(lambda: "session" not in memory_keyring)
    s._tick()
    assert calls == ["track.scrobble"]


def test_the_same_song_heard_twice_in_a_row_scrobbles_twice(make_scrobbler, memory_keyring, monkeypatch):
    player, make = make_scrobbler
    memory_keyring["session"] = "session"
    monkeypatch.setattr(scrobbling, "api_request", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("offline")))
    s = make()
    player.set_track({"path": "/song", "title": "Song", "artist": "Artist"}, 120_000)

    def listen_to_the_end():
        s._listened_ms = 59_500
        player.advance(1000)
        s._last_tick = time.monotonic() - 1.0
        s._last_position = player.position - 1000
        s._tick()

    listen_to_the_end()
    assert s.pendingCount == 1
    player.position = 100_000
    s._tick()
    assert s.pendingCount == 1  # still the same listen
    player.set_track({"path": "/song", "title": "Song", "artist": "Artist"}, 120_000)  # repeat one loads it again
    assert s._listened_ms == 0
    listen_to_the_end()
    assert s.pendingCount == 2


def test_tracks_of_30_seconds_or_less_never_scrobble():
    assert scrobbling.listen_threshold({"path": "/a"}, 30_000) == 0
    assert scrobbling.listen_threshold({"path": "/a"}, 31_000) == 15_500
    assert scrobbling.listen_threshold({"path": "/a"}, 0) == 240_000
    assert scrobbling.listen_threshold({"path": "http://radio", "kind": "station"}, 0) == 60_000


def test_keyring_writes_dont_run_on_the_window_thread(make_scrobbler, memory_keyring, monkeypatch):
    import threading

    _player, make = make_scrobbler
    threads = []
    monkeypatch.setattr(scrobbling.keyring, "set_password",
                        lambda service, name, value: (threads.append(threading.current_thread()),
                                                      memory_keyring.__setitem__(name, value)))
    s = make()
    s.setApiCredentials("key", "secret")
    assert wait_for(lambda: s.configured)
    assert threads and threading.main_thread() not in threads


def test_retry_now_skips_the_back_off(make_scrobbler, memory_keyring, monkeypatch):
    _player, make = make_scrobbler
    memory_keyring["session"] = "session"
    answers = [RuntimeError("Couldn't reach Last.fm: timed out")]

    def fake_api(*_a, **_k):
        if answers:
            raise answers.pop()
        return {"scrobbles": {"@attr": {"accepted": "1"}}}

    monkeypatch.setattr(scrobbling, "api_request", fake_api)
    s = make()
    _queue(s, 1)
    s._send_pending()
    assert wait_for(lambda: s.lastError and not s.busy, timeout=4)
    assert s._retry_at > time.monotonic()
    s.retryNow()
    assert wait_for(lambda: s.pendingCount == 0, timeout=4)
    assert s.lastError == ""


def test_scrobble_codes_read_last_fm_answers():
    assert scrobbling.scrobble_codes({"scrobbles": {"@attr": {"accepted": "1"}}}, 1) == [0]
    assert scrobbling.scrobble_codes({"scrobbles": {"@attr": {"accepted": "0"}}}, 1) == [-1]
    assert scrobbling.scrobble_codes({"scrobbles": {"@attr": {"accepted": "1"}}}, 2) is None
    two = {"scrobbles": {"@attr": {"accepted": 1}, "scrobble": [{"ignoredMessage": {"code": "0"}},
                                                                 {"ignoredMessage": {"code": "5"}}]}}
    assert scrobbling.scrobble_codes(two, 2) == [0, 5]
