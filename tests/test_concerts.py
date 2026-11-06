"""Concerts nearby: finding the place typed in, which of Ticketmaster's shows are kept (the artist must be among the
performers; past ones, and links to anywhere but the ticket sellers, aren't), what's shown (soonest first, not for
artists marked Not interested, only for the place chosen), a key that isn't taken, offline mode, and the shelf as
the Discover controller fills it. The services' answers are stood in for."""
import datetime
import io
import json
import time
import urllib.error

import pytest
from test_discover_online import FakeShell, db, settings  # noqa: F401 - fixtures

from hallucinate.core import concerts, net

TODAY = datetime.date(2026, 11, 6)


def event(eid, date, performers, venue="Le Transbordeur", city="Villeurbanne", status="onsale",
          url="https://www.ticketmaster.fr/fr/manifestation/x-billet/idmanif/1"):
    return {"id": eid, "name": " + ".join(performers), "url": url,
            "dates": {"start": {"localDate": date, "localTime": "20:00:00"}, "status": {"code": status}},
            "_embedded": {"venues": [{"name": venue, "city": {"name": city}, "country": {"name": "France"}}],
                          "attractions": [{"name": p} for p in performers]}}


def test_the_place_is_found_on_the_map(monkeypatch):
    asked = []
    monkeypatch.setattr(concerts, "_json", lambda url, **k: asked.append(url) or [
        {"lat": "45.7578", "lon": "4.8320", "display_name": "Lyon, Métropole de Lyon, France"}])
    found = concerts.geocode("  Lyon ")
    assert found == {"lat": 45.7578, "lon": 4.832, "name": "Lyon, Métropole de Lyon, France"}
    assert "nominatim.openstreetmap.org" in asked[0] and "q=Lyon" in asked[0]
    monkeypatch.setattr(concerts, "_json", lambda url, **k: [])
    assert concerts.geocode("Nowhere at all") is None
    monkeypatch.setattr(concerts, "_json", lambda url, **k: [{"lat": "999", "lon": "0"}])
    assert concerts.geocode("Broken") is None
    assert concerts.geocode("   ") is None


def test_a_point_as_a_geohash():
    assert concerts.geohash(57.64911, 10.40744, 11) == "u4pruydqqvj"
    assert concerts.place_key(45.7578, 4.832, 50) == concerts.place_key(45.7579, 4.8321, 50)  # (the same place)
    assert concerts.place_key(45.7578, 4.832, 50) != concerts.place_key(45.7578, 4.832, 100)


def test_only_the_artists_own_upcoming_shows_are_kept(monkeypatch):
    asked = []
    answer = {"_embedded": {"events": [
        event("a", "2026-12-01", ["Aurora"]),
        event("b", "2026-11-20", ["Aurora Borealis Tribute Band"]),  # (the keyword matched, the artist didn't)
        event("c", "2026-10-01", ["Aurora"]),  # (past)
        event("d", "2027-01-15", ["Bloom", "AURORA"], status="cancelled"),
        event("e", "2027-02-01", ["Aurora"], url="https://evil.example/aurora"),
    ]}}
    monkeypatch.setattr(concerts, "_json", lambda url, **k: asked.append(url) or answer)
    found = concerts.shows("Aurora", "KEY", 45.7578, 4.832, 50, today=TODAY)
    assert [c["id"] for c in found] == ["a", "d", "e"]
    assert found[0] == {"id": "a", "artist": "Aurora", "name": "Aurora", "date": "2026-12-01", "time": "20:00:00",
                        "venue": "Le Transbordeur", "city": "Villeurbanne", "country": "France",
                        "link": "https://www.ticketmaster.fr/fr/manifestation/x-billet/idmanif/1", "status": ""}
    assert found[1]["status"] == "cancelled"
    assert found[2]["link"] == ""  # (only ticket sellers' pages are opened)
    url = asked[0]
    for part in ("keyword=Aurora", "apikey=KEY", "radius=50", "unit=km", "locale=%2A", "classificationName=music",
                 f"geoPoint={concerts.geohash(45.7578, 4.832)}", "startDateTime=2026-11-06T00%3A00%3A00Z"):
        assert part in url, part
    for link, ok in (("https://www.ticketmaster.co.uk/event/1", True), ("https://concerts.livenation.com/x", True),
                     ("https://ticketmaster.evil.com/x", False), ("http://www.ticketmaster.com/x", False),
                     ("https://www.ticketmaster.com.evil.net/x", False), ("https://ticketmaster.fr", True)):
        assert bool(concerts._link(link)) is ok, link
    monkeypatch.setattr(concerts, "_json", lambda url, **k: {"page": {"totalElements": 0}})
    assert concerts.shows("Aurora", "KEY", 0, 0, 25, today=TODAY) == []


def test_a_key_ticketmaster_doesnt_take(monkeypatch):
    def refuse(url, **k):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
    monkeypatch.setattr(concerts, "_json", refuse)
    with pytest.raises(concerts.BadKey):
        concerts.check_key("nope")
    with pytest.raises(concerts.BadKey):
        concerts.shows("Aurora", "nope", 0, 0, 25)
    with pytest.raises(concerts.BadKey):
        concerts.check_key("  ")


def test_offline_mode_asks_nothing(monkeypatch):
    net.set_offline(True)
    try:
        with pytest.raises(OSError):
            concerts.geocode("Lyon")
        with pytest.raises(OSError):
            concerts.shows("Aurora", "KEY", 0, 0, 25)
    finally:
        net.set_offline(False)


