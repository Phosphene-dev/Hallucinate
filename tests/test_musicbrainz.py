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


def genre_server(monkeypatch, releases, group_genres, artist_genres):
    calls = []

    def get(path, params, timeout=15):
        calls.append(path)
        if path == "release/":
            return {"releases": releases}
        if path.startswith("release-group/"):
            return {"genres": group_genres}
        return {"genres": artist_genres}

    monkeypatch.setattr(mb, "_get", get)
    return calls


def hit(title="Hangable Auto Bulb EP.", artist="AFX", score=100):
    return {"id": "r", "title": title, "score": score, "release-group": {"id": "g1"},
            "artist-credit": [{"name": artist, "artist": {"id": "a1", "name": artist}}]}


def test_genre_names_read_like_tags():
    assert [mb.genre_name(g) for g in ("idm", "drum and bass", "post-rock", "hip hop", "r&b", "lofi")] == \
        ["IDM", "Drum and Bass", "Post-Rock", "Hip Hop", "R&B", "Lo-Fi"]


def test_an_albums_genre_comes_from_its_release_group(monkeypatch):
    calls = genre_server(monkeypatch, [hit()], [{"name": "electronic", "count": 2}, {"name": "idm", "count": 5}], [])
    found = mb.find_genre("AFX", "Hangable Auto Bulb EP")
    assert found["genre"] == "IDM" and found["genres"] == ["IDM", "Electronic"] and found["source"] == "album"
    assert calls == ["release/", "release-group/g1"]


def test_without_album_genres_the_artists_are_used_once(monkeypatch):
    calls = genre_server(monkeypatch, [hit()], [], [{"name": "ambient", "count": 1}])
    cache = {}
    assert mb.find_genre("AFX", "Hangable Auto Bulb", cache)["source"] == "artist"
    assert mb.find_genre("AFX", "Hangable Auto Bulb", cache)["genre"] == "Ambient"
    assert calls.count("artist/a1") == 1


@pytest.mark.parametrize("release", [hit(title="Hangable Auto Bulb Remixed"), hit(artist="Someone Else"),
                                     hit(score=60)])
def test_no_genre_rather_than_a_wrong_one(monkeypatch, release):
    genre_server(monkeypatch, [release], [{"name": "idm", "count": 5}], [{"name": "idm", "count": 5}])
    assert mb.find_genre("AFX", "Hangable Auto Bulb") is None


def test_names_match_across_accents_punctuation_and_editions():
    assert mb._same("Sigur Rós", "Sigur Ros") and mb._same("Simon & Garfunkel", "Simon and Garfunkel")
    assert mb._same("Tidal (Deluxe Edition)", "Tidal") and mb._same("Analogue Bubblebath, Vol 3.1", "Analogue Bubblebath Vol. 3.1")
    assert not mb._same("Tidal", "Tidal Wave")
