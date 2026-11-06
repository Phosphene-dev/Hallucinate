"""Discover's online shelves and the wishlist: what's kept and shown from what the services answer (their
answers stood in for here; core/online_discover.py was checked against the real services by hand), what's
left out (ones you have, Not interested, kinds not chosen), offline mode, and the wishlist ticking itself off."""
import time

import pytest

from hallucinate.core import discover as dcore
from hallucinate.core import online_discover as od

RID = "11111111-1111-1111-1111-{:012d}"


def song(i, artist, album):
    return {"path": f"/m/{artist}/{album}/{i}.flac", "mtime": 1, "size": 1, "title": f"{album} {i}", "artist": artist,
            "album_artist": artist, "aa_tag": 1, "album": album, "album_key": f"{artist}|{album}", "track_no": i,
            "disc_no": 1, "year": 2020, "genre": "", "duration": 200.0, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0,
            "sample_rate": 44100}


@pytest.fixture
def db(tmp_path):
    from hallucinate.core.db import Database

    db = Database(tmp_path / "lib.db")
    for artist, album, plays in (("Aurora", "One", 9), ("Bloom", "Two", 3), ("Various Artists", "Hits", 50)):
        for i in range(3):
            t = song(i, artist, album)
            db.upsert_track(t)
            for _ in range(plays):
                db.record_play(t["path"], time.time() - 3600)
    db.commit()
    yield db
    db.close()


def release(n, title, kind="Album", extra=(), date="2026-10-01", artist="Aurora"):
    return {"id": RID.format(n), "title": title, "kind": kind, "extra": list(extra), "date": date, "artist": artist}


def test_the_artists_followed(db):
    assert od.top_artists(db, 1) == [("aurora", "Aurora")]
    assert [k for k, _ in od.top_artists(db, 0)] == ["aurora", "bloom"]  # (never "Various Artists")


def test_new_releases_leave_out_what_you_have_and_what_you_didnt_ask_for(db):
    od.remember_mbid(db, "aurora", "Aurora", RID.format(99), time.time())
    od.store_releases(db, "aurora", [
        release(1, "Three"), release(2, "One (Deluxe Edition)"), release(3, "Live Somewhere", extra=["Live"]),
        release(4, "A Single", kind="Single"), release(5, "Old One", date="2020-01-01"),
        release(6, "Best Of", extra=["Compilation"]), release(7, "Month Only", date="2026-10")], time.time())
    got = [r["title"] for r in od.recent_releases(db, "2026-09-01")]
    assert got == ["Three", "Month Only"]  # (One is yours, whatever the edition; the rest weren't asked for)
    more = [r["title"] for r in od.recent_releases(db, "2026-09-01", ("Album", "Single"), live=True, compilations=True)]
    assert set(more) == {"Three", "Month Only", "Live Somewhere", "A Single", "Best Of"}
    dcore.dismiss(db, "release", RID.format(1), "Three by Aurora")
    assert [r["title"] for r in od.recent_releases(db, "2026-09-01")] == ["Month Only"]
    dcore.dismiss(db, "artist", "aurora", "Aurora")
    assert od.recent_releases(db, "2026-09-01") == []


def test_similar_artists_combine_and_leave_out_yours(db):
    now = time.time()
    od.store_similar(db, "aurora", "deezer", [{"name": "Cinder", "score": 1.0}, {"name": "Bloom", "score": 0.9},
                                             {"name": "Delta", "score": 0.5}], now)
    od.store_similar(db, "bloom", "deezer", [{"name": "Delta", "score": 1.0}, {"name": "Ember", "score": 0.4}], now)
    got = od.suggestions(db, od.top_artists(db, 0), "deezer")
    assert [s["name"] for s in got] == ["Delta", "Cinder", "Ember"]  # (like two of yours first; Bloom is yours)
    assert got[0]["because"] == ["Aurora", "Bloom"]
    dcore.dismiss(db, "artist", "delta", "Delta")
    assert [s["name"] for s in od.suggestions(db, od.top_artists(db, 0), "deezer")] == ["Cinder", "Ember"]
    assert od.suggestions(db, od.top_artists(db, 0), "listenbrainz") == []  # (each source kept apart)
    od.forget(db)
    assert od.suggestions(db, od.top_artists(db, 0), "deezer") == []


