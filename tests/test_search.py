import pytest


def test_prefix_and_multi_token(db, scan, music):
    scan(music)
    assert [t["title"] for t in db.search("mid")["tracks"]] == ["Midnight Rain"]
    assert [t["title"] for t in db.search("rain aurora")["tracks"]] == ["Midnight Rain"]
    assert db.search("zzz") == {"tracks": [], "albums": [], "artists": []}
    assert db.search("   ")["tracks"] == []


def test_diacritics_insensitive(db, scan, music):
    scan(music)
    assert db.search("cafe")["tracks"][0]["title"] == "Café Noir"


def test_grouped_results(db, scan, music):
    scan(music)
    r = db.search("aur")
    assert [a["name"] for a in r["artists"]] == ["Aurora Vale"]
    assert [a["album"] for a in r["albums"]] == ["Northern Lights"]  # via album artist
    assert len(r["tracks"]) == 2
    r = db.search("tidal")
    assert r["albums"][0]["album"] == "Tidal" and r["tracks"][0]["album"] == "Tidal"


def test_special_characters_are_safe(db, scan, music):
    scan(music)
    for q in ['"', "*", "50%", "a_b", "AND OR NOT", "(", "'; DROP TABLE tracks;--"]:
        db.search(q)
    assert db.counts()["tracks"] == 4


def test_artist_pages(db, scan, music):
    scan(music)
    assert [a["album"] for a in db.artist_albums("aurora vale")] == ["Northern Lights"]
    assert len(db.artist_tracks("Aurora Vale")) == 2
    assert [a["name"] for a in db.artists()][:2] == ["Aurora Vale", "Blue Harbor"]


@pytest.mark.parametrize("q", ["s", "so", "album 9", "artist 12", "caf", "zzz", "album 1 artist", "123", "ä"])
def test_in_memory_album_and_artist_search_matches_the_database(tmp_path, q):
    """Library searches albums and artists in memory (fast on huge libraries); it must find the same ones, in
    the same order, as the database query it replaces."""
    from test_library_robust import _bulk

    from hallucinate.core.db import Database, group_index, search_groups

    db = Database(tmp_path / "s.db")
    _bulk(db, 3000)
    db.finalize()
    want = db.search(q)
    albums, artists = search_groups(group_index(db.albums(), db.artists()), q)
    assert [a["album_key"] for a in albums] == [a["album_key"] for a in want["albums"]]
    assert [a["name"] for a in artists] == [a["name"] for a in want["artists"]]
    db.close()
