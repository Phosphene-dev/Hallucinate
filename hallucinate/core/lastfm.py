"""Album tags and artist bios from Last.fm, with the API key you set up for scrobbling.

Last.fm's tags are whatever listeners typed ("seen live", "favourite albums", "2009"), so only the ones that
are genres are used: names on MusicBrainz's genre list (see core.genrelist) and tagged by enough people.
Every request goes through core.net, so offline mode stops it."""
import html
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from .. import __version__
from . import genres as genre_names
from . import net
from .musicbrainz import _norm, genre_name

API = "https://ws.audioscrobbler.com/2.0/"
USER_AGENT = f"Hallucinate/{__version__}"
MIN_COUNT = 10  # out of 100: Last.fm scales the counts so the album's top tag is 100

# Tags that are never genres, for when the genre list couldn't be fetched
_NOT_GENRES = re.compile(
    r"^(seen live|favou?rites?|favou?rite .*|my .*|.* i own|albums? .*|best .*|awesome|beautiful|love|"
    r"amazing|cool|good|great|classic|masterpiece|under \d+ listeners|check out|to listen|owned|vinyl|cd|"
    r"spotify|\d{2,4}s?|.*\d{4}.*|male vocalists?|female vocalists?|british|american|uk|usa|german|french|"
    r"japanese|swedish|canadian|australian|.* records|soundtrack of my life|chill|mellow|sad|happy)$",
)


# From 1 December 2026 Last.fm's API takes a key only from a Last.fm Pro subscriber. A key it turns down answers
# with one of these codes (an invalid or suspended key), or words about Pro or a subscription; from then on
# Hallucinate stops asking with it (scrobbles wait) and the lookups use the free sources instead.
KEY_ERRORS = {10, 26}
_refused = threading.Event()


def refuses_key(code, message=""):
    """Whether a Last.fm error means it won't take the API key any more (rather than a passing problem)."""
    text = (message or "").lower()
    return int(code or 0) in KEY_ERRORS or "subscription" in text or "subscriber" in text or " pro " in f" {text} "


def key_refused():
    """Whether Last.fm has turned the API key down (until a new key, or Send now, says otherwise)."""
    return _refused.is_set()


def set_key_refused(on):
    (_refused.set if on else _refused.clear)()


def _get(method, params, api_key, timeout=15):
    query = urllib.parse.urlencode({"method": method, **params, "api_key": api_key, "format": "json",
                                    "autocorrect": "1"})
    request = urllib.request.Request(API + "?" + query, headers={"User-Agent": USER_AGENT})
    try:
        with net.urlopen(request, timeout=timeout, limit=2_000_000) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # (Last.fm says why in the body: a key it won't take, say)
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except (OSError, ValueError):
            raise exc from None
        if not (isinstance(data, dict) and data.get("error")):
            raise
    if isinstance(data, dict) and data.get("error"):
        if refuses_key(data.get("error"), str(data.get("message") or "")):
            set_key_refused(True)
        return {}
    return data


def filter_tags(tags, known=None, artist=""):
    """The tags that are genres, best first: tagged by enough people and, with `known` (genres.key names),
    on that list; without it, anything that doesn't look like a non-genre tag."""
    out = []
    for t in tags or []:
        name = " ".join(str(t.get("name") or "").split())
        try:
            count = int(t.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        low = name.casefold()
        if not name or count < MIN_COUNT or len(name) > 40 or _norm(name) == _norm(artist):
            continue
        if known is not None:
            if genre_names.key(name) not in known:
                continue
        elif _NOT_GENRES.match(low):
            continue
        out.append(genre_name(low))
    return genre_names.split(out)


def find_genre(artist, album, api_key, known=None):
    """{"genre", "genres", "source": "album", "release"} from the album's Last.fm tags, or None."""
    if not (album or "").strip() or not (artist or "").strip() or not api_key:
        return None
    data = _get("album.getTopTags", {"artist": artist, "album": album}, api_key)
    tags = ((data.get("toptags") or {}).get("tag")) or []
    if isinstance(tags, dict):
        tags = [tags]
    names = filter_tags(tags, known, artist)[:5]
    if not names:
        return None
    return {"genre": names[0], "genres": names, "source": "album", "release": album}


_READ_MORE = re.compile(r"<a href=\"[^\"]*\">Read more on Last\.fm</a>.*$", re.S)


def plain_bio(text):
    """A Last.fm bio as plain text (without its "Read more on Last.fm" link and licence line)."""
    text = _READ_MORE.sub("", text or "")
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"[ \t]+", " ", text.replace("\r", ""))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def artist_bio(name, api_key, lang=""):
    """{"text", "url", "source": "Last.fm"} or None."""
    if not (name or "").strip() or not api_key:
        return None
    params = {"artist": name}
    if lang:
        params["lang"] = lang
    data = _get("artist.getInfo", params, api_key)
    artist = data.get("artist") or {}
    bio = artist.get("bio") or {}
    text = plain_bio(bio.get("content") or bio.get("summary") or "")
    if not text:
        return None
    return {"text": text, "url": artist.get("url", ""), "source": "Last.fm"}


def similar_artists(name, api_key, limit=40):
    """Artists Last.fm's listeners find like `name`, closest first: [{"name", "match" (0–1)}]."""
    if not (name or "").strip() or not api_key:
        return []
    data = _get("artist.getSimilar", {"artist": name, "limit": str(limit)}, api_key)
    out, seen = [], set()
    for a in ((data.get("similarartists") or {}).get("artist") or []):
        n = str(a.get("name") or "").strip()
        if not n or n.casefold() in seen:
            continue
        seen.add(n.casefold())
        try:
            match = max(0.0, min(1.0, float(a.get("match") or 0)))
        except (TypeError, ValueError):
            match = 0.0
        out.append({"name": n[:200], "match": match})
    return out
