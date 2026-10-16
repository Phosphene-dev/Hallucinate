"""Album details from MusicBrainz (https://musicbrainz.org), for fixing an album's tags from one search: its
title, album artist, year and every track's title and number.

MusicBrainz asks for a descriptive User-Agent and no more than one request a second; both are kept here. Every
request goes through core.net, so offline mode stops it."""
import json
import threading
import time
import urllib.parse
import urllib.request

from .. import __version__
from . import net

API = "https://musicbrainz.org/ws/2/"
USER_AGENT = f"Hallucinate/{__version__} ( https://github.com/Phosphene-dev/Hallucinate )"
_lock = threading.Lock()
_last = [0.0]


def _get(path, params, timeout=15):
    with _lock:  # at most one request a second, as MusicBrainz asks
        wait = 1.05 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
    url = API + path + "?" + urllib.parse.urlencode({**params, "fmt": "json"})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with net.urlopen(request, timeout=timeout, limit=4_000_000) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _credit(credits):
    return "".join((c.get("name") or c.get("artist", {}).get("name", "")) + (c.get("joinphrase") or "")
                   for c in credits or []).strip()


def _quote(text):
    return '"' + (text or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def search_releases(artist, album, limit=10):
    """Releases matching an album and artist: [{id, title, artist, year, country, tracks, format, label}],
    best match first."""
    query = f"release:{_quote(album)}"
    if artist:
        query += f" AND artist:{_quote(artist)}"
    data = _get("release/", {"query": query, "limit": str(limit)})
    out = []
    for r in data.get("releases", []):
        media = r.get("media") or []
        out.append({
            "id": r.get("id", ""), "title": r.get("title", ""), "artist": _credit(r.get("artist-credit")),
            "year": (r.get("date") or "")[:4], "country": r.get("country") or "",
            "tracks": int(r.get("track-count") or sum(int(m.get("track-count") or 0) for m in media)),
            "format": " + ".join(sorted({m.get("format") or "" for m in media} - {""})),
            "label": ", ".join(li.get("label", {}).get("name", "") for li in r.get("label-info") or [] if li.get("label")),
            "score": int(r.get("score") or 0),
        })
    return out


def release(release_id):
    """One release in full: {title, artist, year, genre, tracks: [{disc, number, title, artist}]}."""
    data = _get(f"release/{urllib.parse.quote(release_id)}", {"inc": "recordings+artist-credits+genres"})
    tracks = []
    for disc, medium in enumerate(data.get("media") or [], start=1):
        for t in medium.get("tracks") or []:
            tracks.append({"disc": int(medium.get("position") or disc), "number": int(t.get("position") or 0),
                           "title": t.get("title") or (t.get("recording") or {}).get("title", ""),
                           "artist": _credit(t.get("artist-credit")) or _credit(data.get("artist-credit"))})
    genres = sorted(data.get("genres") or [], key=lambda g: -int(g.get("count") or 0))
    return {"title": data.get("title", ""), "artist": _credit(data.get("artist-credit")),
            "year": (data.get("date") or "")[:4], "genre": genres[0]["name"].title() if genres else "",
            "discs": len(data.get("media") or []), "tracks": tracks}


def match_tracks(songs, tracks):
    """Pair an album's songs (in their disc/track order) with a release's tracks. Only when the counts are the
    same: [(song path, track)], else []."""
    if not songs or len(songs) != len(tracks):
        return []
    ordered = sorted(songs, key=lambda s: (int(s.get("disc_no") or 0) or 1, int(s.get("track_no") or 0)))
    return [(s["path"], t) for s, t in zip(ordered, sorted(tracks, key=lambda t: (t["disc"], t["number"])))]
