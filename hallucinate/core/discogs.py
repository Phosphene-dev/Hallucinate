"""Genres, styles and artist profiles from Discogs (https://www.discogs.com).

Discogs only answers searches with a personal access token (made at discogs.com/settings/developers); it's
kept in the system keyring and passed in here. Discogs allows 60 requests a minute with a token; requests are
spaced a second apart, and every one goes through core.net, so offline mode stops it.

An album's Discogs genres are broad ("Electronic") and its styles specific ("IDM", "Ambient"), so the styles
come first: they're the album's main genres, the broad ones after them."""
import json
import re
import threading
import time
import urllib.parse
import urllib.request

from .. import __version__
from . import net
from .musicbrainz import _norm, _same

API = "https://api.discogs.com/"
USER_AGENT = f"Hallucinate/{__version__} +https://github.com/Phosphene-dev/Hallucinate"
_lock = threading.Lock()
_last = [0.0]

# Discogs' own genre names that are really several genres in one
_BROAD = {
    "Funk / Soul": ["Funk", "Soul"],
    "Folk, World, & Country": ["Folk", "World", "Country"],
    "Stage & Screen": ["Soundtrack"],
    "Non-Music": [],
    "Children's": ["Children's Music"],
}


def _get(path, params, token, timeout=15):
    with _lock:
        wait = 1.05 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                                                   "Authorization": f"Discogs token={token}"})
    with net.urlopen(request, timeout=timeout, limit=4_000_000) as resp:
        return json.loads(resp.read().decode("utf-8"))


def identity(token):
    """The Discogs user name a token belongs to (raises urllib's HTTPError 401 for a wrong one)."""
    return _get("oauth/identity", None, token).get("username", "")


def _bare_artist(name):
    """Discogs tells same-named artists apart with "(2)" and marks name variations with "*"."""
    return re.sub(r"\s*\(\d+\)$", "", (name or "").replace("*", "").strip())


def _split_title(title):
    """A search result's title, "Artist - Album", as (artist, album)."""
    artist, sep, album = (title or "").partition(" - ")
    return (artist, album) if sep else ("", title or "")


def genre_list(styles, genres):
    """An album's genres from its Discogs styles and genres: the styles first, then the broad genres."""
    out = list(styles or [])
    for g in genres or []:
        out += _BROAD.get(g, [g])
    seen, names = set(), []
    for name in out:
        key = _norm(name)
        if key and key not in seen:
            seen.add(key)
            names.append(name.strip())
    return names


def _search_album(artist, album, token):
    for kind in ("master", "release"):
        params = {"type": kind, "release_title": album, "per_page": "8"}
        if (artist or "").strip():
            params["artist"] = artist
        for r in _get("database/search", params, token).get("results", []):
            found_artist, found_album = _split_title(r.get("title", ""))
            if not _same(found_album, album):
                continue
            if (artist or "").strip() and not _same(_bare_artist(found_artist), artist):
                continue
            return r
    return None


def find_genre(artist, album, token):
    """{"genre", "genres" (best first), "source": "album", "release"} for an album, or None when Discogs has
    no confident match."""
    if not (album or "").strip() or not token:
        return None
    hit = _search_album(artist, album, token)
    if not hit:
        return None
    names = genre_list(hit.get("style"), hit.get("genre"))
    if not names:
        return None
    return {"genre": names[0], "genres": names[:6], "source": "album", "release": _split_title(hit["title"])[1]}


# Discogs profile markup: [a=Name] and [l=Label] links, [a123] by number, [url=...]text[/url], [b], [i]
_LINKED = re.compile(r"\[(?:a|l|m|r)=([^\]]+)\]")
_NUMBERED = re.compile(r"\[(?:a|l|m|r)\d+\]")
_URL = re.compile(r"\[url=[^\]]*\](.*?)\[/url\]", re.S)
_TAGS = re.compile(r"\[/?(?:b|i|u)\]")


def plain_profile(text):
    """A Discogs profile as plain text."""
    text = _URL.sub(r"\1", text or "")
    text = _LINKED.sub(lambda m: _bare_artist(m.group(1)), text)
    text = _NUMBERED.sub("", text)
    text = _TAGS.sub("", text)
    text = re.sub(r"[ \t]+", " ", text.replace("\r", ""))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def artist_bio(name, token, album=""):
    """{"text", "url", "source": "Discogs"} for an artist, or None. With one of their albums, the artist is
    found through it (two artists can share a name); otherwise by an exact name match."""
    if not (name or "").strip() or not token:
        return None
    artist_id = None
    if (album or "").strip():
        hit = _search_album(name, album, token)
        if hit:
            kind = "masters" if hit.get("type") == "master" else "releases"
            data = _get(f"{kind}/{int(hit['id'])}", None, token)
            for a in data.get("artists") or []:
                if _same(_bare_artist(a.get("name", "")), name):
                    artist_id = a.get("id")
                    break
    if artist_id is None:
        for r in _get("database/search", {"type": "artist", "q": name, "per_page": "5"}, token).get("results", []):
            if _same(_bare_artist(r.get("title", "")), name):
                artist_id = r.get("id")
                break
    if artist_id is None:
        return None
    data = _get(f"artists/{int(artist_id)}", None, token)
    text = plain_profile(data.get("profile", ""))
    if not text:
        return None
    return {"text": text, "url": data.get("uri", ""), "source": "Discogs"}
