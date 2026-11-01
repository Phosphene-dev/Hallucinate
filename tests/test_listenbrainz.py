import json

from conftest import wait_for
from PySide6.QtCore import QObject, Signal

from hallucinate import listenbrainz
from hallucinate.listenbrainz import (
    ListenBrainzScrobbler,
    fetch_listenbrainz_history,
    lb_request,
    parse_lastfm_page,
    parse_listens,
    track_metadata,
)
from hallucinate.userlib import UserLibrary


class FakePlayer(QObject):
    trackChanged = Signal()
    stateChanged = Signal()
    played = Signal(object)
    skipped = Signal(object)
    seeked = Signal(int)

    def __init__(self):
        super().__init__()
        self.current = {}
        self.playing = False
        self.position = 0
        self.duration = 0


def test_track_metadata_and_listen_parsers():
    metadata = track_metadata({"artist": "Björk", "title": "Jóga", "album": "Homogenic",
                               "duration": 251, "track_no": 2})
    assert metadata["artist_name"] == "Björk"
    assert metadata["track_name"] == "Jóga"
    assert metadata["release_name"] == "Homogenic"
    assert metadata["additional_info"]["duration"] == 251
    assert metadata["additional_info"]["tracknumber"] == 2

    listens = parse_listens({"payload": {"listens": [{
        "listened_at": 123,
        "track_metadata": {"artist_name": "Björk", "track_name": "Jóga", "release_name": "Homogenic"},
    }]}})
    assert listens == [{"ts": 123, "artist": "Björk", "title": "Jóga", "album": "Homogenic"}]
    legacy, pages = parse_lastfm_page({"recenttracks": {
        "track": [{"name": "Jóga", "artist": {"#text": "Björk"}, "album": {"#text": "Homogenic"},
                   "date": {"uts": "123"}}, {"name": "Live now", "artist": {"#text": "Björk"}}],
        "@attr": {"totalPages": "2"},
    }})
    assert pages == 2
    assert legacy == [{"ts": 123, "artist": "Björk", "title": "Jóga", "album": "Homogenic"}]


def test_token_validation_uses_authorization_header(monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"valid":true,"user_name":"listener"}'

    def open_url(request, timeout):
        requests.append(request)
        assert timeout == 20
        return Response()

    monkeypatch.setattr(listenbrainz.net, "urlopen", open_url)

    result = lb_request("https://api.listenbrainz.org", "/1/validate-token", "secret-token")

    assert result["valid"]
    assert requests[0].get_header("Authorization") == "Token secret-token"


def test_fetch_listenbrainz_history_paginates_and_quotes_username(monkeypatch):
    responses = [
        [{"ts": 100, "artist": "Artist", "title": "New", "album": "A"},
         {"ts": 90, "artist": "Artist", "title": "Old", "album": "A"}],
        [{"ts": 80, "artist": "Artist", "title": "Older", "album": "A"}],
        [],
    ]
    calls = []

    def request(base, path, token, params):
        calls.append((path, token, dict(params)))
        return {"payload": {"listens": [
            {"listened_at": item["ts"], "track_metadata": {
                "artist_name": item["artist"], "track_name": item["title"], "release_name": item["album"],
            }} for item in responses.pop(0)
        ]}}

    progress = []
    monkeypatch.setattr(listenbrainz, "lb_request", request)
    result = fetch_listenbrainz_history("https://lb.example", "person/name", "token", progress.append)

    assert [item["ts"] for item in result] == [100, 90, 80]
    assert calls[0] == ("/1/user/person%2Fname/listens", "token", {"count": 1000})
    assert calls[1][2] == {"count": 1000, "max_ts": 90}
    assert progress == [2, 3]


def test_imported_history_deduplicates_and_updates_matched_play_counts(db, scan, music):
    scan(music)
    track = next(item for item in db._rows("SELECT * FROM tracks") if item["title"] == "Echoes of Dawn")
    listens = [
        {"ts": 1700000000, "artist": "Aurora Vale", "title": "Echoes of Dawn", "album": "Northern Lights"},
        {"ts": 1700000000, "artist": "Aurora Vale", "title": "Echoes of Dawn", "album": "Northern Lights"},
        {"ts": 1700000100, "artist": "Unknown", "title": "Elsewhere", "album": "Elsewhere"},
    ]
    result = db.import_plays(listens, "listenbrainz")

    assert result == {"added": 2, "matched": 1}
    assert db.most_played(5)[0]["path"] == track["path"]
    assert db.most_played(5)[0]["plays"] == 1
    assert db.import_plays(listens, "listenbrainz") == {"added": 0, "matched": 0}


