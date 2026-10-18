"""Podcast feeds and downloads over the network: following only permanent redirects, asking a feed's server
"anything new?" (ETag / Last-Modified), downloads that carry on where they stopped, and downloads remembered
across a restart. Everything is served from 127.0.0.1."""
import http.server
import threading

import pytest
from conftest import wait_for

from hallucinate.core import net
from hallucinate.core import podcasts as pc

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Moved Show</title>
<item><title>One</title><guid>one</guid><enclosure url="/ep.mp3" type="audio/mpeg" length="0"/></item>
</channel></rss>"""
EPISODE = bytes(range(256)) * 400  # 100 KiB


class Server:
    """Redirects (`moves`: path -> (status, target)), a feed with an ETag, and an episode served with ranges
    (or not, with `ranges` off). `cut_after` breaks an episode download off after that many bytes."""

    def __init__(self):
        self.moves, self.seen, self.ranges, self.cut_after, self.slow = {}, [], True, None, False
        self.etag = '"v1"'
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *a):
                pass

            def do_GET(self):  # noqa: N802
                fake.seen.append((self.path, dict(self.headers)))
                if self.path in fake.moves:
                    code, target = fake.moves[self.path]
                    self.send_response(code)
                    self.send_header("Location", target)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path == "/feed.xml":
                    if self.headers.get("If-None-Match") == fake.etag:
                        self.send_response(304)
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("ETag", fake.etag)
                    self.send_header("Last-Modified", "Tue, 13 Oct 2026 08:00:00 GMT")
                    self.send_header("Content-Length", str(len(FEED)))
                    self.end_headers()
                    self.wfile.write(FEED)
                    return
                if self.path == "/ep.mp3":
                    start = 0
                    rng = self.headers.get("Range")
                    if fake.ranges and rng:
                        start = int(rng.split("=")[1].split("-")[0])
                        self.send_response(206)
                        self.send_header("Content-Range", f"bytes {start}-{len(EPISODE) - 1}/{len(EPISODE)}")
                    else:
                        self.send_response(200)
                    self.send_header("Content-Type", "audio/mpeg")
                    self.send_header("Content-Length", str(len(EPISODE) - start))
                    self.end_headers()
                    body = EPISODE[start:]
                    if fake.cut_after is not None:
                        body = body[:fake.cut_after]
                    try:
                        for i in range(0, len(body), 8192):
                            self.wfile.write(body[i:i + 8192])
                            if fake.slow:
                                import time

                                time.sleep(0.05)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                self.send_error(404)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    srv = Server()
    yield srv
    srv.close()


def test_only_a_permanent_redirect_moves_the_subscription(server):
    server.moves = {"/old.xml": (301, "/new.xml"), "/new.xml": (302, "/feed.xml"), "/temp.xml": (307, "/feed.xml"),
                    "/perm.xml": (308, "/feed.xml")}
    podcast, episodes, url = pc.fetch_feed(server.base + "/old.xml")
    assert podcast["title"] == "Moved Show" and episodes[0]["url"] == server.base + "/ep.mp3"  # links from the real one
    assert url == server.base + "/new.xml"  # followed the 301, not the 302 after it
    assert pc.fetch_feed(server.base + "/temp.xml")[2] == server.base + "/temp.xml"
    assert pc.fetch_feed(server.base + "/perm.xml")[2] == server.base + "/feed.xml"
    assert pc.permanent_url("a", [(302, "b"), (301, "c")]) == "a"


def test_a_feed_that_hasnt_changed_isnt_sent_again(server):
    first = pc.fetch_feed_if_changed(server.base + "/feed.xml")
    assert first["etag"] == '"v1"' and first["modified"].startswith("Tue, 13 Oct 2026") and first["episodes"]
    again = pc.fetch_feed_if_changed(server.base + "/feed.xml", first["etag"], first["modified"])
    assert again["podcast"] is None and again["episodes"] is None and again["etag"] == '"v1"'
    assert server.seen[-1][1].get("If-None-Match") == '"v1"'
    server.etag = '"v2"'  # the feed changed
    assert pc.fetch_feed_if_changed(server.base + "/feed.xml", '"v1"')["episodes"]


def test_a_broken_off_download_carries_on_where_it_stopped(server, tmp_path):
    target = tmp_path / "ep.mp3"
    server.cut_after = 30_000
    with pytest.raises(OSError):
        pc.download(server.base + "/ep.mp3", target)
    part = tmp_path / "ep.mp3.part"
    assert part.stat().st_size == 30_000 and not target.exists()  # kept to carry on from
    server.cut_after = None
    seen = []
    pc.download(server.base + "/ep.mp3", target, progress=lambda done, total: seen.append((done, total)))
    assert target.read_bytes() == EPISODE and not part.exists()
    assert server.seen[-1][1].get("Range") == "bytes=30000-"
    assert seen[-1] == (len(EPISODE), len(EPISODE))


def test_a_server_without_ranges_sends_it_all_again(server, tmp_path):
    target = tmp_path / "ep.mp3"
    (tmp_path / "ep.mp3.part").write_bytes(b"x" * 500)
    server.ranges = False
    pc.download(server.base + "/ep.mp3", target)
    assert target.read_bytes() == EPISODE


def test_a_cancelled_download_leaves_nothing_but_a_paused_one_keeps_its_part(server, tmp_path):
    target = tmp_path / "ep.mp3"
    with pytest.raises(InterruptedError):
        pc.download(server.base + "/ep.mp3", target, cancelled=lambda: True)
    assert not (tmp_path / "ep.mp3.part").exists()
    (tmp_path / "ep.mp3.part").write_bytes(EPISODE[:100])
    with pytest.raises(InterruptedError):
        pc.download(server.base + "/ep.mp3", target, paused=lambda: True)
    assert (tmp_path / "ep.mp3.part").exists() and not target.exists()


@pytest.fixture
def make_shows(qapp, tmp_path):
    from hallucinate.player import Player
    from hallucinate.podcasts import Podcasts

    made = []

    def make():
        player = Player(session_file=tmp_path / "session.json")
        podcasts = Podcasts(tmp_path / "streams.db", tmp_path / "data", tmp_path / "cache", player)
        messages = []
        podcasts.message.connect(messages.append)
        made.append((podcasts, player))
        return podcasts, messages

    yield make
    for podcasts, player in made:
        podcasts.shutdown()
        player.shutdown()


def _follow(podcasts, url):
    podcasts.follow(url)
    assert wait_for(lambda: podcasts.count == 1 and not podcasts.busy)
    return podcasts.shows._items[0]["id"]


def test_refresh_asks_whats_new_and_keeps_the_link_after_a_temporary_redirect(server, make_shows):
    podcasts, messages = make_shows()
    server.moves = {"/show.xml": (302, "/feed.xml")}
    show = _follow(podcasts, server.base + "/show.xml")
    assert podcasts._db.podcast(show)["feed_url"] == server.base + "/show.xml"
    podcasts.refresh(show)
    assert wait_for(lambda: "No new episodes" in messages)
    p = podcasts._db.podcast(show)
    assert p["feed_url"] == server.base + "/show.xml" and p["etag"] == '"v1"'  # still the link you followed
    messages.clear()
    podcasts.refresh(show)
    assert wait_for(lambda: "No new episodes" in messages)
    assert server.seen[-1][1].get("If-None-Match") == '"v1"'  # answered "not modified"
    server.moves = {"/show.xml": (301, "/feed.xml")}  # now it moved for good
    messages.clear()
    podcasts.refresh(show)
    assert wait_for(lambda: "No new episodes" in messages)
    assert podcasts._db.podcast(show)["feed_url"] == server.base + "/feed.xml"


def test_unfinished_downloads_carry_on_after_a_restart(server, make_shows, tmp_path):
    podcasts, messages = make_shows()
    show = _follow(podcasts, server.base + "/feed.xml")
    episode = podcasts._db.episodes(show)[0]["id"]
    net.set_offline(True)
    try:
        podcasts.downloadUnplayed(show)
        assert "when it's off" in messages[-1]
        assert podcasts._db.queued_downloads() == [episode]
    finally:
        net.set_offline(False)
    podcasts.shutdown()
    again, _messages = make_shows()  # the app starts again
    assert again._resume_timer.isActive()
    again.resumeNetwork()
    assert wait_for(lambda: again._db.episode(episode)["local_path"], timeout=15)
    assert open(again._db.episode(episode)["local_path"], "rb").read() == EPISODE
    assert again._db.queued_downloads() == []


def test_stop_network_pauses_downloads_and_failures_are_in_words(server, make_shows):
    podcasts, messages = make_shows()
    show = _follow(podcasts, server.base + "/feed.xml")
    episode = podcasts._db.episodes(show)[0]["id"]
    server.slow = True
    podcasts.download(episode)
    assert wait_for(lambda: any(path == "/ep.mp3" for path, _h in server.seen))  # under way
    podcasts.stopNetwork()
    assert wait_for(lambda: not podcasts._downloading, timeout=15)
    assert not podcasts._db.episode(episode)["local_path"] and not any(m.startswith("Download failed") for m in messages)
    assert podcasts._db.queued_downloads() == [episode]  # kept, with what it had got, to carry on
    server.slow = False
    podcasts._db.conn.execute("UPDATE episodes SET url=?, local_path='' WHERE id=?",
                              (server.base + "/missing.mp3", episode))
    podcasts._db.conn.commit()
    podcasts.download(episode)
    assert wait_for(lambda: any(m.startswith("Download failed") for m in messages), timeout=15)
    assert "nothing was found at that link" in [m for m in messages if m.startswith("Download failed")][-1]
    assert podcasts._db.queued_downloads() == []  # a 404 isn't tried again


def test_failed_covers_arent_fetched_on_every_reload(server, make_shows, monkeypatch):
    podcasts, _messages = make_shows()
    asked = []
    monkeypatch.setattr(podcasts, "_fetch_images", lambda urls: asked.append(urls))
    podcasts._db.add_podcast({"title": "Pic", "feed_url": server.base + "/x.xml", "image": server.base + "/nope.png"})
    podcasts.reload()
    assert wait_for(lambda: asked == [[server.base + "/nope.png"]])  # (on a worker)
    monkeypatch.undo()
    podcasts._fetch_images([server.base + "/nope.png"])  # a 404
    asked.clear()
    monkeypatch.setattr(podcasts, "_fetch_images", lambda urls: asked.append(urls))
    podcasts.reload()
    assert not wait_for(lambda: asked, timeout=0.5)
    podcasts._failed_art[server.base + "/nope.png"] -= 2 * 3600  # an hour later it's tried again
    podcasts.reload()
    assert wait_for(lambda: asked == [[server.base + "/nope.png"]])
