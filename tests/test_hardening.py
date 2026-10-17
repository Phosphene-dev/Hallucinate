"""Defences against hostile data: tags, lyrics and online answers can't format the interface or make it go online."""
import re
from pathlib import Path

import pytest

QML = Path(__file__).parents[1] / "hallucinate" / "qml"


def test_every_text_element_is_plain_text():
    """Qt's default (AutoText) turns "<b>…" or "<img src=http://…>" in a song title into formatting and fetches.
    Every Text element must say Text.PlainText; add it to new ones."""
    missing = []
    for f in sorted([*QML.glob("*.qml"), *QML.glob("HallucinateStyle/*.qml")]):
        lines = f.read_text(encoding="utf-8").split("\n")
        for i, line in enumerate(lines):
            if not re.match(r"^\s*(?:[A-Za-z_][\w.]*\s*:\s*)?Text \{", line):
                continue
            if line.rstrip().endswith("}"):
                block = line
            else:
                depth, j, block = line.count("{") - line.count("}"), i + 1, ""
                while j < len(lines) and depth > 0:
                    if depth == 1:
                        block += lines[j]
                    depth += lines[j].count("{") - lines[j].count("}")
                    j += 1
            if "textFormat: Text.PlainText" not in block:
                missing.append(f"{f.name}:{i + 1}")
    assert not missing, missing


def test_interface_cannot_go_online(qapp):
    """Even rich text with a remote image (if one ever slipped through) gets an empty local answer."""
    from conftest import wait_for
    from PySide6.QtCore import QCoreApplication, QEvent, QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    from hallucinate import qmlnet

    engine = QQmlApplicationEngine()
    qmlnet.install(engine)
    qmlnet.LocalOnlyAccessManager.blocked.clear()
    engine.loadData(b"""
import QtQuick
Window {
    visible: true; width: 200; height: 100
    Text { textFormat: Text.RichText; text: "<img src=\\"http://127.0.0.1:9/pixel.png\\">" }
    Image { y: 40; source: "https://127.0.0.1:9/cover.jpg" }
}""", QUrl("file:///probe.qml"))
    try:
        blocked = qmlnet.LocalOnlyAccessManager.blocked
        assert wait_for(lambda: len(blocked) >= 2, timeout=3), blocked
        assert {"http://127.0.0.1:9/pixel.png", "https://127.0.0.1:9/cover.jpg"} <= set(blocked)
    finally:
        for root in engine.rootObjects():
            root.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        del engine


def test_update_check_only_keeps_a_version_number(monkeypatch):
    import io
    import json

    from hallucinate import updates

    body = json.dumps({"tag_name": "v1.2.3<img src=x>", "html_url": "https://evil.example/", "assets": []})

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(updates.net, "urlopen", lambda req, timeout=0: Resp(body.encode()))
    latest = updates.fetch_latest()
    assert latest["version"] == "1.2.3" and latest["url"] == updates.RELEASES_PAGE


def test_network_answers_are_size_capped(monkeypatch):
    import io
    import json

    import pytest

    from hallucinate.core import lyrics, net

    class Resp(io.BytesIO):
        def close(self):
            pass

    def fake(data):
        return lambda request, timeout=10: Resp(data)

    monkeypatch.setattr(net.urllib.request, "urlopen", fake(b"x" * 101))
    with net.urlopen("https://example.invalid", limit=100) as r:
        with pytest.raises(net.ResponseTooLarge):
            r.read()
    with net.urlopen("https://example.invalid", limit=100) as r:
        assert len(r.read(50)) == 50 and len(r.read(50)) == 50
        with pytest.raises(net.ResponseTooLarge):
            r.read(10)
    # an endless answer from a lookup ends as an ordinary "no network" error, not a memory blow-up
    monkeypatch.setattr(net, "MAX_RESPONSE", 1000)
    monkeypatch.setattr(net.urlopen, "__defaults__", (10, 1000))
    monkeypatch.setattr(net.urllib.request, "urlopen", fake(json.dumps({"plainLyrics": "la" * 5000}).encode()))
    with pytest.raises(OSError):
        lyrics.fetch_lrclib("Artist", "Title")


