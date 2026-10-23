"""Several genres per album (the main one first): reading and writing them, filtering and smart playlists by
any of them, and finding them on MusicBrainz, Discogs and Last.fm."""
import mutagen
import pytest
from audio import FFMPEG, encode

from hallucinate.core import discogs, genrefinder, genres, lastfm, musicbrainz, tagedit
from hallucinate.core import rules as R
from hallucinate.core.tags import read_track

needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")


def test_a_genre_text_is_split_into_its_genres_main_one_first():
    assert genres.split("IDM; Ambient;  Electronic") == ["IDM", "Ambient", "Electronic"]
    assert genres.split("Rock/Pop") == ["Rock", "Pop"]
    assert genres.split(["Hip-Hop; Rap", "rap", "Trip Hop"]) == ["Hip-Hop", "Rap", "Trip Hop"]
    assert genres.split("") == [] and genres.main("") == ""
    assert genres.join(["Shoegaze", "Dream Pop", "shoegaze"]) == "Shoegaze; Dream Pop"
    assert genres.main("Jazz; Hard Bop") == "Jazz"
    assert genres.has("Jazz; Hard Bop", "hard bop") and genres.has("Électronique", "electronique")
    assert not genres.has("Jazz; Hard Bop", "Bop") and not genres.has("Jazz", "")


@pytest.mark.parametrize("ext", ["mp3", "flac", "ogg", "opus", "m4a", "wma", "wv"])
@needs_ffmpeg
def test_several_genres_are_written_as_separate_values_and_read_back(tmp_path, ext):
    path = encode(tmp_path / f"song.{ext}", ext, seconds=0.5, title="Song")
    tagedit.write_tags(str(path), {"genre": "IDM; Ambient; Electronic"})
    assert read_track(str(path))["genre"] == "IDM; Ambient; Electronic"
    f = mutagen.File(path)
    if ext == "flac" or ext in ("ogg", "opus"):
        assert f.tags["GENRE"] == ["IDM", "Ambient", "Electronic"]  # other players see three genres
    tagedit.write_tags(str(path), {"genre": "Ambient"})
    assert read_track(str(path))["genre"] == "Ambient"


def _add(db, path, genre):
    db.upsert_track({
        "path": path, "mtime": 0, "size": 1, "title": path, "artist": "A", "album_artist": "A", "aa_tag": 1,
        "album": "LP", "album_key": "a|lp", "track_no": 0, "disc_no": 0, "year": 2000, "genre": genre,
        "duration": 100, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 44100,
    })


def test_filters_and_smart_playlists_match_any_of_a_songs_genres(db):
    _add(db, "/m/1", "IDM; Ambient")
    _add(db, "/m/2", "Ambient")
    _add(db, "/m/3", "Ambient Techno")
    db.commit()
    assert db.all_genres() == ["Ambient", "Ambient Techno", "IDM"]
    assert {t["path"] for t in db.filtered_tracks(genre="ambient")} == {"/m/1", "/m/2"}
    rule = {"match": "all", "rules": [{"field": "genre", "op": "is", "value": "Ambient"}]}
    assert {t["path"] for t in R.matching_tracks(db, rule)} == {"/m/1", "/m/2"}
    rule["rules"][0]["op"] = "is_not"
    assert {t["path"] for t in R.matching_tracks(db, rule)} == {"/m/3"}


def test_an_albums_genres_rank_by_how_many_songs_carry_them(db):
    from hallucinate.core import albums

    _add(db, "/m/1", "IDM; Ambient")
    _add(db, "/m/2", "Ambient; IDM")
    _add(db, "/m/3", "Ambient")
    db.commit()
    assert albums.liner_notes(db, "a|lp")["genres"][:2] == ["Ambient", "IDM"]


