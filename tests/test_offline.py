"""Offline mode: one switch closes every internet connection, and nothing gets around it."""
import ast
from pathlib import Path

import pytest

from hallucinate.core import net

PACKAGE = Path(__file__).parents[1] / "hallucinate"


@pytest.fixture
def offline():
    net.set_offline(True)
    yield
    net.set_offline(False)


def test_every_internet_request_goes_through_the_gate():
    """Only core/net.py may open connections; new code that calls urllib, http.client or a TCP socket directly
    would slip past offline mode, so it fails here. (discord.py's AF_UNIX socket is local IPC and allowed.)"""
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path in (PACKAGE / "core" / "net.py", PACKAGE / "qmlnet.py"):  # the gate, and the interface's blocker
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("urllib.request", "http.client", "requests"):
                if any(a.name not in ("Request",) for a in node.names):
                    offenders.append(f"{path.name}:{node.lineno} imports {[a.name for a in node.names]}")
            elif isinstance(node, ast.Import) and any(a.name in ("http.client", "requests", "httpx") for a in node.names):
                offenders.append(f"{path.name}:{node.lineno} imports {[a.name for a in node.names]}")
            elif isinstance(node, ast.Attribute) and node.attr in ("urlopen", "create_connection", "QNetworkAccessManager"):
                base = node.value
                if not (isinstance(base, ast.Name) and base.id == "net"):
                    offenders.append(f"{path.name}:{node.lineno} uses .{node.attr}")
            elif isinstance(node, ast.Name) and node.id == "QNetworkAccessManager":
                offenders.append(f"{path.name}:{node.lineno} uses QNetworkAccessManager")
    qml = [f"{p.name}" for p in (PACKAGE / "qml").glob("*.qml") if "XMLHttpRequest" in p.read_text(encoding="utf-8")]
    assert not offenders and not qml, offenders + qml


def test_offline_blocks_requests_without_touching_the_network(offline, monkeypatch):
    import urllib.error
    import urllib.request

    from hallucinate.core import artfetch, lyrics

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("connected while offline"))
    with pytest.raises(urllib.error.URLError, match="Offline mode is on"):
        net.urlopen(urllib.request.Request("https://example.invalid"))
    with pytest.raises(OSError):  # callers see it as "no network": not cached as "no lyrics", not fatal
        lyrics.fetch_lrclib("Artist", "Title")
    with pytest.raises(OSError):
        artfetch.fetch_cover("Artist", "Album")


def test_scrobbles_wait_while_offline(offline):
    from types import SimpleNamespace

    from hallucinate import listenbrainz, scrobbling

    started = []
    item = {"artist": "A", "track": "T", "timestamp": 1}
    lastfm = SimpleNamespace(connected=True, _busy=False, _pending=[item], _retry_at=0.0,
                             _start_job=lambda *a, **k: started.append(a))
    scrobbling.LastFmScrobbler._send_pending(lastfm)
    lb = SimpleNamespace(connected=True, _busy=False, _pending=[item], _retry_at=0.0, _base="", _token="",
                         _start=lambda *a, **k: started.append(a))
    listenbrainz.ListenBrainzScrobbler._flush(lb)
    assert not started  # nothing sent...
    assert lastfm._pending and lb._pending and lastfm._retry_at == lb._retry_at == 0.0  # ...nothing dropped or delayed
    net.set_offline(False)
    scrobbling.LastFmScrobbler._send_pending(lastfm)
    listenbrainz.ListenBrainzScrobbler._flush(lb)
    assert len(started) == 2  # back online, both send straight away


def test_update_check_does_nothing_offline(qapp, offline):
    from hallucinate import updates

    asked = []
    checker = updates.UpdateChecker(fetch=lambda: asked.append(1) or {"version": "99.0", "url": "x"})
    try:
        checker.checkNow()
        assert asked == [] and checker.status == "Offline mode is on" and not checker.busy
    finally:
        checker.shutdown()