def test_only_web_links_are_ever_fetched(tmp_path):
    from hallucinate.core import net

    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    for url in (secret.as_uri(), "ftp://example.com/x", "data:,hi", "javascript:alert(1)", "/etc/passwd"):
        with pytest.raises(net.NotWebLink):
            net.urlopen(url)


def test_a_feed_cannot_point_episodes_at_local_files():
    from hallucinate.core import podcasts as pc

    feed = b"""<rss><channel><title>Evil</title><link>file:///etc</link><image><url>file:///etc/x.png</url></image>
      <item><title>Key</title><guid>1</guid><enclosure url="file:///home/u/.ssh/id_rsa" type="audio/mpeg"/></item>
      <item><title>Real</title><guid>2</guid><enclosure url="https://example.com/2.mp3" type="audio/mpeg"/></item>
    </channel></rss>"""
    podcast, episodes = pc.parse_feed(feed, "https://example.com/feed")
    assert [e["title"] for e in episodes] == ["Real"]
    assert podcast["link"] == "" and podcast["image"] == ""


def test_broken_http_answers_are_ordinary_network_errors(monkeypatch):
    import http.client
    import urllib.error

    from hallucinate.core import net

    def broken(*a, **k):
        raise http.client.BadStatusLine("garbage")

    monkeypatch.setattr(net.urllib.request, "urlopen", broken)
    with pytest.raises(urllib.error.URLError):
        net.urlopen("https://example.com/")


def test_station_websites_are_only_web_links():
    from hallucinate.core.stations import web_homepage

    assert web_homepage("www.example.com") == "https://www.example.com"
    assert web_homepage("http://radio.example/") == "http://radio.example/"
    for bad in ("file:///C:/x.exe", "smb://host/share", "javascript:alert(1)", "search-ms:query=x", "", "a b"):
        assert web_homepage(bad) == ""


def test_playlists_pointing_at_each_other_stop(monkeypatch):
    from hallucinate.core import stations as st

    class Resp:
        def __init__(self, url):
            self.headers = {"Content-Type": "audio/x-scpls"}
            self.url = url

        def read(self, n=-1):
            return f"[playlist]\nFile1={self.url}x\nNumberOfEntries=1\n".encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(st.net, "urlopen", lambda req, timeout=0, limit=0: Resp(req.full_url))
    with pytest.raises(OSError):
        st.resolve("https://example.com/a.pls")


def test_trash_never_takes_a_folder_outside_the_music(tmp_path):
    from hallucinate.library import _strictly_inside

    music = tmp_path / "Music"
    (music / "Artist" / "Album").mkdir(parents=True)
    roots = {str(music)}
    assert _strictly_inside(str(music / "Artist" / "Album"), roots)
    assert not _strictly_inside(str(music), roots)  # the library folder itself
    assert not _strictly_inside(str(tmp_path / "Downloads"), roots)
    assert not _strictly_inside(str(tmp_path / "Music2"), roots)  # a name that only starts the same


def test_a_damaged_waveform_cache_file_is_recomputed(tmp_path):
    from hallucinate.waveform import Envelope

    bad = tmp_path / "x.env.npz"
    bad.write_bytes(b"PK\x03\x04 truncated zip")
    assert Envelope.load(bad) is None and not bad.exists()


def test_tokens_are_not_forwarded_to_another_server():
    import urllib.request

    from hallucinate.core import net

    req = urllib.request.Request("https://api.listenbrainz.org/1/submit", headers={"Authorization": "Token secret"})
    handler = net._WebOnlyRedirects()
    same = handler.redirect_request(req, None, 302, "Found", {}, "https://api.listenbrainz.org/2/submit")
    other = handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example/collect")
    assert "Token secret" in same.headers.values()
    assert "Token secret" not in other.headers.values()