def test_the_wishlist_ticks_itself_off(db):
    od.wish(db, "album", "Aurora", "One", now=1)
    od.wish(db, "album", "Aurora", "Two", note="the blue vinyl", now=2)
    od.wish(db, "artist", "Cinder", now=3)
    od.wish(db, "album", "Aurora", "One", now=4)  # (already on it: stays as it was)
    assert [w["title"] or w["artist"] for w in od.wishes(db)] == ["Cinder", "Two", "One"]
    got = od.tick_off(db, 10)
    assert [w["title"] for w in got] == ["One"]
    db.upsert_track(song(0, "Cinder", "Debut"))
    db.commit()
    assert [w["artist"] for w in od.tick_off(db, 11)] == ["Cinder"]
    assert od.tick_off(db, 12) == []
    wishes = od.wishes(db)
    assert [w["got"] is None for w in wishes] == [True, False, False] and wishes[0]["note"] == "the blue vinyl"
    od.unwish(db, wishes[0]["key"])
    assert len(od.wishes(db)) == 2


def test_links_and_dates():
    assert od.padded("2025") == "2025-01-01" and od.padded("2025-08") == "2025-08-01"
    assert od.store_link("bandcamp", "Sigur Rós", "Ágætis byrjun") == \
        "https://bandcamp.com/search?q=Sigur+R%C3%B3s+%C3%81g%C3%A6tis+byrjun"
    assert od.store_link("nowhere", "A").startswith("https://bandcamp.com/")
    assert od.release_link("not an id") == "" and od.cover_url("../../etc") == ""
    assert od._web("javascript:alert(1)") == "" and od._web("http://x") == ""


def test_offline_mode_asks_nothing(monkeypatch):
    from hallucinate.core import net

    net.set_offline(True)
    try:
        with pytest.raises(OSError):
            od.similar_deezer("Aurora")
        with pytest.raises(OSError):
            od.artist_id("Aurora")
    finally:
        net.set_offline(False)


def test_a_picture_must_be_a_picture(tmp_path, monkeypatch):
    import io

    from hallucinate.core import net

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    body = [b"<html>not a picture</html>"]
    monkeypatch.setattr(net, "urlopen", lambda *a, **k: Resp(body[0]))
    assert od.fetch_image("https://example.org/a.jpg", str(tmp_path)) == ""
    body[0] = b"\xff\xd8\xff" + b"\x00" * 100
    path = od.fetch_image("https://example.org/a.jpg", str(tmp_path))
    assert path and open(path, "rb").read(3) == b"\xff\xd8\xff"
    assert od.fetch_image("http://example.org/b.jpg", str(tmp_path)) == ""


# --- in the app ----------------------------------------------------------------------------------------------
class FakeShell:
    def __init__(self, **on):
        from PySide6.QtCore import QObject, Signal

        class S(QObject):
            featuresChanged = Signal()

        self.s = S()
        self.featuresChanged = self.s.featuresChanged
        self.features = dict(on)
        self.said = []

    def featureOn(self, name):  # noqa: N802
        return self.features.get(name, False)

    def notify(self, title, body):
        self.said.append((title, body))


@pytest.fixture
def settings():
    from PySide6.QtCore import QSettings

    QSettings().remove("discoverOnline")
    yield
    QSettings().remove("discoverOnline")


