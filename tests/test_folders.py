"""Folder view: listing a level of the library, breadcrumbs, and playing a folder."""
import os

from hallucinate.core import folders


def add(db, path, track=1, disc=0, duration=60.0, art=None):
    db.upsert_track({
        "path": path, "mtime": 0, "size": 1, "title": os.path.basename(path), "artist": "A", "album_artist": "A",
        "aa_tag": 1, "album": "B", "album_key": "A|B", "track_no": track, "disc_no": disc, "year": 2000,
        "genre": "", "duration": duration, "fmt": "FLAC", "codec": "FLAC", "bitrate": 0, "sample_rate": 44100,
        "art": art,
    })


def p(*parts):
    return os.path.join(os.sep, "m", *parts)


def library(db):
    add(db, p("Music", "Artist", "Album", "02.flac"), track=2)
    add(db, p("Music", "Artist", "Album", "01.flac"), track=1, art="/art/x.jpg")
    add(db, p("Music", "Artist", "Album", "CD2", "01.flac"), track=1, disc=2)
    add(db, p("Music", "loose.flac"), duration=30.0)
    add(db, p("Music2", "other.flac"))  # a sibling whose name starts the same isn't inside Music
    add(db, p("Musicals", "show.flac"))


def test_roots_list_the_library_folders(db):
    library(db)
    data = folders.contents(db, "", [p("Music"), p("Music2") + os.sep])
    assert [(f["name"], f["songs"], f["root"]) for f in data["folders"]] == [("Music", 4, True), ("Music2", 1, True)]
    assert data["folders"][0]["art"] == "/art/x.jpg" and data["folders"][0]["duration"] == 210.0
    assert data["crumbs"] == [] and data["tracks"] == []


def test_a_level_has_subfolders_tracks_and_breadcrumbs(db):
    library(db)
    roots = [p("Music")]
    top = folders.contents(db, p("Music"), roots)
    assert [(f["name"], f["songs"]) for f in top["folders"]] == [("Artist", 3)]
    assert [t["path"] for t in top["tracks"]] == [p("Music", "loose.flac")]
    assert top["parent"] == "" and [c["name"] for c in top["crumbs"]] == ["Music"]

    album = folders.contents(db, p("Music", "Artist", "Album") + os.sep, roots)
    assert album["path"] == p("Music", "Artist", "Album") and album["parent"] == p("Music", "Artist")
    assert [t["track_no"] for t in album["tracks"]] == [1, 2]
    assert [(f["name"], f["path"]) for f in album["folders"]] == [("CD2", p("Music", "Artist", "Album", "CD2"))]
    assert [(c["name"], c["path"]) for c in album["crumbs"]] == [
        ("Music", p("Music")), ("Artist", p("Music", "Artist")), ("Album", p("Music", "Artist", "Album"))]

    gone = folders.contents(db, p("Music", "Nowhere"), roots)
    assert gone["folders"] == [] and gone["tracks"] == []


def test_tracks_below_go_folder_by_folder(db):
    library(db)
    assert [os.path.relpath(t["path"], p("Music")) for t in folders.tracks_below(db, p("Music"))] == [
        "loose.flac",
        os.path.join("Artist", "Album", "01.flac"),
        os.path.join("Artist", "Album", "02.flac"),
        os.path.join("Artist", "Album", "CD2", "01.flac"),
    ]


def test_library_folder_slots(qapp, tmp_path, scan, music):
    from conftest import wait_for

    from hallucinate.library import Library

    scan(music)
    lib = Library(tmp_path / "lib.db", tmp_path / "art")
    try:
        assert wait_for(lambda: lib.artistCount >= 2)
        lib._db.add_folder(str(music))
        roots = lib.folderContents("")
        assert [f["name"] for f in roots["folders"]] == ["Music"] and roots["folders"][0]["durText"]
        data = lib.folderContents(str(music / "Aurora Vale" / "Northern Lights"))
        assert [t["title"] for t in data["tracks"]] == ["Echoes of Dawn", "Midnight Rain"]
        assert "artUrl" in data["tracks"][0]
        assert [c["name"] for c in data["crumbs"]] == ["Music", "Aurora Vale", "Northern Lights"]
    finally:
        lib.shutdown()