def test_history_import_runs_off_thread_into_user_library(db, scan, music, tmp_path, monkeypatch, qapp):
    scan(music)
    db_path = db.conn.execute("PRAGMA database_list").fetchone()["file"]
    player = FakePlayer()
    userlib = UserLibrary(db_path, player)
    scrobbler = ListenBrainzScrobbler(player, tmp_path, userlib)
    monkeypatch.setattr(listenbrainz, "fetch_listenbrainz_history", lambda *args: [
        {"ts": 1700000000, "artist": "Aurora Vale", "title": "Echoes of Dawn", "album": "Northern Lights"},
    ])

    scrobbler.importHistory("listenbrainz", "listener")
    assert wait_for(lambda: not scrobbler.importing)
    assert "Imported 1 new listen (1 matched" in scrobbler.importStatus
    assert db.most_played(5)[0]["plays"] == 1

    scrobbler.shutdown()
    userlib.shutdown()


def test_listenbrainz_keyring_connection_and_offline_queue(tmp_path, monkeypatch, qapp):
    secrets = {}
    monkeypatch.setattr(listenbrainz.keyring, "get_password", lambda service, user: secrets.get((service, user)))
    monkeypatch.setattr(listenbrainz.keyring, "set_password",
                        lambda service, user, value: secrets.__setitem__((service, user), value))
    monkeypatch.setattr(listenbrainz.keyring, "delete_password",
                        lambda service, user: secrets.pop((service, user), None))
    requests = []

    def request(base, path, token=None, payload=None, params=None):
        requests.append((path, token, payload))
        if path == "/1/validate-token":
            return {"valid": True, "user_name": "listener"}
        return {"status": "ok"}

    monkeypatch.setattr(listenbrainz, "lb_request", request)
    player = FakePlayer()
    scrobbler = ListenBrainzScrobbler(player, tmp_path)
    track = {"path": "/music/song.flac", "artist": "Artist", "title": "Song", "album": "Record", "duration": 180}
    scrobbler._queue_listen(track, 1700000000)
    assert scrobbler.pendingCount == 1
    assert json.loads((tmp_path / "listenbrainz-listens.json").read_text(encoding="utf-8"))[0]["track_metadata"]["track_name"] == "Song"

    scrobbler.connectToken("secure-token", "")
    assert wait_for(lambda: scrobbler.connected and not scrobbler.busy)
    assert secrets[(listenbrainz.KEYRING_SERVICE, "token")] == "secure-token"
    assert secrets[(listenbrainz.KEYRING_SERVICE, "user")] == "listener"
    assert requests[0][0:2] == ("/1/validate-token", "secure-token")
    assert wait_for(lambda: scrobbler.pendingCount == 0)
    assert any(call[2] and call[2]["listen_type"] == "single" for call in requests)

    player.current = track
    player.playing = True
    player.stateChanged.emit()
    assert wait_for(lambda: any(call[2] and call[2]["listen_type"] == "playing_now" for call in requests))
    assert wait_for(lambda: not scrobbler.busy)
    scrobbler.disconnectAccount()
    assert not scrobbler.connected
    assert wait_for(lambda: (listenbrainz.KEYRING_SERVICE, "token") not in secrets)
    scrobbler.shutdown()


def _scrobbler(tmp_path, monkeypatch, request, secrets=None):
    secrets = {} if secrets is None else secrets
    monkeypatch.setattr(listenbrainz.keyring, "get_password", lambda service, user: secrets.get((service, user)))
    monkeypatch.setattr(listenbrainz.keyring, "set_password",
                        lambda service, user, value: secrets.__setitem__((service, user), value))
    monkeypatch.setattr(listenbrainz.keyring, "delete_password",
                        lambda service, user: secrets.pop((service, user), None))
    monkeypatch.setattr(listenbrainz, "lb_request", request)
    player = FakePlayer()
    scrobbler = ListenBrainzScrobbler(player, tmp_path)
    scrobbler._timer.stop()  # the tests tick by hand
    return player, scrobbler


def _listens(n):
    return [{"listened_at": 1000 + i, "track_metadata": {"artist_name": "A", "track_name": f"Song {i}"}}
            for i in range(n)]


def test_listens_count_by_the_last_fm_rule(tmp_path, monkeypatch, qapp):
    import time

    player, scrobbler = _scrobbler(tmp_path, monkeypatch, lambda *a, **k: {"status": "ok"})
    try:
        player.current = {"path": "/long.flac", "artist": "A", "title": "Long", "duration": 600}
        player.duration, player.playing = 600_000, True
        player.trackChanged.emit()

        def tick():
            player.position += 1000
            scrobbler._last_tick = time.monotonic() - 1.0
            scrobbler._last_position = player.position - 1000
            scrobbler._count()

        scrobbler._listened_ms = 60_000  # the old rule (30 s) would have counted it by now
        tick()
        assert scrobbler.pendingCount == 0
        scrobbler._listened_ms = 239_500  # four minutes: it counts
        tick()
        assert scrobbler.pendingCount == 1
        tick()
        assert scrobbler.pendingCount == 1
        player.position = 0
        player.trackChanged.emit()  # repeat one: the same song again
        scrobbler._listened_ms = 239_500
        tick()
        assert scrobbler.pendingCount == 2
    finally:
        scrobbler.shutdown()


