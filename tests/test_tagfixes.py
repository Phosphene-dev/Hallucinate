"""Library health's "Find all" for albums without a year, albums without track numbers and songs without an
artist or album: what's suggested, and that saving fills only what's still missing."""
from conftest import make_mp3, wait_for

from hallucinate.core import health, tagfixes


def test_years_come_from_the_folder_name_when_it_says_one():
    assert tagfixes.year_from_names(["/m/Pink Floyd/The Wall (1979)/01.flac"]) == 1979
    assert tagfixes.year_from_names(["/m/1997 - OK Computer/a.mp3"]) == 1997
    assert tagfixes.year_from_names(["/m/A - B [2003]/CD1/1 x.flac", "/m/A - B [2003]/CD2/1 y.flac"]) == 2003
    assert tagfixes.year_from_names(["/m/A/B/1 x.flac"]) == 0
    assert tagfixes.year_from_names(["/m/1999 vs 2004/x.flac"]) == 0  # two years: no telling which
    assert tagfixes.year_from_names(["/m/A/Album 3000/x.flac"]) == 0


def test_a_year_online_is_the_earliest_release_that_matches():
    hits = [{"title": "OK Computer", "artist": "Radiohead", "year": "2017", "score": 100},
            {"title": "OK Computer", "artist": "Radiohead", "year": "1997", "score": 95},
            {"title": "OK Computer (Live)", "artist": "Someone", "year": "1990", "score": 90},
            {"title": "Other", "artist": "Radiohead", "year": "1985", "score": 85}]
    assert tagfixes.year_online("Radiohead", "OK Computer", lambda artist, album: hits) == ("1997", "OK Computer")
    assert tagfixes.year_online("Radiohead", "Unknown Album", lambda artist, album: hits) == ("", "")
    assert tagfixes.year_online("Radiohead", "Nothing", lambda artist, album: []) == ("", "")


def test_track_numbers_come_from_file_names_only_when_every_song_has_one():
    songs = [{"path": "/a/1-02 x.flac"}, {"path": "/a/1-01 y.flac"}, {"path": "/a/2-01 z.flac"}]
    assert [(r["disc_no"], r["track_no"]) for r in tagfixes.numbers_from_names(songs)] == [(1, 1), (1, 2), (2, 1)]
    cd2 = [{"path": "/a/CD2/01. x.flac"}, {"path": "/a/CD2/02 y.flac"}]
    assert [(r["disc_no"], r["track_no"]) for r in tagfixes.numbers_from_names(cd2)] == [(2, 1), (2, 2)]
    assert tagfixes.numbers_from_names([{"path": "/a/01 x.mp3"}, {"path": "/a/Bonus.mp3"}]) == []
    assert tagfixes.numbers_from_names([{"path": "/a/01 x.mp3"}, {"path": "/a/01 y.mp3"}]) == []  # the same number twice
    # titles that start with a number aren't track numbers
    assert tagfixes.numbers_from_names([{"path": "/a/99 Problems.mp3"}, {"path": "/a/7 Rings.mp3"}]) == []


def test_track_numbers_online_match_songs_by_title():
    songs = [{"path": "/a/x.mp3", "title": "Airbag"}, {"path": "/a/y.mp3", "title": "Paranoid Android"}]
    hits = [{"id": "short", "title": "OK Computer", "tracks": 1, "score": 100},
            {"id": "r1", "title": "OK Computer", "tracks": 2, "score": 99}]
    full = {"title": "OK Computer", "discs": 1, "tracks": [{"disc": 1, "number": 2, "title": "Paranoid Android"},
                                                           {"disc": 1, "number": 1, "title": "Airbag"}]}
    asked = []

    def release(rid):
        asked.append(rid)
        return full

    tracks, note = tagfixes.numbers_online("Radiohead", "OK Computer", songs, lambda a, b: hits, release)
    assert asked == ["r1"] and note == "OK Computer"
    assert [(t["path"], t["track_no"], t["disc_no"]) for t in tracks] == [("/a/x.mp3", 1, 0), ("/a/y.mp3", 2, 0)]
    songs[1]["title"] = "Something else"
    assert tagfixes.numbers_online("Radiohead", "OK Computer", songs, lambda a, b: hits, release) == ([], "")


