"""Find missing cover art on MusicBrainz / Cover Art Archive."""
import time
import urllib.error
import urllib.request

from . import musicbrainz, net
from .lyrics import USER_AGENT

MAX_BYTES = 8_000_000
CAA = "https://coverartarchive.org/"


class ServiceError(OSError):
    """MusicBrainz or the Cover Art Archive answered with a server error (5xx): their side, not the network.
    The message is meant to be shown as is."""


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with net.urlopen(req, timeout=timeout) as resp:
        return resp.read(MAX_BYTES)


def _search(params, timeout=10):
    """A MusicBrainz release search, through musicbrainz._get: every MusicBrainz request in the app shares its
    one-a-second limit (cover lookups, Discord's and tag fixes alike), as MusicBrainz asks."""
    return musicbrainz._get("release/", params, timeout=timeout)


def _quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_releases(artist, album, limit=5, sleep=time.sleep):
    """[(release id, release-group id)] best match first. A busy or failing MusicBrainz (503, 5xx) is retried
    once after a second, as its rate limit asks."""
    query = f"release:{_quote(album)}"
    if artist and artist.lower() not in ("unknown artist", "various artists"):
        query += f" AND artist:{_quote(artist)}"
    for attempt in (1, 2):
        try:
            data = _search({"query": query, "limit": limit})
            break
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise
            if attempt == 2:
                raise ServiceError(f"MusicBrainz is having trouble right now (HTTP {exc.code}); "
                                   "try again in a minute") from exc
            sleep(1.1)
    releases = data.get("releases") if isinstance(data, dict) else None
    return [(r["id"], (r.get("release-group") or {}).get("id") or "")
            for r in releases or [] if isinstance(r, dict) and isinstance(r.get("id"), str)]


def find_release_ids(artist, album, limit=5):
    return [rid for rid, _group in find_releases(artist, album, limit)]


def _is_image(data):
    return data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"


def fetch_cover(artist, album, sleep=time.sleep):
    """Image bytes of the best matching front cover, or None when no match has one. Raises ServiceError when the
    cover servers failed for every candidate, and OSError on network trouble.

    The Cover Art Archive's images live on archive.org, which now and then fails a single image with a 5xx; that
    only skips to the next size or candidate instead of ending the search. Releases without their own art fall
    back to their release group's cover (shared by every edition of the album)."""
    try:
        releases = find_releases(artist, album, sleep=sleep)
        candidates = []
        for rid, _group in releases:
            candidates += [f"release/{rid}/front-500", f"release/{rid}/front-250"]
        for group in dict.fromkeys(g for _rid, g in releases if g):
            candidates.append(f"release-group/{group}/front-500")
        server_error = None
        for path in candidates:
            try:
                data = _get(CAA + path)
            except urllib.error.HTTPError as exc:
                if exc.code >= 500:
                    server_error = exc
                continue  # 404/400: no art for this one
            if _is_image(data):
                return data
        if server_error is not None:
            raise ServiceError(f"The Cover Art Archive is having trouble right now (HTTP {server_error.code}); "
                               "try again in a bit")
    except ServiceError:
        raise
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise OSError(str(exc)) from exc
    return None
