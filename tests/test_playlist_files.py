"""Playlist files: reading M3U/M3U8/PLS, writing M3U8, and importing/exporting through the library."""
import os

from hallucinate.core import playlist_files as pf


def test_m3u_with_extinf_relative_absolute_and_urls(tmp_path):
    text = ("﻿#EXTM3U\n#EXTINF:215,Björk - Jóga\nAlbum/01 Jóga.flac\n"
            "/music/abs.mp3\nfile:///music/uri%20song.mp3\nhttp://radio.example/stream\n"
            "Win\\Sub\\track.mp3\n#EXTINF:-1,No Artist Here\nnext.ogg\n")
    entries = pf.parse_m3u(text, str(tmp_path))
    assert entries[0] == {"path": str(tmp_path / "Album" / "01 Jóga.flac"), "artist": "Björk", "title": "Jóga",
                          "duration": 215.0}
    assert [e["path"] for e in entries[1:]] == [
        "/music/abs.mp3", "/music/uri song.mp3", str(tmp_path / "Win" / "Sub" / "track.mp3"), str(tmp_path / "next.ogg")]
    assert entries[-1]["artist"] == "" and entries[-1]["title"] == "No Artist Here" and entries[-1]["duration"] == 0


def test_pls(tmp_path):
    text = "[playlist]\nFile1=a.mp3\nTitle1=Artist - Song\nLength1=100\nFile2=http://x/y\nNumberOfEntries=2\n"
    entries = pf.parse_pls(text, str(tmp_path))
    assert entries == [{"path": str(tmp_path / "a.mp3"), "artist": "Artist", "title": "Song", "duration": 100.0}]


def test_write_round_trip(tmp_path):
    inside = tmp_path / "Music" / "A" / "1.flac"
    outside = "/elsewhere/2.mp3"
    dest = tmp_path / "Music" / "list.m3u8"
    text = pf.write_m3u([{"path": str(inside), "artist": "X", "title": "One", "duration": 61.4},
                         {"path": outside, "artist": "", "title": "Two", "duration": 0}], str(dest))
    assert text.splitlines() == ["#EXTM3U", "#EXTINF:61,X - One", "A/1.flac", "#EXTINF:0,Two", outside]
    dest.parent.mkdir(parents=True)
    dest.write_text(text, encoding="utf-8")
    back = pf.read(str(dest))
    assert [e["path"] for e in back] == [str(inside), outside] and back[0]["title"] == "One"


def test_import_and_export_through_the_library(qapp, tmp_path, db, scan, music):
    from conftest import wait_for

    from hallucinate.userlib import UserLibrary

    scan(music)
    paths = [r[0] for r in db.conn.execute("SELECT path FROM tracks ORDER BY path")]
    moved = tmp_path / "old-drive"
    playlist = tmp_path / "Road trip.m3u"
    lines = ["#EXTM3U", paths[0],  # exact path
             "#EXTINF:10,Aurora Vale - Midnight Rain", str(moved / "x.mp3"),  # moved: found by artist and title
             str(moved / os.path.basename(paths[-1])),  # moved: found by file name
             "/nowhere/missing.flac"]
    playlist.write_text("\n".join(lines), encoding="latin-1")
    ul = UserLibrary(tmp_path / "lib.db")
    results = []
    ul.playlistImported.connect(results.append)
    try:
        ul.importPlaylist(playlist.as_uri())
        assert wait_for(lambda: results)
        r = results[0]
        assert r["name"] == "Road trip" and r["added"] == 3 and r["missing"] == 1 and r["id"] > 0 and not r["error"]
        ul.openPlaylist(r["id"])
        assert wait_for(lambda: ul.playlistTracks.count == 3)
        out = tmp_path / "export"
        assert ul.exportPlaylist("playlist", str(out)) == ""
        exported = pf.read(str(out) + ".m3u8")
        assert len(exported) == 3 and exported[0]["path"] == paths[0]
        assert ul.exportPlaylist("liked", str(tmp_path / "liked.m3u8")) == "There are no songs to export"
        ul.importPlaylist(str(tmp_path / "missing.m3u"))
        assert wait_for(lambda: len(results) == 2) and results[1]["error"]
    finally:
        ul.shutdown()