def test_queued_listens_go_in_batches(tmp_path, monkeypatch, qapp):
    sent = []

    def request(base, path, token=None, payload=None, params=None):
        sent.append(payload)
        return {"status": "ok"}

    _player, scrobbler = _scrobbler(tmp_path, monkeypatch, request)
    try:
        scrobbler._token = "token"
        scrobbler._pending = _listens(150)
        scrobbler._flush()
        assert wait_for(lambda: scrobbler.pendingCount == 0)
        assert [len(p["payload"]) for p in sent] == [100, 50]
        assert sent[0]["listen_type"] == "import"
    finally:
        scrobbler.shutdown()


def test_a_listen_listenbrainz_refuses_is_dropped(tmp_path, monkeypatch, qapp):
    sent = []

    def request(base, path, token=None, payload=None, params=None):
        sent.append([item["track_metadata"]["track_name"] for item in payload["payload"]])
        if any(name == "Song 1" for name in sent[-1]):
            raise listenbrainz.Rejected(400, "ListenBrainz rejected the request (400)")
        return {"status": "ok"}

    _player, scrobbler = _scrobbler(tmp_path, monkeypatch, request)
    try:
        scrobbler._token = "token"
        scrobbler._pending = _listens(3)
        scrobbler._flush()
        assert wait_for(lambda: scrobbler.pendingCount == 0 and not scrobbler.busy)
        assert sent == [["Song 0", "Song 1", "Song 2"], ["Song 0"], ["Song 1"], ["Song 2"]]
        assert scrobbler.rejectedCount == 1 and scrobbler.rejected[0]["track"] == "Song 1"
    finally:
        scrobbler.shutdown()


def test_a_revoked_token_signs_out_instead_of_retrying(tmp_path, monkeypatch, qapp):
    secrets = {(listenbrainz.KEYRING_SERVICE, "token"): "old", (listenbrainz.KEYRING_SERVICE, "user"): "me"}

    def request(*_a, **_k):
        raise listenbrainz.Rejected(401, "ListenBrainz rejected the request (401)")

    _player, scrobbler = _scrobbler(tmp_path, monkeypatch, request, secrets)
    try:
        assert scrobbler.connected
        scrobbler._pending = _listens(2)
        scrobbler._flush()
        assert wait_for(lambda: not scrobbler.connected)
        assert "connect ListenBrainz again" in scrobbler.status and "401" in scrobbler.lastError
        assert scrobbler.pendingCount == 2
        assert wait_for(lambda: (listenbrainz.KEYRING_SERVICE, "token") not in secrets)
    finally:
        scrobbler.shutdown()


def test_a_server_of_your_own_is_normalised_and_remembered(monkeypatch, qapp, tmp_path):
    """Maloja, Koito and Multi-Scrobbler speak the ListenBrainz API under a path of their own; the server is kept, so
    listens (and the token) never go to listenbrainz.org after a restart."""
    import pytest

    from hallucinate import listenbrainz as lb

    assert lb.normalize_server("") == ""
    assert lb.normalize_server("https://api.listenbrainz.org/") == ""
    assert lb.normalize_server("maloja.home.lan/apis/listenbrainz/") == "https://maloja.home.lan/apis/listenbrainz"
    assert lb.normalize_server("http://192.168.1.5:42010/apis/listenbrainz/1/submit-listens") == \
        "http://192.168.1.5:42010/apis/listenbrainz"
    with pytest.raises(ValueError):
        lb.normalize_server("ftp://example.com")
    assert lb.server_label("") == "ListenBrainz" and lb.server_label("https://koito.example/apis/listenbrainz") == "koito.example"

    store = {}
    monkeypatch.setattr(lb.keyring, "get_password", lambda s, k: store.get(k))
    monkeypatch.setattr(lb.keyring, "set_password", lambda s, k, v: store.__setitem__(k, v))
    calls = []

    def fake(base, path, token=None, payload=None, params=None):
        calls.append((base, path))
        return {"valid": True, "user_name": "me"}
    monkeypatch.setattr(lb, "lb_request", fake)

    from conftest import wait_for
    from PySide6.QtCore import QObject, Signal

    class P(QObject):
        trackChanged = Signal()
        stateChanged = Signal()
        seeked = Signal(int)
        current, playing, position, duration = {}, False, 0, 0

    player = P()
    s = lb.ListenBrainzScrobbler(player, tmp_path)
    try:
        s.connectToken("tok", "maloja.example.com/apis/listenbrainz")
        assert wait_for(lambda: s.connected, timeout=4)
        assert calls[0] == ("https://maloja.example.com/apis/listenbrainz", "/1/validate-token")
        assert s.server == "https://maloja.example.com/apis/listenbrainz" and s.serverName == "maloja.example.com"
        assert "maloja.example.com" in s.status
        again = lb.ListenBrainzScrobbler(player, tmp_path)  # after a restart
        assert again._base == "https://maloja.example.com/apis/listenbrainz"
        again.shutdown()
    finally:
        s._qsettings.remove("listenbrainz/server")
        s.shutdown()
