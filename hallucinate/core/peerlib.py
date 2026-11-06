"""Libraries shared between computers running Hallucinate: one computer's songs in another's library, played
from the first over the local network, as a music server's are (servers.py).

The computers are paired already (handoff.py: one shows a code, the other enters it and keeps the key it gets).
The sharing one says yes once (Settings → Remote & web → Paired computers can play my library), and then its web
server answers, for paired devices only:

- /lib/hello   who it is, and the asking device's own id there (to sign links with)
- /lib/songs   its songs, a page at a time: what's needed to list them (titles, artists, albums, numbers, the
               format), never a path. Songs are known by an id made from their path (`song_id`), which stays the
               same across rescans.
- /lib/cover/<id>  an album's cover
- /lib/s/<device>/<song>?e=…&s=…  a song's file, to play.

The first three take the key as a Bearer token. A song's link is what the player opens, so it can't carry a
header: it's signed instead, with an HMAC of the device, the song and when it stops working, keyed with a hash
of the device's key (`sign`): the key itself never goes in a link, and a link works only for a while (LINK_S).
The sharing computer keeps only that hash of each key, so it checks the signature with what it has.

Nothing here can change anything on the sharing computer: it only lists and plays."""
import datetime
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import net

LINK_S = 12 * 3600  # how long a song's link works (enough for a long queue; made again when it's played again)
PAGE = 500
MAX_SONGS = 500_000
SQL_SHAREABLE = "path NOT GLOB '[a-z]*://*' AND file IS NULL AND cue_start = 0 AND cue_end = 0"


def song_id(path):
    """A song's id: from its path, so it stays the same across rescans, without saying what the path is."""
    return hashlib.sha256(("hallucinate-song\0" + path).encode("utf-8")).hexdigest()[:24]


def key_secret(key):
    """What links are signed with: the hash of the device's key the sharing computer keeps (webserver._hash)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def sign(secret, device_id, sid, expires):
    message = f"{device_id}/{sid}/{int(expires)}".encode("ascii")
    return hmac.new(secret.encode("ascii"), message, hashlib.sha256).hexdigest()[:40]


def check(secret, device_id, sid, expires, signature, now=None):
    """Whether a song's link is genuine and still working."""
    now = time.time() if now is None else now
    try:
        expires = int(expires)
    except (TypeError, ValueError):
        return False
    if not now <= expires <= now + LINK_S + 60:
        return False
    return hmac.compare_digest(sign(secret, device_id, sid, expires), str(signature)[:40])


# --- the sharing side ----------------------------------------------------------------------------------------
def listing(db, offset=0, limit=PAGE):
    """A page of the songs this computer shares: {"total", "songs": [...]}, in a steady order."""
    limit = max(1, min(PAGE, int(limit)))
    total = db.conn.execute(f"SELECT COUNT(*) FROM tracks WHERE {SQL_SHAREABLE}").fetchone()[0]  # noqa: S608
    rows = db.conn.execute(
        "SELECT path, mtime, size, title, artist, album_artist, album, album_key, track_no, disc_no, year, genre,"
        " duration, fmt, bitrate, sample_rate, bit_depth, explicit, rg_track, rg_album, rg_peak, art FROM tracks"
        f" WHERE {SQL_SHAREABLE} ORDER BY id LIMIT ? OFFSET ?", (limit, max(0, int(offset)))).fetchall()  # noqa: S608
    songs = []
    for r in rows:
        songs.append({"id": song_id(r["path"]), "title": r["title"], "artist": r["artist"],
                      "album_artist": r["album_artist"], "album": r["album"],
                      "album_id": hashlib.sha256(r["album_key"].encode("utf-8")).hexdigest()[:16],
                      "track_no": r["track_no"], "disc_no": r["disc_no"], "year": r["year"], "genre": r["genre"],
                      "duration": r["duration"], "suffix": (r["fmt"] or "").lower()[:16], "bitrate": r["bitrate"],
                      "sample_rate": r["sample_rate"], "bit_depth": r["bit_depth"], "explicit": r["explicit"],
                      "size": r["size"],
                      "changed": datetime.datetime.fromtimestamp(r["mtime"], datetime.timezone.utc).isoformat(),
                      "cover": hashlib.sha256(r["album_key"].encode("utf-8")).hexdigest()[:16] if r["art"] else "",
                      "rg_track": r["rg_track"], "rg_album": r["rg_album"], "rg_peak": r["rg_peak"]})
    return {"total": total, "songs": songs}


class Index:
    """Song ids and cover ids back to paths and albums (made when first asked, again when one isn't found)."""

    def __init__(self):
        self._songs, self._albums, self._made = {}, {}, 0.0

    def _make(self, db):
        rows = db.conn.execute(f"SELECT path, album_key FROM tracks WHERE {SQL_SHAREABLE}").fetchall()  # noqa: S608
        self._songs = {song_id(r[0]): r[0] for r in rows}
        self._albums = {hashlib.sha256(r[1].encode("utf-8")).hexdigest()[:16]: r[1] for r in rows}
        self._made = time.monotonic()

    def path(self, db, sid):
        if sid not in self._songs and time.monotonic() - self._made > 5:
            self._make(db)
        return self._songs.get(sid)

    def album(self, db, cover):
        if cover not in self._albums and time.monotonic() - self._made > 5:
            self._make(db)
        return self._albums.get(cover)


