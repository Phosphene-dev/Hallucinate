"""Artist bios: yours always wins, one looked up online is kept, and you choose where it comes from."""
import pytest
from conftest import wait_for

from hallucinate import bios
from hallucinate.core import discogs, lastfm, musicbrainz, net, wikipedia
from hallucinate.core.db import Database


class Sources:
    """A stand-in for OnlineSources."""
    def __init__(self, fetch=True, first="", lastfm_key="", token=""):
        self.fetchBios, self.bioSource, self._key, self._token = fetch, first, lastfm_key, token

    @property
    def bioSources(self):
        return [{"name": "Wikipedia", "ready": True}, {"name": "Last.fm", "ready": bool(self._key)},
                {"name": "Discogs", "ready": bool(self._token)}]

    def discogs_token(self, wait=0):
        return self._token

    def lastfm_key(self):
        return self._key


@pytest.fixture
def library(tmp_path):
    db = Database(tmp_path / "lib.db")
    db.upsert_track({
        "path": "/m/1", "mtime": 0, "size": 1, "title": "Roygbiv", "artist": "Boards of Canada",
        "album_artist": "Boards of Canada", "aa_tag": 1, "album": "Music Has the Right to Children",
        "album_key": "boc|mhtrtc", "track_no": 1, "disc_no": 0, "year": 1998, "genre": "IDM", "duration": 100,
        "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 44100,
    })
    db.commit()
    db.close()
    return tmp_path / "lib.db"


def test_the_first_source_with_a_bio_is_used(monkeypatch):
    asked = []
    monkeypatch.setattr(wikipedia, "artist_bio", lambda n, a, lang: asked.append("w"))
    monkeypatch.setattr(lastfm, "artist_bio", lambda n, key, lang: asked.append("l") or
                        {"text": "From Last.fm", "url": "https://last.fm/x", "source": "Last.fm"})
    got = bios.lookup("BoC", "MHTRTC", ["Wikipedia", "Last.fm", "Discogs"], lastfm_key="k")
    assert got["source"] == "Last.fm" and asked == ["w", "l"]
    assert bios.lookup("BoC", "", ["Discogs"]) is None  # no token: nothing asked, nothing found


def test_a_bio_is_fetched_once_and_yours_always_wins(qapp, library, monkeypatch):
    calls = []
    monkeypatch.setattr(bios, "lookup", lambda name, album, order, *a: calls.append((name, album, order)) or
                        {"text": "Scottish duo.", "url": "https://en.wikipedia.org/wiki/BoC", "source": "Wikipedia"})
    ab = bios.ArtistBios(library, Sources())
    try:
        ab.ensure("Boards of Canada")
        assert wait_for(lambda: ab.bio("boards of canada")["text"] == "Scottish duo.")
        assert calls == [("Boards of Canada", "Music Has the Right to Children", ["Wikipedia"])]
        ab.ensure("Boards of Canada")  # already there: not asked again
        assert len(calls) == 1
        ab.setOwn("Boards of Canada", "  Mine.  ")
        b = ab.bio("Boards of Canada")
        assert b["text"] == "Mine." and b["own"] and b["source"] == "" and b["fetchedText"] == "Scottish duo."
        ab.setOwn("Boards of Canada", "")
        assert ab.bio("Boards of Canada")["text"] == "Scottish duo."
        ab.ensure("Various Artists")
        assert len(calls) == 1
    finally:
        ab.shutdown()


def test_a_chosen_source_is_the_only_one_asked(qapp, library, monkeypatch):
    calls = []
    monkeypatch.setattr(bios, "lookup", lambda name, album, order, *a: calls.append(order) or None)
    ab = bios.ArtistBios(library, Sources(token="t"))
    try:
        ab.pick("Boards of Canada", "Discogs")
        assert wait_for(lambda: calls == [["Discogs"]])
        assert wait_for(lambda: not ab.bio("Boards of Canada")["busy"])
        assert ab.bio("Boards of Canada")["picked"] == "Discogs"
        ab.pick("Boards of Canada", "Last.fm")  # not set up: nothing asked
        assert calls == [["Discogs"]]
    finally:
        ab.shutdown()


def test_no_lookups_offline_or_switched_off(qapp, library, monkeypatch):
    calls = []
    monkeypatch.setattr(bios, "lookup", lambda *a: calls.append(a))
    ab = bios.ArtistBios(library, Sources(fetch=False))
    try:
        ab.ensure("Boards of Canada")
        net.set_offline(True)
        ab.refresh("Boards of Canada")
        assert calls == []
    finally:
        net.set_offline(False)
        ab.shutdown()


def test_a_network_failure_isnt_remembered_as_no_bio(qapp, library, monkeypatch):
    def down(*a):
        raise OSError("down")

    monkeypatch.setattr(bios, "lookup", down)
    ab = bios.ArtistBios(library, Sources())
    try:
        ab.ensure("Boards of Canada")
        assert wait_for(lambda: not ab.bio("Boards of Canada")["busy"])
        assert ab._row("boards of canada") is None
    finally:
        ab.shutdown()


