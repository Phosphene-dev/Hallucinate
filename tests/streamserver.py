"""A tiny local web server for radio and podcast tests: an endless ICY stream with changing song titles,
playlist files, and any other file a test hands it. Nothing leaves the machine."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

METAINT = 8192


class StreamServer:
    """`files` maps a path ("/feed.xml") to (content type, bytes); "/live" streams `audio` (MP3 bytes) forever
    with ICY titles from `titles()` (a callable, so a test can change the song)."""

    def __init__(self, audio=b"", files=None, name="Test FM", genre="Ambient"):
        self.audio, self.files, self.name, self.genre = audio, dict(files or {}), name, genre
        self.title = "Artist One - First Song"
        self.requests = []
        self.drop_after = None  # bytes; the live stream cuts off after this many (a dropped connection)
        self.stall_after = None  # bytes; the live stream goes silent after this many but keeps the connection
        self.stalled = threading.Event()  # set once a stream has gone silent
        self.release = threading.Event()  # set to let silent streams end (the server closing)
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                pass

            def do_GET(self):  # noqa: N802
                server.requests.append(self.path)
                if self.path.startswith("/live"):
                    return self._live()
                if self.path.startswith("/html"):
                    return self._send("text/html", b"<html>not a stream</html>")
                if self.path in server.files:
                    kind, data = server.files[self.path]
                    return self._send(kind, data)
                self.send_error(404)

            def _send(self, kind, data):
                rng = self.headers.get("Range")
                start = 0
                if rng and rng.startswith("bytes="):
                    start = int(rng[6:].split("-")[0] or 0)
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
                else:
                    self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data) - start))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                try:
                    self.wfile.write(data[start:])
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _live(self):
                icy = self.headers.get("Icy-MetaData") == "1"
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("icy-name", server.name)
                self.send_header("icy-genre", server.genre)
                self.send_header("icy-br", "128")
                if icy:
                    self.send_header("icy-metaint", str(METAINT))
                self.end_headers()
                data, pos, sent = server.audio, 0, 0
                try:
                    while True:
                        if server.drop_after is not None and sent >= server.drop_after:
                            return
                        if server.stall_after is not None and sent >= server.stall_after:
                            server.stalled.set()
                            server.release.wait()  # silent, the connection still open
                            return
                        chunk = (data * 2)[pos:pos + METAINT]
                        pos = (pos + METAINT) % len(data)
                        self.wfile.write(chunk)
                        sent += len(chunk)
                        if icy:
                            meta = f"StreamTitle='{server.title}';".encode()
                            meta += b"\0" * ((16 - len(meta) % 16) % 16)
                            self.wfile.write(bytes([len(meta) // 16]) + meta)
                        time.sleep(METAINT / 16000 / 2)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path):
        return self.base + path

    def close(self):
        self.release.set()
        self.httpd.shutdown()
        self.httpd.server_close()