def test_whats_kept_and_shown(db):  # noqa: F811
    from hallucinate.core import discover as dcore

    here, there = concerts.place_key(45.75, 4.83, 50), concerts.place_key(48.85, 2.35, 50)
    gig = {"id": "a", "artist": "Aurora", "name": "Aurora", "date": "2027-01-10", "time": "", "venue": "V",
           "city": "C", "country": "", "link": "", "status": ""}
    concerts.store(db, "aurora", here, [gig, dict(gig, id="b", date="2026-12-01"), dict(gig, id="old", date="2026-01-01")], 1.0)
    concerts.store(db, "bloom", here, [dict(gig, id="c", artist="Bloom", date="2026-12-05")], 1.0)
    concerts.store(db, "aurora", there, [dict(gig, id="paris")], 1.0)
    assert [c["id"] for c in concerts.upcoming(db, here, today=TODAY)] == ["b", "c", "a"]
    assert concerts.checked(db, "aurora", here) == 1.0 and concerts.checked(db, "aurora", "elsewhere") == 0
    concerts.store(db, "aurora", here, [gig], 2.0)  # (asked again: what it says now replaces what it said)
    assert [c["id"] for c in concerts.upcoming(db, here, today=TODAY)] == ["c", "a"]
    dcore.dismiss(db, "artist", "bloom", "Bloom")
    assert [c["id"] for c in concerts.upcoming(db, here, today=TODAY)] == ["a"]
    concerts.forget(db)
    assert concerts.upcoming(db, here, today=TODAY) == [] and concerts.checked(db, "aurora", here) == 0


class FakeSources:
    def __init__(self, key):
        from PySide6.QtCore import QObject, Signal

        class S(QObject):
            changed = Signal()

        self.s = S()
        self.changed = self.s.changed
        self.key = key

    @property
    def ticketmasterConnected(self):  # noqa: N802
        return bool(self.key)

    def ticketmaster_key(self, wait=3.0):
        return self.key

    def lastfm_key(self):
        return ""


def test_the_shelf(qapp, db, tmp_path, monkeypatch, settings):  # noqa: F811
    from conftest import wait_for

    from hallucinate import discoveronline
    from hallucinate.discoveronline import OnlineDiscover

    monkeypatch.setattr(discoveronline, "TICKETMASTER_GAP_S", 0)
    places, asked = [], []
    monkeypatch.setattr(concerts, "geocode", lambda text: places.append(text) or (
        {"lat": 45.7578, "lon": 4.832, "name": "Lyon, France"} if text == "Lyon" else None))
    soon = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()

    def shows(artist, key, lat, lon, radius, today=None):
        asked.append((artist, key, radius))
        return [{"id": "x1", "artist": artist, "name": artist, "date": soon, "time": "", "venue": "Hall",
                 "city": "Lyon", "country": "France", "link": "", "status": ""}] if artist == "Aurora" else []
    monkeypatch.setattr(concerts, "shows", shows)
    sources = FakeSources("")
    shell = FakeShell(discoverConcerts=True)
    o = OnlineDiscover(tmp_path / "lib.db", tmp_path, None, shell, sources, autostart=False)
    said = []
    o.message.connect(said.append)
    try:
        o.open()
        assert not o.ticketmasterReady and o.concerts == []
        o.setConcertPlace("Atlantis")
        assert o.concertPlaceStatus == "looking"
        assert wait_for(lambda: o.concertPlaceStatus == "missing", timeout=10)
        o.setConcertPlace("Lyon")
        assert wait_for(lambda: o.concertPlaceName == "Lyon, France", timeout=10)
        time.sleep(0.3)
        assert asked == []  # (no key yet: nothing asked)
        sources.key = "KEY"
        sources.changed.emit()  # (a key set up: looked up at once)
        assert wait_for(lambda: o.concerts, timeout=10)
        assert {a for a, _k, _r in asked} == {"Aurora", "Bloom"} and asked[0][1:] == ("KEY", 50)
        assert [(c["artist"], c["venue"]) for c in o.concerts] == [("Aurora", "Hall")]
        n = len(asked)
        o.open()
        assert wait_for(lambda: o.busy == "", timeout=10) and len(asked) == n  # (not due again for days)
        o.setConcertRadius(100)  # (somewhere else, as far as what was found goes: asked again)
        assert wait_for(lambda: len(asked) == n + 2, timeout=10) and asked[-1][2] == 100
        o.notInterestedArtist("Aurora")
        assert wait_for(lambda: o.concerts == [], timeout=10)
        shell.features["discoverConcerts"] = False
        shell.featuresChanged.emit()
        o.setConcertRadius(25)
        time.sleep(0.3)
        assert len(asked) == n + 2  # (switched off: nothing asked)
        assert json.dumps(o.concerts) == "[]"
    finally:
        o.shutdown()


def test_a_refused_key_says_so(qapp, db, tmp_path, monkeypatch, settings):  # noqa: F811
    from conftest import wait_for

    from hallucinate.discoveronline import OnlineDiscover

    monkeypatch.setattr(concerts, "geocode", lambda text: {"lat": 1.0, "lon": 2.0, "name": "Here"})
    calls = []

    def refuse(*a, **k):
        calls.append(a[0])
        raise concerts.BadKey("no")
    monkeypatch.setattr(concerts, "shows", refuse)
    o = OnlineDiscover(tmp_path / "lib.db", tmp_path, None, FakeShell(discoverConcerts=True), FakeSources("BAD"),
                       autostart=False)
    said = []
    o.message.connect(said.append)
    try:
        o.open()
        o.setConcertPlace("Here")
        assert wait_for(lambda: said, timeout=10)
        assert "Ticketmaster" in said[0] and len(calls) == 1  # (stops at the first refusal)
    finally:
        o.shutdown()