def test_artist_and_album_are_guessed_from_folders_and_file_names():
    roots = ["/m"]
    guess = tagfixes.guess_from_path
    assert guess("/m/Pink Floyd/The Wall (1979)/01 - In the Flesh.flac", roots) == {"artist": "Pink Floyd", "album": "The Wall"}
    assert guess("/m/Pink Floyd - The Wall [FLAC]/CD2/03 x.flac", roots) == {"artist": "Pink Floyd", "album": "The Wall"}
    assert guess("/m/Downloads/Artist X - Song.mp3", roots) == {"artist": "Artist X", "album": ""}
    assert guess("/m/loose.mp3", roots) == {"artist": "", "album": ""}
    assert guess("/m/Björk/Post/04. Hyper-Ballad.mp3", roots) == {"artist": "Björk", "album": "Post"}
    assert guess("/m/Weezer/Weezer/01 x.mp3", roots) == {"artist": "Weezer", "album": "Weezer"}  # self-titled


def test_only_the_missing_tag_is_guessed_and_songs_are_grouped_by_folder():
    unknown_a, unknown_b = health.UNKNOWN_ARTIST, health.UNKNOWN_ALBUM
    songs = [{"path": "/m/Band/Record/1.mp3", "artist": unknown_a, "album": unknown_b},
             {"path": "/m/Band/Record/2.mp3", "artist": unknown_a, "album": unknown_b},
             {"path": "/m/Band/Record/3.mp3", "artist": "Guest", "album": unknown_b},
             {"path": "/m/loose.mp3", "artist": unknown_a, "album": unknown_b}]
    groups = tagfixes.untagged_groups(songs, ["/m"])
    assert [(g["artist"], g["album"], len(g["paths"])) for g in groups] == [("", "Record", 1), ("Band", "Record", 2)]


def _editor(tmp_path, folders):
    from hallucinate.core.db import Database
    from hallucinate.core.scanner import Scanner
    from hallucinate.metaedit import MetadataEditor

    db = Database(tmp_path / "lib.db")
    (tmp_path / "art").mkdir(exist_ok=True)
    Scanner(db, tmp_path / "art").scan([str(f) for f in folders])
    db.close()
    return MetadataEditor(tmp_path / "lib.db", tmp_path / "art")


def _counts(tmp_path):
    from hallucinate.core.db import Database

    db = Database(tmp_path / "lib.db")
    try:
        return {c["id"]: c["count"] for c in health.report(db)["checks"]}
    finally:
        db.close()


def test_found_years_numbers_and_tags_are_written_once_kept(qapp, tmp_path):
    root = tmp_path / "Music"
    album = root / "Aurora Vale" / "Northern Lights (2004)"
    loose = root / "Blue Harbor" / "Tidal"
    album.mkdir(parents=True)
    loose.mkdir(parents=True)
    make_mp3(album / "01 - Echoes.mp3", "Echoes", "Aurora Vale", "Northern Lights", "Aurora Vale")
    make_mp3(album / "02 - Rain.mp3", "Rain", "Aurora Vale", "Northern Lights", "Aurora Vale")
    make_mp3(loose / "Tide.mp3", "Tide")
    ed = _editor(tmp_path, [root])
    finished = []
    ed.fixesFinished.connect(finished.append)
    try:
        before = _counts(tmp_path)
        assert before["year"] >= 1 and before["numbers"] == 1 and before["untagged"] == 1
        for kind in ("year", "numbers", "untagged"):
            finished.clear()
            ed._fetch_fixes(kind, online=False)  # (on this thread: offline, so names only)
            assert wait_for(lambda: finished)
            found = ed.fixProposals
            if kind == "year":
                assert [(p["title"], p["year"], p["source"]) for p in found] == [("Northern Lights", 2004, "names")]
            elif kind == "numbers":
                assert [t["track_no"] for t in found[0]["tracks"]] == [1, 2]
            else:
                assert [(p["artist"], p["album"], p["songs"]) for p in found] == [("Blue Harbor", "Tidal", 1)]
            saved = []
            ed.saved.connect(saved.append)
            ed.saveFixes(found)
            assert wait_for(lambda: saved and not ed.fixesSaving)
            ed.saved.disconnect(saved.append)
            assert ed.fixProposals == []
        after = _counts(tmp_path)
        assert after["numbers"] == 0 and after["untagged"] == 0 and after["year"] < before["year"]
    finally:
        ed.shutdown()


