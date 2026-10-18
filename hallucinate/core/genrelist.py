"""MusicBrainz's list of genres (about two thousand names), for telling which Last.fm tags are genres.

Fetched once (one request) and kept in the data folder for a month; when it can't be had, None, and the
Last.fm tags are filtered by what they look like instead (see core.lastfm)."""
import time
import urllib.request
from pathlib import Path

from . import genres as genre_names
from . import net
from .musicbrainz import USER_AGENT

URL = "https://musicbrainz.org/ws/2/genre/all?fmt=txt"
KEEP_S = 30 * 86_400
_cache = {}


def known(data_dir, now=None):
    """The genre names (as genres.key), or None."""
    now = time.time() if now is None else now
    path = Path(data_dir) / "genres-musicbrainz.txt"
    if path in _cache:
        return _cache[path]
    names = None
    try:
        fresh = path.stat().st_mtime > now - KEEP_S
    except OSError:
        fresh = False
    if not fresh and not net.is_offline():
        try:
            request = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
            with net.urlopen(request, timeout=20, limit=1_000_000) as resp:
                text = resp.read().decode("utf-8")
            if len(text.splitlines()) > 100:  # a real list, not an error page
                tmp = path.with_suffix(".tmp")
                tmp.write_text(text, encoding="utf-8")
                tmp.replace(path)
        except (OSError, ValueError):
            pass
    try:
        names = {genre_names.key(line.strip()) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()}
    except OSError:
        names = None
    if names:
        _cache[path] = names
    return names or None
