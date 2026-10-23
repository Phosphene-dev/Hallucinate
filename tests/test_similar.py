"""Similar artists from Last.fm on an artist's page: off until switched on, kept a month, split into those you
have and those to discover, and a mix of the artist with the ones you have."""
import pytest
from conftest import wait_for

from hallucinate.core import lastfm


class Sources:
    fetchSimilar = True

    def __init__(self, key="k"):
        self.key = key

    def lastfm_key(self):
        return self.key


class Library:
    def artistInfo(self, name):
        have = {"boards of canada": {"name": "Boards of Canada", "albums": 3, "tracks": 40, "artUrl": ""}}
        return have.get(name.lower(), {"name": name, "albums": 0, "tracks": 0, "artUrl": ""})


def test_last_fms_answer_is_read():
    data = {"similarartists": {"artist": [{"name": "Boards of Canada", "match": "1"},
                                          {"name": "boards of canada", "match": "0.9"},
                                          {"name": "Autechre", "match": "0.8"}, {"name": ""}]}}
    import hallucinate.core.lastfm as lf

    old = lf._get
    lf._get = lambda method, params, key, timeout=15: data
    try:
        assert lastfm.similar_artists("Aphex Twin", "k") == [{"name": "Boards of Canada", "match": 1.0},
                                                              {"name": "Autechre", "match": 0.8}]
        assert lastfm.similar_artists("Aphex Twin", "") == []  # no key, no ask
    finally:
        lf._get = old


@pytest.fixture
def similar(qapp, tmp_path, monkeypatch):
    from hallucinate.similar import SimilarArtists

    asked = []

    def fake(name, key):
        asked.append(name)
        return [{"name": "Boards of Canada", "match": 1.0}, {"name": "Autechre", "match": 0.7}]

    monkeypatch.setattr(lastfm, "similar_artists", fake)
    s = SimilarArtists(tmp_path / "lib.db", Sources(), Library())
    s.asked = asked
    yield s
    s.shutdown()


def test_similar_artists_are_split_into_yours_and_ones_to_discover(similar):
    assert similar.similar("Aphex Twin")["on"] and not similar.similar("Aphex Twin")["asked"]
    similar.ensure("Aphex Twin")
    assert wait_for(lambda: similar.similar("Aphex Twin")["asked"])
    found = similar.similar("aphex twin")
    assert [a["name"] for a in found["have"]] == ["Boards of Canada"]
    assert [a["name"] for a in found["discover"]] == ["Autechre"]
    assert found["discover"][0]["url"] == "https://www.last.fm/music/Autechre"
    similar.ensure("Aphex Twin")  # kept for a month: not asked again
    similar.ensure("Various Artists")  # not an artist
    assert similar.asked == ["Aphex Twin"]


def test_nothing_is_asked_while_off_offline_or_without_a_key(similar):
    from hallucinate.core import net

    similar._sources.fetchSimilar = False
    similar.ensure("Aphex Twin")
    similar._sources.fetchSimilar = True
    similar._sources.key = ""
    similar.ensure("Aphex Twin")
    assert not similar.similar("Aphex Twin")["on"]
    similar._sources.key = "k"
    net.set_offline(True)
    try:
        similar.ensure("Aphex Twin")
    finally:
        net.set_offline(False)
    assert similar.asked == []


def test_a_mix_takes_turns_between_the_artists(qapp, tmp_path):
    from hallucinate.core.db import Database
    from hallucinate.library import Library as Lib

    d = Database(tmp_path / "lib.db")
    n = 0
    for artist in ("A", "B"):
        for i in range(10):
            n += 1
            d.upsert_track({"path": f"/m/{artist}{i}", "mtime": 0, "size": 1, "title": f"{artist}{i}", "artist": artist,
                            "album_artist": artist, "aa_tag": 1, "album": artist, "album_key": artist, "track_no": i,
                            "disc_no": 0, "year": 0, "genre": "", "duration": 60, "fmt": "FLAC", "codec": "FLAC",
                            "bitrate": 0, "sample_rate": 0})
    d.commit()
    d.close()
    played = []

    class Player:
        def playList(self, tracks, index):
            played.extend(tracks)

    lib = Lib(tmp_path / "lib.db", tmp_path / "art")
    try:
        lib._player = Player()
        lib.playArtistMix(["A", "B", "Nobody"])
        assert len(played) == 16
        firsts = {played[0]["artist"], played[1]["artist"]}
        assert firsts == {"A", "B"}  # one of each before either comes again
    finally:
        lib.shutdown()