def test_saving_leaves_alone_what_you_have_set_since_the_lookup(qapp, tmp_path):
    from mutagen.id3 import ID3, TDRC

    root = tmp_path / "Music"
    album = root / "Band" / "Record (1999)"
    album.mkdir(parents=True)
    make_mp3(album / "01 a.mp3", "A", "Band", "Record", "Band")
    make_mp3(album / "02 b.mp3", "B", "Band", "Record", "Band")
    ed = _editor(tmp_path, [root])
    finished = []
    ed.fixesFinished.connect(finished.append)
    try:
        ed._fetch_fixes("year", online=False)
        assert wait_for(lambda: finished)
        found = ed.fixProposals
        assert found and found[0]["year"] == 1999
        # meanwhile you set it yourself
        for f in album.iterdir():
            tags = ID3(f)
            tags.add(TDRC(encoding=3, text="1998"))
            tags.save(f)
        from hallucinate.core.db import Database
        from hallucinate.core.scanner import Scanner

        db = Database(tmp_path / "lib.db")
        Scanner(db, tmp_path / "art").refresh_files([str(f) for f in album.iterdir()])
        db.close()
        ed.saveFixes(found)
        assert wait_for(lambda: not ed.fixesSaving)
        assert all(str(ID3(f)["TDRC"].text[0]) == "1998" for f in album.iterdir())
    finally:
        ed.shutdown()


def test_a_year_in_the_album_folder_above_cd_folders_counts_for_every_disc():
    assert tagfixes.year_from_names(["/m/A - B [2003]/CD1/1 x.flac", "/m/A - B [2003]/CD2/1 y.flac"]) == 2003
    assert tagfixes.year_from_names(["/m/A - B (1999)/Disc 2/1 y.flac"]) == 1999


def test_each_check_keeps_what_it_found_until_reviewed(qapp, tmp_path):
    """Finding track numbers doesn't throw away years found and not reviewed yet: each check keeps its own,
    and Review brings that check's up."""
    from conftest import wait_for

    ed = _editor(tmp_path, [])
    try:
        ed._fixes.update(kind="year", proposals=[{"kind": "year", "key": "k", "title": "A", "year": 1999}])
        finished = []
        ed.fixesFinished.connect(finished.append)
        ed._fetch_fixes = lambda kind, online: ed._fixes_progress.emit(
            {"busy": False, "proposals": [{"kind": kind, "key": "n", "title": "B", "tracks": []}], "finished": True})
        ed.findFixes("numbers")
        assert wait_for(lambda: finished)
        assert ed.fixCounts == {"year": 1, "numbers": 1} and ed.fixKind == "numbers"
        ed.reviewFixes("year")
        assert ed.fixKind == "year" and [p["title"] for p in ed.fixProposals] == ["A"]
        assert ed.fixCounts == {"year": 1, "numbers": 1}
        ed.clearFixProposals()
        assert ed.fixCounts == {"numbers": 1}
    finally:
        del ed._fetch_fixes
        ed.shutdown()
