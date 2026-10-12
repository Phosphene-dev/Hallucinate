"""Defences against hostile data: tags, lyrics and online answers can't format the interface or make it go online."""
import re
from pathlib import Path

QML = Path(__file__).parents[1] / "hallucinate" / "qml"


def test_every_text_element_is_plain_text():
    """Qt's default (AutoText) turns "<b>…" or "<img src=http://…>" in a song title into formatting and fetches.
    Every Text element must say Text.PlainText; add it to new ones."""
    missing = []
    for f in sorted(QML.glob("*.qml")):
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