def test_looking_up_and_showing(qapp, db, tmp_path, monkeypatch, settings):
    from conftest import wait_for

    from hallucinate.discoveronline import OnlineDiscover

    asked = []
    monkeypatch.setattr(od, "artist_id", lambda name: asked.append(name) or RID.format(len(asked)))
    monkeypatch.setattr(od, "releases_since", lambda mbid, since: [release(int(mbid[-3:]) * 10, "New " + mbid[-1])])
    monkeypatch.setattr(od, "fetch_image", lambda url, folder: "")
    monkeypatch.setattr(od, "similar_listenbrainz", lambda mbid: [{"name": "Cinder", "score": 1.0, "mbid": "", "url": ""}])
    shell = FakeShell(discoverNewReleases=True, discoverSimilar=True, discoverWishlist=True)
    o = OnlineDiscover(tmp_path / "lib.db", tmp_path, None, shell, None, autostart=False)
    said = []
    o.message.connect(said.append)
    try:
        o.open()
        assert wait_for(lambda: o.newReleases and o.similarArtists, timeout=10), (o.newReleases, o.similarArtists)
        assert asked == ["Aurora", "Bloom"]  # (each artist looked up once: similar artists reuse the id)
        assert [s["name"] for s in o.similarArtists] == ["Cinder"]
        o.open()  # (not due again so soon: nothing asked)
        assert wait_for(lambda: o.busy == "", timeout=10) and asked == ["Aurora", "Bloom"]
        r = o.newReleases[0]
        o.addWish("album", r["artist"], r["title"], r["link"], r["id"])
        assert wait_for(lambda: o.wishlist and o.newReleases[0]["wished"], timeout=10)
        assert said and "wishlist" in said[-1]
        o.notInterestedArtist("Cinder")
        assert wait_for(lambda: o.similarArtists == [], timeout=10)
        shell.features["discoverNewReleases"] = False
        shell.featuresChanged.emit()
        assert wait_for(lambda: o.newReleases == [], timeout=10)
    finally:
        o.shutdown()


def test_offline_the_shelves_show_what_was_found_and_ask_nothing(qapp, db, tmp_path, monkeypatch, settings):
    from conftest import wait_for

    from hallucinate.core import net
    from hallucinate.discoveronline import OnlineDiscover

    od.remember_mbid(db, "aurora", "Aurora", RID.format(9), time.time())
    od.store_releases(db, "aurora", [release(1, "Kept")], time.time())
    monkeypatch.setattr(od, "artist_id", lambda name: pytest.fail("asked while offline"))
    monkeypatch.setattr(od, "releases_since", lambda *a: pytest.fail("asked while offline"))
    shell = FakeShell(discoverNewReleases=True)
    net.set_offline(True)
    o = OnlineDiscover(tmp_path / "lib.db", tmp_path, None, shell, None, autostart=False)
    try:
        o.open()
        o.refresh()
        assert wait_for(lambda: [r["title"] for r in o.newReleases] == ["Kept"], timeout=10)
        assert o.offline and o.busy == ""
        o.preview("Aurora")  # (no preview offline either)
        assert o.previewing == ""
    finally:
        net.set_offline(False)
        o.shutdown()


def test_a_preview_pauses_the_music_and_carries_on_after(qapp, db, tmp_path, monkeypatch, settings):
    from conftest import wait_for

    from hallucinate.discoveronline import OnlineDiscover

    class Player:
        playing, volume = True, 0.5
        calls = []

        def pause(self):
            self.playing = False
            self.calls.append("pause")

        def play(self):
            self.playing = True
            self.calls.append("play")

    monkeypatch.setattr(od, "preview", lambda artist, source: {"title": "Song", "artist": artist,
                                                               "url": "https://example.invalid/a.mp3", "link": ""})
    player = Player()
    o = OnlineDiscover(tmp_path / "lib.db", tmp_path, player, FakeShell(discoverSimilar=True), None, autostart=False)
    try:
        o.preview("Cinder")
        assert o.previewing == "Cinder"
        assert wait_for(lambda: player.calls == ["pause"] and o.previewTitle == "Song", timeout=10)
        o.preview("Cinder")  # (again: stops it)
        assert o.previewing == "" and player.calls == ["pause", "play"]
        o.setPreviews("off")
        o.preview("Cinder")
        assert o.previewing == ""
    finally:
        o.shutdown()


