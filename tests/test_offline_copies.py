"""Server songs kept on this computer: downloaded once, played from the copy (in offline mode too), carried on
after a stop, and removed only from their own folder."""
import http.server
import threading

import pytest
from conftest import wait_for

from hallucinate.core import net, remote
from hallucinate.core.db import Database

AUDIO = b"ID3" + bytes(5000)


class Handler(http.server.BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):  # noqa: N802
        Handler.hits.append(self.path)
        if "missing" in self.path:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(AUDIO)))
        self.end_headers()
        self.wfile.write(AUDIO)

    def log_message(self, *args):
        pass


class Server:
    base = ""

    def __init__(self, port):
        self.port = port

    def stream_url(self, song_id):
        return f"http://127.0.0.1:{self.port}/stream/{song_id}"


@pytest.fixture
def setup(qapp, tmp_path):
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    remote.register("subsonic", "s1", Server(httpd.server_address[1]))
    db = Database(tmp_path / "lib.db")
    for song in ("a", "b", "missing"):
        db.upsert_track({"path": remote.make_path("subsonic", "s1", song), "mtime": 0, "size": 1, "title": song,
                         "artist": "X", "album_artist": "X", "aa_tag": 1, "album": "L", "album_key": "x|l",
                         "track_no": 1, "disc_no": 0, "year": 0, "genre": "", "duration": 1, "fmt": "MP3",
                         "codec": "MP3", "bitrate": 0, "sample_rate": 0})
    db.commit()
    db.close()
    Handler.hits = []
    yield tmp_path
    httpd.shutdown()
    remote.forget("subsonic", "s1")


def make(tmp_path):
    from hallucinate.offline import OfflineCopies

    return OfflineCopies(tmp_path / "lib.db", tmp_path / "copies")


def test_kept_songs_play_from_their_copy_even_offline(setup):
    a, b = remote.make_path("subsonic", "s1", "a"), remote.make_path("subsonic", "s1", "b")
    copies = make(setup)
    try:
        assert copies.status([a, b, "/m/own.flac"]) == {"servers": 2, "kept": 0, "waiting": 0}
        copies.keep([a, b, "/m/own.flac"])  # (a file of yours isn't a server's: nothing to keep)
        assert wait_for(lambda: copies.count == 2 and not copies.busy)
        assert copies.status([a, b])["kept"] == 2 and copies.bytes == 2 * len(AUDIO)
        file = remote.local_copy(a)
        assert file.startswith(str(setup / "copies")) and open(file, "rb").read() == AUDIO
        assert remote.stream_url(a).startswith("file:") and remote.host(a) == "" and not remote.streamed(a)
        net.set_offline(True)
        try:
            assert remote.available(a)  # plays without the server
            assert not remote.available(remote.make_path("subsonic", "s1", "missing"))
        finally:
            net.set_offline(False)
        hits = len(Handler.hits)
        copies.keep([a])  # kept already: not fetched again
        assert len(Handler.hits) == hits
        copies.remove([a])
        assert not remote.local_copy(a) and copies.count == 1
        import os

        assert not os.path.exists(file)
    finally:
        copies.shutdown()


def test_copies_are_known_again_after_a_restart_and_gone_songs_are_tidied(setup):
    a = remote.make_path("subsonic", "s1", "a")
    copies = make(setup)
    copies.keep([a])
    assert wait_for(lambda: copies.count == 1 and not copies.busy)
    copies.shutdown()
    remote.set_copy(a, "")
    copies = make(setup)
    try:
        assert remote.local_copy(a)  # read back from the library
        db = Database(setup / "lib.db")
        db.remove_paths([a])
        db.commit()
        db.close()
        copies.tidy()
        assert copies.count == 0 and not remote.local_copy(a)
    finally:
        copies.shutdown()


def test_a_song_that_wont_download_is_dropped_and_offline_mode_waits(setup):
    a, missing = remote.make_path("subsonic", "s1", "a"), remote.make_path("subsonic", "s1", "missing")
    copies = make(setup)
    messages = []
    copies.message.connect(messages.append)
    try:
        net.set_offline(True)
        try:
            copies.keep([a])
            assert copies.waiting == 1 and "Offline mode" in messages[-1]
        finally:
            net.set_offline(False)
        copies.keep([missing])
        copies.resumeNetwork()
        assert wait_for(lambda: copies.count == 1 and copies.waiting == 0 and not copies.busy)
        assert wait_for(lambda: any("couldn't be kept" in m for m in messages))
    finally:
        copies.shutdown()
