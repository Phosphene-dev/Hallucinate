"""Internet radio: playlist files, stream titles, saving stations, playing them, and keeping them out of stats."""
import pytest
from audio import FFMPEG, encode
from conftest import wait_for
from streamserver import StreamServer

from hallucinate.core import stations as st

pytestmark = pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")


@pytest.fixture(scope="module")
def tone(tmp_path_factory):
    path = encode(tmp_path_factory.mktemp("tone") / "tone.mp3", "mp3", seconds=20)
    return path.read_bytes()


@pytest.fixture
def server(tone):
    srv = StreamServer(tone, files={
        "/station.pls": ("audio/x-scpls", b"[playlist]\nFile1=PLACEHOLDER\nTitle1=Pls Radio\nNumberOfEntries=1\n"),
    })
    pls = f"[playlist]\nFile1={srv.url('/live')}\nTitle1=Pls Radio\nNumberOfEntries=1\n".encode()
    srv.files["/station.pls"] = ("audio/x-scpls", pls)
    yield srv
    srv.close()


def test_playlist_files_and_titles():
    pls = "[playlist]\nFile2=http://b/2\nFile1=http://a/1\nTitle1=One\nTitle2=Two\n"
    assert st.parse_playlist(pls) == ["http://a/1", "http://b/2"]
    assert st.playlist_titles(pls) == {"http://a/1": "One", "http://b/2": "Two"}
    m3u = "#EXTM3U\n#EXTINF:-1,Jazz FM\nhttp://j/stream\nnot a link\n"
    assert st.parse_playlist(m3u) == ["http://j/stream"]
    assert st.playlist_titles(m3u) == {"http://j/stream": "Jazz FM"}
    assert st.parse_playlist("#EXTM3U\n#EXT-X-VERSION:3\nseg1.ts\n") == []  # HLS is a stream, not a list
    xspf = "<playlist><trackList><track><location>https://x/y</location></track></trackList></playlist>"
    assert st.parse_playlist(xspf) == ["https://x/y"]


def test_stream_titles():
    assert st.parse_icy_block(b"StreamTitle='Band - Song';StreamUrl='';\0\0") == "Band - Song"
    assert st.split_title("Band - Song") == ("Band", "Song")
    assert st.split_title("Just a jingle") == ("", "Just a jingle")
    assert st.split_title("Test FM", station="Test FM") == ("", "")
    assert st.split_title("  ") == ("", "")


def test_reading_a_live_title_and_resolving_links(server):
    title, headers = st.read_stream_title(server.url("/live"))
    assert title == "Artist One - First Song" and headers["icy-name"] == "Test FM"
    info = st.resolve(server.url("/live"))
    assert info["url"] == server.url("/live") and info["name"] == "Test FM" and info["tags"] == "Ambient"
    assert info["codec"] == "MP3" and info["bitrate"] == 128
    via_playlist = st.resolve(server.url("/station.pls"))
    assert via_playlist["url"] == server.url("/live") and via_playlist["name"] == "Test FM"
    with pytest.raises(OSError):
        st.resolve(server.url("/html"))
    with pytest.raises(OSError):
        st.resolve("ftp://nope")


def test_offline_mode_stops_station_lookups(server):
    from hallucinate.core import net

    net.set_offline(True)
    try:
        with pytest.raises(OSError):
            st.read_stream_title(server.url("/live"))
        with pytest.raises(OSError):
            st.directory_servers()
    finally:
        net.set_offline(False)
    assert not [r for r in server.requests if r.startswith("/live")]


@pytest.fixture
def radio(qapp, tmp_path):
    from hallucinate.player import Player
    from hallucinate.stations import Stations

    player = Player(session_file=tmp_path / "session.json")
    stations = Stations(tmp_path / "streams.db", tmp_path / "cache", player)
    messages = []
    stations.message.connect(messages.append)
    yield stations, player, messages
    stations.shutdown()
    player.shutdown()


def test_saving_playing_and_naming_the_song(radio, server):
    stations, player, messages = radio
    stations.add(server.url("/station.pls"), "")
    assert wait_for(lambda: stations.count == 1), messages
    saved = stations.model._items[0]
    assert saved["name"] == "Test FM" and saved["url"] == server.url("/live") and "128 kbps" in saved["detail"]
    stations.add(server.url("/live"), "")  # the same stream again
    assert wait_for(lambda: any("already saved" in m for m in messages))
    assert stations.count == 1

    played = []
    player.played.connect(played.append)
    stations.play(saved["id"])
    assert wait_for(lambda: player.playing and player.position > 200, timeout=15), player.error
    assert player.current["kind"] == "station" and player.duration == 0 and not player.canSeek
    # the stream title becomes the song: artist and title, with the station kept as the album
    assert wait_for(lambda: player.current.get("artist") == "Artist One", timeout=15)
    assert player.current["title"] == "First Song" and player.current["album"] == "Test FM"
    server.title = "Artist Two - Second Song"
    stations._poll_title()
    assert wait_for(lambda: player.current.get("title") == "Second Song", timeout=15)
    assert not played  # a minute of a song hasn't passed, and stats never get radio
    assert stations.model._items[0]["plays"] == 1