def test_discogs_styles_come_before_its_broad_genres():
    assert discogs.genre_list(["Downtempo", "Trip Hop"], ["Electronic", "Funk / Soul"]) == \
        ["Downtempo", "Trip Hop", "Electronic", "Funk", "Soul"]
    assert discogs.genre_list([], ["Folk, World, & Country", "Non-Music"]) == ["Folk", "World", "Country"]
    assert discogs.plain_profile("[b]Founded[/b] by [a=Aphex Twin (2)] on [l=Warp]. [a12345] [url=http://x]site[/url]") \
        == "Founded by Aphex Twin on Warp.  site".replace("  ", " ")


def test_discogs_finds_an_album_by_its_title_and_artist(monkeypatch):
    asked = []

    def get(path, params, token, timeout=15):
        asked.append((path, dict(params or {}), token))
        if params.get("type") == "master":
            return {"results": [{"title": "Other - Thing", "style": ["Rock"], "genre": ["Rock"]},
                                {"title": "Boards Of Canada* - Music Has The Right To Children", "type": "master",
                                 "id": 1, "style": ["IDM", "Downtempo"], "genre": ["Electronic"]}]}
        return {"results": []}

    monkeypatch.setattr(discogs, "_get", get)
    hit = discogs.find_genre("Boards of Canada", "Music Has the Right to Children", "tok")
    assert hit["genres"] == ["IDM", "Downtempo", "Electronic"] and hit["genre"] == "IDM"
    assert asked[0][2] == "tok"
    assert discogs.find_genre("Boards of Canada", "Music Has the Right to Children", "") is None  # no token, no ask
    assert len(asked) == 1


def test_only_last_fm_tags_that_are_genres_are_kept():
    tags = [{"name": "electronic", "count": 100}, {"name": "seen live", "count": 90},
            {"name": "albums i own", "count": 50}, {"name": "idm", "count": 40}, {"name": "2009", "count": 30},
            {"name": "Boards of Canada", "count": 30}, {"name": "ambient", "count": 5}]
    assert lastfm.filter_tags(tags, artist="Boards of Canada") == ["Electronic", "IDM"]
    known = {"electronic", "ambient"}
    assert lastfm.filter_tags(tags, known=known) == ["Electronic"]  # IDM isn't on that list; ambient too few


def test_last_fm_bios_lose_their_link_and_markup():
    text = 'Boards of Canada are a <b>Scottish</b> duo.<br/>Formed in 1986 &amp; more. <a href="https://www.last.fm/music/Boards+of+Canada">Read more on Last.fm</a>. User-contributed text is available under the Creative Commons By-SA License'
    assert lastfm.plain_bio(text) == "Boards of Canada are a Scottish duo.\nFormed in 1986 & more."


def test_sources_are_combined_with_agreement_ranking_higher(monkeypatch):
    monkeypatch.setattr(musicbrainz, "find_genre", lambda a, b, cache=None:
                        {"genre": "Electronic", "genres": ["Electronic", "IDM"], "source": "album", "release": b})
    monkeypatch.setattr(discogs, "find_genre", lambda a, b, token:
                        {"genre": "IDM", "genres": ["IDM", "Downtempo", "Electronic"], "source": "album", "release": b})
    monkeypatch.setattr(lastfm, "find_genre", lambda a, b, key, known=None:
                        {"genre": "IDM", "genres": ["IDM", "Ambient"], "source": "album", "release": b})
    hit = genrefinder.find("BoC", "MHTRTC", discogs_token="t", lastfm_key="k")
    assert hit["genres"][:2] == ["IDM", "Electronic"] and hit["genre"] == "IDM; Electronic; Downtempo"
    assert hit["sources"] == ["MusicBrainz", "Discogs", "Last.fm"]
    # without a token or key those sources aren't asked
    only = genrefinder.find("BoC", "MHTRTC")
    assert only["sources"] == ["MusicBrainz"] and only["genre"] == "Electronic; IDM"