def test_wikipedia_finds_the_article_through_musicbrainz(monkeypatch):
    def mb(path, params, timeout=15):
        if path == "release/":
            return {"releases": [{"score": 100, "title": "Music Has the Right to Children",
                                  "artist-credit": [{"name": "Boards of Canada", "artist": {"id": "boc", "name": "Boards of Canada"}}]}]}
        assert path == "artist/boc"
        return {"relations": [{"type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q123"}}]}

    fetched = []

    def fetch(url, timeout=15):
        fetched.append(url)
        if "wikidata" in url:
            return {"entities": {"Q123": {"sitelinks": {"enwiki": {"title": "Boards of Canada"}}}}}
        return {"query": {"pages": {"1": {"title": "Boards of Canada", "extract": "Boards of Canada are a duo."}}}}

    monkeypatch.setattr(musicbrainz, "_get", mb)
    monkeypatch.setattr(wikipedia, "_fetch", fetch)
    got = wikipedia.artist_bio("Boards of Canada", "Music Has the Right to Children", "en")
    assert got == {"text": "Boards of Canada are a duo.", "url": "https://en.wikipedia.org/wiki/Boards_of_Canada",
                   "source": "Wikipedia"}


def test_discogs_bio_is_found_through_an_album(monkeypatch):
    def get(path, params, token, timeout=15):
        if path == "database/search":
            return {"results": [{"title": "Boards Of Canada - Geogaddi", "type": "master", "id": 7}]}
        if path == "masters/7":
            return {"artists": [{"name": "Boards Of Canada", "id": 42}]}
        assert path == "artists/42"
        return {"profile": "Scottish duo, [a=Mike Sandison] and [a=Marcus Eoin].", "uri": "https://www.discogs.com/artist/42"}

    monkeypatch.setattr(discogs, "_get", get)
    got = discogs.artist_bio("Boards of Canada", "t", "Geogaddi")
    assert got["text"] == "Scottish duo, Mike Sandison and Marcus Eoin." and got["source"] == "Discogs"


def test_your_bios_are_in_backups(tmp_path, library):
    from hallucinate.core import backup

    db = Database(library)
    db.conn.execute("INSERT INTO artist_bios(s_aa, own, text) VALUES('boc', 'Mine', 'fetched')")
    db.conn.execute("INSERT INTO artist_bios(s_aa, text) VALUES('other', 'fetched only')")
    db.commit()
    db.close()
    backup.export(library, None, tmp_path / "b.json.gz")
    data = backup.read(tmp_path / "b.json.gz")
    assert [r["s_aa"] for r in data["artist_bios"]] == ["boc"]  # fetched bios are fetched again
    fresh = tmp_path / "fresh.db"
    Database(fresh).close()
    backup.restore({"format": "hallucinate-backup", "version": 1,
                    "artist_bios": [{"s_aa": "boc", "own": "Mine", "picked": ""}]}, fresh, None)
    db = Database(fresh)
    assert db.conn.execute("SELECT own FROM artist_bios WHERE s_aa='boc'").fetchone()[0] == "Mine"
    db.close()


def test_genre_text_with_commas_and_old_rules_still_match():
    from hallucinate.core import genres

    assert genres.split("Folk, World, & Country; Blues") == ["Folk, World, & Country", "Blues"]
    assert genres.has("Rock/Pop", "Rock/Pop") and genres.has("Rock/Pop", "pop")
    assert genres.key("Hip-Hop") == genres.key("hip hop") == genres.key("HipHop")


def test_a_chosen_default_source_is_the_only_one_asked(qapp, library, monkeypatch):
    calls = []
    monkeypatch.setattr(bios, "lookup", lambda name, album, order, *a: calls.append(order) or None)
    ab = bios.ArtistBios(library, Sources(first="Wikipedia", lastfm_key="k", token="t"))
    try:
        ab.ensure("Boards of Canada")
        assert wait_for(lambda: calls == [["Wikipedia"]])
        assert wait_for(lambda: not ab.bio("Boards of Canada")["busy"])
        ab.pick("Boards of Canada", "Discogs")
        assert wait_for(lambda: len(calls) == 2 and not ab.bio("Boards of Canada")["busy"])
        ab.ensure("Boards of Canada")  # Discogs had nothing a moment ago: not asked again on every visit
        assert len(calls) == 2
    finally:
        ab.shutdown()


def test_a_late_keyring_answer_doesnt_undo_a_disconnect(qapp, monkeypatch):
    import keyring

    from hallucinate.onlinesources import OnlineSources

    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring, name, lambda *_: None)
    src = OnlineSources(lambda: "")
    src.forgetDiscogs()
    src._apply_keyring({"values": {"token": "old", "user": "me"}, "error": ""})
    assert not src.discogsConnected
