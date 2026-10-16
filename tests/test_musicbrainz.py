"""MusicBrainz album lookup: releases found, a release's tracks paired with an album's songs."""
import pytest

from hallucinate.core import musicbrainz as mb

SEARCH = {"releases": [{"id": "r1", "title": "Northern Lights", "score": 100, "date": "2019-03-01", "country": "GB",
                        "track-count": 2, "artist-credit": [{"name": "Aurora Vale"}],
                        "media": [{"format": "CD", "track-count": 2}],
                        "label-info": [{"label": {"name": "Glow"}}]}]}
RELEASE = {"title": "Northern Lights", "date": "2019-03-01", "artist-credit": [{"name": "Aurora Vale"}],
           "genres": [{"name": "dream pop", "count": 3}, {"name": "pop", "count": 1}],
           "media": [{"position": 1, "tracks": [{"position": 1, "title": "Dawn"}, {"position": 2, "title": "Dusk"}]}]}


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def get(path, params, timeout=15):
        calls.append((path, params))
        return SEARCH if path == "release/" else RELEASE

    monkeypatch.setattr(mb, "_get", get)
    return calls


def test_search_and_release(fake):
    found = mb.search_releases("Aurora Vale", 'Northern "Lights"')
    assert found[0] == {"id": "r1", "title": "Northern Lights", "artist": "Aurora Vale", "year": "2019", "country": "GB",
                        "tracks": 2, "format": "CD", "label": "Glow", "score": 100}
    assert 'release:"Northern \\"Lights\\"" AND artist:"Aurora Vale"' == fake[0][1]["query"]
    rel = mb.release("r1")
    assert rel["genre"] == "Dream Pop" and [t["title"] for t in rel["tracks"]] == ["Dawn", "Dusk"]


def test_tracks_pair_only_when_counts_match():
    tracks = [{"disc": 1, "number": 2, "title": "Dusk"}, {"disc": 1, "number": 1, "title": "Dawn"}]
    songs = [{"path": "/b", "track_no": 2, "disc_no": 0}, {"path": "/a", "track_no": 1, "disc_no": 0}]
    assert [(p, t["title"]) for p, t in mb.match_tracks(songs, tracks)] == [("/a", "Dawn"), ("/b", "Dusk")]
    assert mb.match_tracks(songs[:1], tracks) == []


def test_offline_stops_lookups():
    from hallucinate.core import net

    net.set_offline(True)
    try:
        with pytest.raises(OSError):
            mb._get("release/", {"query": "x"})
    finally:
        net.set_offline(False)