def test_songs_on_the_radio_count_only_for_scrobbling_when_allowed(radio):
    from hallucinate.core.kinds import counts_for_scrobbling

    stations, _player, _ = radio
    entry = {"kind": "station", "artist": "A", "title": "B", "stream_title": "A - B", "scrobble": False}
    assert not counts_for_scrobbling(entry)
    assert counts_for_scrobbling({**entry, "scrobble": True})
    assert not counts_for_scrobbling({**entry, "scrobble": True, "artist": ""})
    assert not counts_for_scrobbling({"kind": "episode", "artist": "A", "title": "B"})
    assert counts_for_scrobbling({"artist": "A", "title": "B"})
    stations.setScrobble(True)
    assert stations.scrobble is True
    stations.setScrobble(False)


def test_user_library_ignores_radio_plays(qapp, tmp_path):
    from hallucinate.core.db import Database
    from hallucinate.player import Player
    from hallucinate.userlib import UserLibrary

    Database(tmp_path / "lib.db").close()
    player = Player(session_file=None)
    user = UserLibrary(tmp_path / "lib.db", player)
    user.recordPlay({"path": "http://x/live", "kind": "station", "artist": "A", "title": "B"})
    user.recordPlay({"path": "/m/song.flac", "kind": "episode"})
    user.shutdown()
    db = Database(tmp_path / "lib.db")
    assert db.conn.execute("SELECT COUNT(*) FROM play_log").fetchone()[0] == 0
    db.close()
    player.shutdown()


def test_a_dropped_station_reconnects(radio, server, monkeypatch):
    from hallucinate import player as player_module

    stations, player, _ = radio
    monkeypatch.setattr(player_module, "STREAM_RETRIES", 3)
    stations.add(server.url("/live"), "Drops")
    assert wait_for(lambda: stations.count == 1)
    stations.play(stations.model._items[0]["id"])
    assert wait_for(lambda: player.playing and player.position > 200, timeout=15), player.error
    before = len([r for r in server.requests if r == "/live"])
    player._reconnect_stream("test drop")
    assert "reconnecting" in player.error
    assert wait_for(lambda: len([r for r in server.requests if r == "/live"]) > before, timeout=10)
    assert wait_for(lambda: player.playing and player.position > 100 and player.error == "", timeout=15), player.error


def test_offline_mode_keeps_stations_quiet(radio, server):
    from hallucinate.core import net

    stations, player, messages = radio
    stations.add(server.url("/live"), "Quiet")
    assert wait_for(lambda: stations.count == 1)
    net.set_offline(True)
    try:
        stations.play(stations.model._items[0]["id"])
        assert any("Offline" in m for m in messages)
        player.playList([stations._entry(stations._db.stations()[0])], 0)
        assert "Offline" in player.error and not player.playing
        stations.search("jazz")
        assert "Offline" in stations.status
    finally:
        net.set_offline(False)


def test_station_files_in_and_out(radio, tmp_path):
    stations, _player, _ = radio
    (tmp_path / "in.m3u").write_text("#EXTM3U\n#EXTINF:-1,One FM\nhttp://one/live\n#EXTINF:-1,Two FM\nhttp://two/live\n")
    assert stations.importFile(str(tmp_path / "in.m3u")) == "Added 2 stations"
    assert stations.importFile(str(tmp_path / "in.m3u")) == "Those stations are already saved"
    assert sorted(s["name"] for s in stations.model._items) == ["One FM", "Two FM"]
    assert stations.exportFile(str(tmp_path / "out")) == "Saved 2 stations to out.m3u"
    assert st.parse_playlist((tmp_path / "out.m3u").read_text()) == ["http://one/live", "http://two/live"]
    first = stations.model._items[0]
    stations.rename(first["id"], "Renamed")
    stations.remove(stations.model._items[-1]["id"])
    assert [s["name"] for s in stations.model._items] == ["Renamed"]


def test_directory_results_can_be_saved(radio, monkeypatch):
    stations, _player, _ = radio
    found = [{"name": "Jazz One", "url": "http://jazz/one", "homepage": "", "favicon": "", "tags": "jazz",
              "country": "France", "codec": "MP3", "bitrate": 192, "uuid": "u1", "votes": 3}]
    monkeypatch.setattr(st, "search_directory", lambda q: found if q == "jazz" else [])
    stations.search("jazz")
    assert wait_for(lambda: not stations.searching)
    assert stations.results.count == 1 and stations.results._items[0]["saved"] is False
    assert stations.results._items[0]["detail"] == "jazz  ·  France  ·  MP3 192 kbps"
    stations.addResult(0)
    assert stations.count == 1 and stations.results._items[0]["saved"] is True
    stations.search("nothing")
    assert wait_for(lambda: not stations.searching) and "No stations match" in stations.status