def test_news_is_only_whats_new_and_shown(qapp, db, tmp_path, monkeypatch, settings):
    """An artist looked at for the first time brings no notification (their past year isn't news); later, only
    new releases the shelf shows count (not a live album when live albums are off)."""
    import datetime

    from conftest import wait_for

    from hallucinate.discoveronline import OnlineDiscover

    today = datetime.date.today().isoformat()
    found = {"Aurora": [release(1, "Old News", date=today)]}
    monkeypatch.setattr(od, "artist_id", lambda name: RID.format(500 + len(name)))
    by_id = {RID.format(500 + len(n)): n for n in ("Aurora", "Bloom")}
    monkeypatch.setattr(od, "releases_since", lambda mbid, since: found.get(by_id[mbid], []))
    monkeypatch.setattr(od, "fetch_image", lambda url, folder: "")
    shell = FakeShell(discoverNewReleases=True)
    o = OnlineDiscover(tmp_path / "lib.db", tmp_path, None, shell, None, autostart=False)
    o.setNotifyNew(True)
    try:
        o.open()
        assert wait_for(lambda: o.newReleases and o.busy == "", timeout=10)
        assert shell.said == []  # (first look at these artists)
        found["Aurora"] += [release(2, "Fresh", date=today), release(3, "Live One", extra=["Live"], date=today)]
        o.refresh()
        assert wait_for(lambda: len(o.newReleases) == 2 and o.busy == "", timeout=10)
        assert len(shell.said) == 1 and "1 new release" in shell.said[0][1]
    finally:
        o.shutdown()


def test_stop_drops_lookups_waiting_their_turn(qapp, db, tmp_path, monkeypatch, settings):
    import threading

    from conftest import wait_for

    from hallucinate.discoveronline import OnlineDiscover

    gate, asked = threading.Event(), []
    monkeypatch.setattr(od, "artist_id", lambda name: gate.wait(5) and RID.format(1))
    monkeypatch.setattr(od, "releases_since", lambda mbid, since: asked.append(mbid) or [])
    monkeypatch.setattr(od, "similar_listenbrainz", lambda mbid: asked.append("similar") or [])
    o = OnlineDiscover(tmp_path / "lib.db", tmp_path, None, FakeShell(discoverNewReleases=True, discoverSimilar=True),
                       None, autostart=False)
    try:
        o.open()
        o.open()  # (asked again while waiting: not queued twice)
        assert wait_for(lambda: o.busy == "releases", timeout=5)
        o.stop()
        gate.set()
        assert wait_for(lambda: o.busy == "", timeout=10)
        assert "similar" not in asked and len(asked) <= 1
    finally:
        o.shutdown()


def test_deezer_pictures_for_any_source(qapp, db, tmp_path, monkeypatch, settings):
    """Off unless chosen: artists like yours from ListenBrainz get their pictures from Deezer (asked once, by
    name; one Deezer doesn't know is asked about again only after a month)."""
    from PySide6.QtCore import QSettings
    from conftest import wait_for

    from hallucinate.discoveronline import OnlineDiscover

    monkeypatch.setattr(od, "artist_id", lambda name: RID.format(len(name)))
    monkeypatch.setattr(od, "fetch_image", lambda url, folder: "")
    monkeypatch.setattr(od, "cached_image", lambda url, folder: url)
    monkeypatch.setattr(od, "similar_listenbrainz", lambda mbid: [{"name": "Cinder", "score": 1.0, "mbid": "", "url": ""},
                                                                  {"name": "Nobody Knows", "score": 0.5, "mbid": "", "url": ""}])
    asked = []
    monkeypatch.setattr(od, "deezer_artist", lambda name: asked.append(name) or (
        {"id": 1, "name": name, "picture": "https://e-cdns-images.dzcdn.net/cinder.jpg", "url": ""} if name == "Cinder" else None))
    o = OnlineDiscover(tmp_path / "lib.db", tmp_path, None, FakeShell(discoverSimilar=True), None, autostart=False)
    try:
        o.open()
        assert wait_for(lambda: o.similarArtists and o.busy == "", timeout=10)
        assert asked == [] and all(not s["picture"] for s in o.similarArtists)  # (off: Deezer isn't asked)
        o.setDeezerPictures(True)
        assert wait_for(lambda: any(s["picture"] for s in o.similarArtists), timeout=10)
        pics = {s["name"]: s["picture"] for s in o.similarArtists}
        assert pics["Cinder"].endswith("cinder.jpg") and not pics["Nobody Knows"]
        assert sorted(asked) == ["Cinder", "Nobody Knows"]
        o.refresh()
        assert wait_for(lambda: o.busy == "", timeout=10)
        time.sleep(0.2)
        assert sorted(asked) == ["Cinder", "Nobody Knows"]  # (kept: not asked again)
        assert QSettings().value("discoverOnline/deezerPictures") in (True, "true")
    finally:
        o.shutdown()
