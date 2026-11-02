"""Handoff's core: songs described for the other computer, found again in its library, and the link that streams
the ones it doesn't have."""
from hallucinate.core import handoff


def song(**kw):
    base = {"kind": "music", "title": "", "artist": "", "album": "", "album_artist": "", "duration": 0.0,
            "track_no": 0, "disc_no": 0}
    base.update(kw)
    return base


def test_songs_are_found_in_the_other_library(db, scan, music):
    scan(music)
    rows = {r["title"]: r for r in db._rows("SELECT * FROM tracks")}
    wire = [handoff.describe(rows["Midnight Rain"]), handoff.describe(rows["Café Noir"])]
    assert "path" not in wire[0]  # nothing that only means something on the sending computer
    # the other computer's tags differ only in case and accents
    wire[1]["artist"], wire[1]["title"] = "BLUE HARBOR", "Cafe Noir"
    found = handoff.match(db.conn, [handoff.clean(w) for w in wire])
    assert found == [rows["Midnight Rain"]["path"], rows["Café Noir"]["path"]]


def test_a_song_it_doesnt_have_isnt_matched(db, scan, music):
    scan(music)
    wanted = [song(title="Not Here", artist="Nobody"), song(title="Midnight Rain", artist="Aurora Vale",
                                                             album="Live at Somewhere", duration=600)]
    rain = db._rows("SELECT duration FROM tracks WHERE title='Midnight Rain'")[0]["duration"]
    assert rain < 100  # (a short test file: a 10-minute live take on another album is a different recording)
    assert handoff.match(db.conn, wanted) == [None, None]


def test_the_closest_version_wins(db, scan, music):
    scan(music)
    path = db._rows("SELECT path FROM tracks WHERE title='Echoes of Dawn'")[0]["path"]
    got = handoff.match(db.conn, [song(title="echoes of dawn", artist="aurora vale", album="Northern Lights")])
    assert got == [path]


def test_what_arrives_is_checked():
    assert handoff.clean("nope") is None
    assert handoff.clean({"kind": "station", "url": "file:///etc/passwd"}) is None
    s = handoff.clean({"kind": "evil", "title": 5, "duration": "x", "track_no": 1e12, "artist": "A" * 10_000})
    assert s["kind"] == "music" and s["title"] == "" and s["duration"] == 0 and s["track_no"] == 9999
    assert len(s["artist"]) == 300
    st = handoff.clean({"kind": "station", "url": "https://radio.example/stream", "station": "Radio"})
    assert st["url"] == "https://radio.example/stream" and st["station"] == "Radio"


def test_the_handoff_link_expires_and_can_be_revoked():
    now = [0.0]
    link = handoff.HandoffLink("192.168.1.5", ["/a.flac", "/b.flac"], lifetime=10, clock=lambda: now[0])
    assert link.path_for(1) == "/b.flac" and link.path_for(2) is None and link.path_for(-1) is None
    now[0] = 11
    assert link.path_for(0) is None
    link2 = handoff.HandoffLink("192.168.1.5", ["/a.flac"])
    link2.revoke()
    assert link2.path_for(0) is None and len(link2.token) >= 32