def test_the_artists_genre_is_only_used_when_no_source_has_the_albums(monkeypatch):
    monkeypatch.setattr(musicbrainz, "find_genre", lambda a, b, cache=None:
                        {"genre": "Rock", "genres": ["Rock"], "source": "artist", "release": b})
    monkeypatch.setattr(discogs, "find_genre", lambda a, b, token:
                        {"genre": "Shoegaze", "genres": ["Shoegaze"], "source": "album", "release": b})
    assert genrefinder.find("A", "B", discogs_token="t")["genre"] == "Shoegaze"
    assert genrefinder.find("A", "B")["source"] == "artist"


def test_a_source_that_fails_doesnt_stop_the_others(monkeypatch):
    def down(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(musicbrainz, "find_genre", down)
    monkeypatch.setattr(discogs, "find_genre", lambda a, b, token:
                        {"genre": "Jazz", "genres": ["Jazz"], "source": "album", "release": b})
    assert genrefinder.find("A", "B", discogs_token="t")["genre"] == "Jazz"
    with pytest.raises(OSError):  # all of them down: not "nothing found"
        genrefinder.find("A", "B")


def test_display_shows_the_main_genre_or_all_of_them(qapp):
    from PySide6.QtGui import QIcon

    from hallucinate.player import Player
    from hallucinate.shell import DesktopShell

    player = Player()
    shell = DesktopShell(qapp, player, QIcon())
    try:
        assert shell.genresText("IDM; Ambient", False) == "IDM"
        assert shell.genresText("IDM; Ambient", True) == "IDM, Ambient"
        assert shell.genresText("", True) == ""
    finally:
        shell.shutdown()
        player.shutdown()


def test_genres_spelled_differently_count_as_one(db):
    import time

    from hallucinate.core import albums, artists, genre_views, recap

    _add(db, "/m/1", "Hip-Hop")
    _add(db, "/m/2", "hip-hop; Jazz")
    _add(db, "/m/3", "Jazz")
    now = time.time()
    for n, p in enumerate(("/m/1", "/m/2", "/m/3")):
        db.record_play(p, now - 10 + n)
    db.commit()
    assert albums.liner_notes(db, "a|lp")["genres"][:2] == ["Hip-Hop", "Jazz"]
    assert artists.profile(db, "A")["genres"][:2] == ["Hip-Hop", "Jazz"]
    period = "month:" + time.strftime("%Y-%m", time.localtime(now - 10))
    assert recap.recap(db, period, now=now)["genres"][:2] == ["Hip-Hop", "Jazz"]
    # the genre page and its songs (with the cheap LIKE test before genre_has)
    assert genre_views.page(db, "HIP-HOP")["tracks"] == 2
    assert {t["path"] for t in genre_views.tracks(db, "jazz")} == {"/m/2", "/m/3"}
    assert genre_views.tracks(db, "hop") == []


def test_genre_prefilter_never_drops_a_match():
    import sqlite3

    for text, name in [("Hip  Hop", "hip hop"), ("Rock/Pop", "Rock/Pop"), ("Électro; IDM", "electro"),
                       ("R_B", "r_b"), ("Folk, World, & Country", "folk, world, & country")]:
        assert genres.has(text, name)
        sql, params = genres.prefilter(name)
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE t(s_genre TEXT)")
        conn.execute("INSERT INTO t VALUES(?)", (genres.fold(text),))
        assert conn.execute(f"SELECT COUNT(*) FROM t WHERE {sql}", params).fetchone()[0] == 1, (text, name)


def test_songs_are_found_by_their_genre_too_names_first(db):
    _add(db, "/m/1", "Shoegaze; Dream Pop")
    _add(db, "/m/2", "Jazz")
    db.upsert_track({**db.track(1), "path": "/m/3", "title": "Shoegaze Song", "genre": "Jazz"})
    db.commit()
    found = [t["path"] for t in db.search("shoegaze", groups=False)["tracks"]]
    assert found[0] == "/m/3" and "/m/1" in found and "/m/2" not in found
    assert [t["path"] for t in db.search("dream pop", groups=False)["tracks"]] == ["/m/1"]


def test_an_old_search_index_without_genres_is_built_again(tmp_path):
    from hallucinate.core.db import Database

    path = tmp_path / "lib.db"
    old = Database(path)
    _add(old, "/m/1", "Krautrock")
    old.conn.execute("DROP TABLE tracks_fts")
    old.conn.execute("CREATE VIRTUAL TABLE tracks_fts USING fts5(title, artist, album)")
    old.conn.execute("INSERT INTO tracks_fts(rowid, title, artist, album) SELECT id, title, artist, album FROM tracks")
    old.commit()
    old.close()
    db = Database(path)
    assert [t["path"] for t in db.search("krautrock", groups=False)["tracks"]] == ["/m/1"]
    db.close()


def test_songs_sort_by_most_played_and_newest(db):
    from hallucinate.core import genre_views

    for p in ("/m/1", "/m/2", "/m/3"):
        _add(db, p, "")
    for _ in range(3):
        db.record_play("/m/2")
    db.record_play("/m/3")
    db.commit()
    songs = db.song_list()
    assert [t["path"] for t in sorted(songs, key=genre_views.song_sort_key("plays", db))] == ["/m/2", "/m/3", "/m/1"]
    assert [t["path"] for t in sorted(songs, key=genre_views.song_sort_key("added"))] == ["/m/3", "/m/2", "/m/1"]


def test_artists_carry_their_plays_and_newest_addition(db):
    _add(db, "/m/1", "")
    db.record_play("/m/1")
    db.record_play("/m/1")
    db.commit()
    (a,) = db.artists()
    assert a["plays"] == 2 and a["added"] > 0 and a["tracks"] == 1


def test_a_playlist_is_copied_and_its_repeats_taken_out(db):
    for p in ("/m/1", "/m/2"):
        _add(db, p, "")
    db.commit()
    pid = db.create_playlist("Mix")
    db.playlist_add(pid, ["/m/2", "/m/1", "/m/2", "/m/1", "/m/2"])
    copy = db.duplicate_playlist(pid, "Mix (copy)")
    assert [t["path"] for t in db.playlist_tracks(copy)] == ["/m/2", "/m/1", "/m/2", "/m/1", "/m/2"]
    assert db.playlist_dedupe(pid) == 3
    assert [t["path"] for t in db.playlist_tracks(pid)] == ["/m/2", "/m/1"]
    assert len(db.playlist_tracks(copy)) == 5  # the copy is its own


def test_a_search_with_a_typo_shows_what_was_probably_meant(db):
    from hallucinate.core.spelling import Speller, distance

    assert distance("radiohed", "radiohead", 2) == 1 and distance("wroks", "works", 2) == 1  # a swap is one
    assert distance("abc", "xyzuvw", 2) == 3
    s = Speller(["Radiohead", "OK Computer", "Boards of Canada", "Béla Bartók", "Beethoven", "Beethoven"])
    assert s.correct("radiohed") == "radiohead"
    assert s.correct("bords of canda") == "boards of canada"
    assert s.correct("bartok") == "" and s.correct("radioh") == ""  # found as it is
    assert s.correct("beethovan") == "beethoven"
    assert s.correct("qqqqqqq") == ""  # nothing close: no suggestion rather than a wild one


def test_the_library_falls_back_to_the_corrected_search(qapp, tmp_path):
    from conftest import wait_for

    from hallucinate.core.db import Database
    from hallucinate.library import Library

    d = Database(tmp_path / "lib.db")
    _add(d, "/m/1", "Shoegaze")
    d.upsert_track({**d.track(1), "path": "/m/2", "title": "Paranoid Android", "artist": "Radiohead"})
    d.commit()
    d.close()
    lib = Library(tmp_path / "lib.db", tmp_path / "art")
    try:
        lib.search("paranoid andriod")
        assert wait_for(lambda: lib.searchResults.get("tracks"))
        assert lib.searchResults["corrected"] == "paranoid android"
        assert [t["path"] for t in lib.searchResults["tracks"]] == ["/m/2"]
        lib.search("paranoid")
        assert wait_for(lambda: lib.searchResults.get("tracks") and "corrected" not in lib.searchResults)
    finally:
        lib.shutdown()