# --- the other side: a shared library, as a music server ----------------------------------------------------
class PeerError(OSError):
    pass


class Server:
    """Another computer's shared library (the client servers.py uses, like subsonic.Server)."""

    def __init__(self, base, key, device_id="", timeout=20):
        self.base = base.rstrip("/")
        self._key = key
        self.device_id = device_id
        self.timeout = timeout

    def _get(self, path, limit=16 * 1024 * 1024, raw=False):
        parts = urllib.parse.urlsplit(self.base)
        request = urllib.request.Request(self.base + path, headers={"Authorization": f"Bearer {self._key}",
                                                                    "User-Agent": "Hallucinate", "X-Hallucinate": "1"})
        if not net.is_local_address(parts.hostname or ""):
            raise PeerError("not an address on your network")
        try:
            with net.urlopen(request, timeout=self.timeout, limit=limit) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise PeerError("the other computer didn't let us in (is sharing on, and are they still paired?)") \
                    from None
            raise
        if raw:
            return data
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("that isn't Hallucinate") from exc

    def ping(self):
        """{"type": its name, "songs"}; learns this device's id there."""
        hello = self._get("/lib/hello", limit=64 * 1024)
        if not isinstance(hello, dict) or hello.get("app") != "Hallucinate":
            raise ValueError("that isn't Hallucinate")
        self.device_id = str(hello.get("device", ""))[:40]
        return {"type": str(hello.get("name", "Hallucinate"))[:100], "songs": int(hello.get("songs") or 0),
                "device": self.device_id}

    def pages(self, page=PAGE, should_stop=lambda: False):
        offset, seen = 0, set()
        while offset < MAX_SONGS and not should_stop():
            answer = self._get(f"/lib/songs?offset={offset}&limit={page}")
            songs = answer.get("songs") if isinstance(answer, dict) else None
            if not isinstance(songs, list) or not songs:
                return
            fresh = [s for s in (_song(x) for x in songs[:page]) if s and s["id"] not in seen]
            if not fresh:
                return
            seen.update(s["id"] for s in fresh)
            yield fresh
            if len(songs) < page:
                return
            offset += len(songs)

    def stream_url(self, sid, now=None):
        expires = int((time.time() if now is None else now) + LINK_S)
        signature = sign(key_secret(self._key), self.device_id, sid, expires)
        return f"{self.base}/lib/s/{self.device_id}/{urllib.parse.quote(sid)}?e={expires}&s={signature}"

    def cover(self, cover_id, size=600):
        from .artfetch import MAX_BYTES

        data = self._get(f"/lib/cover/{urllib.parse.quote(cover_id)}", limit=MAX_BYTES, raw=True)
        return data if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" else b""

    def scrobble(self, song_id, when_ms=None, submission=True):
        pass  # (plays are counted here; the other computer's own counts are its own)

    def set_rating(self, song_id, stars):
        pass


def _text(value, limit=500):
    return str(value or "").strip()[:limit]


def _num(value, low=0, high=10**12):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def _gain(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if -60 <= v <= 60 else None


def _song(item):
    """A song the other computer listed, as plain checked values (the shape subsonic.song_from gives)."""
    if not isinstance(item, dict):
        return None
    sid = _text(item.get("id"), 40)
    if not sid or not all(c in "0123456789abcdef" for c in sid):
        return None
    artist = _text(item.get("artist"))
    return {"id": sid, "title": _text(item.get("title")) or "Unknown title", "artist": artist,
            "album_artist": _text(item.get("album_artist")) or artist, "album": _text(item.get("album")),
            "album_id": _text(item.get("album_id"), 40), "track_no": _num(item.get("track_no"), 0, 9999),
            "disc_no": _num(item.get("disc_no"), 0, 999), "year": _num(item.get("year"), 0, 9999),
            "genre": _text(item.get("genre"), 200), "duration": float(_num(item.get("duration"), 0, 10**7)),
            "suffix": _text(item.get("suffix"), 16).lower(), "bitrate": _num(item.get("bitrate"), 0, 100_000),
            "sample_rate": _num(item.get("sample_rate"), 0, 10**6), "bit_depth": _num(item.get("bit_depth"), 0, 64),
            "explicit": _num(item.get("explicit"), 0, 2), "size": _num(item.get("size")),
            "cover": _text(item.get("cover"), 40), "rating": 0, "starred": False,
            "rg_track": _gain(item.get("rg_track")), "rg_album": _gain(item.get("rg_album")),
            "rg_peak": _gain(item.get("rg_peak")), "changed": _text(item.get("changed"), 40)}
