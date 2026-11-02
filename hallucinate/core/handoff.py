"""Handing playback from one computer running Hallucinate to another.

The sending computer describes its queue (`describe`): for each song what identifies it anywhere (artist, title,
album, length, track and disc number), never a path or a link with a login in it. The receiving computer finds each
song in its own library (`match`): the same artist and title, then the album and length to choose between versions
(a live take and the studio one). A song it doesn't have plays from the sending computer through one handoff
link (`HandoffLink`), which only the receiving computer's address can use and which expires.

Radio stations travel as their stream address (it's public), and podcast episodes by their feed and episode link.
Qt-free."""
import secrets
import threading
import time

from .db import fold

MAX_SONGS = 5000  # a queue longer than this is cut (from the playing song on)
LINK_LIFETIME_S = 24 * 3600
LENGTH_SLACK_S = 3.0  # the same song, ripped or encoded differently, can differ by a second or two


def describe(track):
    """A queue entry as it travels: what identifies it, nothing that only means something on this computer."""
    kind = track.get("kind") or "music"

    def text(key, limit=300):
        return str(track.get(key) or "")[:limit]

    out = {"kind": kind, "title": text("title"), "artist": text("artist"), "album": text("album"),
           "album_artist": text("album_artist"), "duration": float(track.get("duration") or 0),
           "track_no": int(track.get("track_no") or 0), "disc_no": int(track.get("disc_no") or 0)}
    if kind == "station":
        out.update(url=text("path", 2000), station=text("station"))
    elif kind == "episode":
        out.update(url=text("path", 2000), feed=text("feed", 2000))
    return out


def _num(value, default=0.0):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value \
        else default


def clean(song):
    """A received song description, with every field checked (it came over the network)."""
    if not isinstance(song, dict):
        return None
    kind = song.get("kind") if song.get("kind") in ("music", "station", "episode") else "music"

    def text(key, limit=300):
        v = song.get(key)
        return v[:limit] if isinstance(v, str) else ""

    out = {"kind": kind, "title": text("title"), "artist": text("artist"), "album": text("album"),
           "album_artist": text("album_artist"), "duration": max(0.0, min(_num(song.get("duration")), 1e6)),
           "track_no": int(max(0, min(_num(song.get("track_no")), 9999))),
           "disc_no": int(max(0, min(_num(song.get("disc_no")), 999)))}
    if kind in ("station", "episode"):
        url = text("url", 2000)
        if not url.lower().startswith(("http://", "https://")):
            return None
        out["url"] = url
        out["station" if kind == "station" else "feed"] = text("station" if kind == "station" else "feed", 2000)
    return out


def match(conn, songs):
    """For each received (cleaned) song, the path of the same song in this library, or None. `conn` is the
    library's sqlite connection."""
    out = []
    cache = {}
    for song in songs:
        if song is None or song["kind"] != "music" or not song["title"]:
            out.append(None)
            continue
        key = (fold(song["artist"]), fold(song["title"]))
        if key not in cache:
            cache[key] = conn.execute(
                "SELECT path, s_album, duration, track_no, disc_no, album_artist FROM tracks "
                "WHERE s_artist=? AND s_title=?", key).fetchall()
        rows = cache[key]
        if not rows:
            out.append(None)
            continue
        album = fold(song["album"])
        dur = song["duration"]

        def score(r):
            s = 0
            if album and r[1] == album:
                s += 4
            if dur and r[2] and abs(r[2] - dur) <= LENGTH_SLACK_S:
                s += 2
            if song["track_no"] and r[3] == song["track_no"]:
                s += 1
            if song["disc_no"] and r[4] == song["disc_no"]:
                s += 1
            return s
        best = max(rows, key=score)
        # the same artist and title but a clearly different recording (a 9-minute live take for a 3-minute
        # song, on another album) isn't the song that was playing: stream that one instead
        if dur and best[2] and abs(best[2] - dur) > max(20.0, dur * 0.15) and not (album and best[1] == album):
            out.append(None)
        else:
            out.append(best[0])
    return out


class HandoffLink:
    """On the sending computer: the queue's songs, each fetchable by its place in it, by one computer's address
    only, until it expires or is replaced. `path_for(index)` gives the file (or None); thread-safe."""

    def __init__(self, client, paths, lifetime=LINK_LIFETIME_S, clock=time.monotonic):
        self.client = client
        self.token = secrets.token_urlsafe(24)
        self._paths = list(paths)
        self._clock = clock
        self._until = clock() + lifetime
        self._lock = threading.Lock()

    @property
    def expired(self):
        return self._clock() > self._until

    def path_for(self, index):
        with self._lock:
            if self.expired or not 0 <= index < len(self._paths):
                return None
            return self._paths[index]

    def revoke(self):
        with self._lock:
            self._until = 0
