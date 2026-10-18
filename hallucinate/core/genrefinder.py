"""An album's genres from every source you've set up, put together: MusicBrainz, Discogs (with a token) and
Last.fm (with the API key from scrobbling). A genre several sources agree on, or that a source lists first,
ranks higher. The artist's genres (from MusicBrainz) are only used when no source has any for the album.

Nothing here writes anything: these are suggestions, and genres you've set yourself are never replaced (only
albums without a genre are looked up)."""
import logging

from . import discogs, lastfm, musicbrainz
from . import genres as genre_names

logger = logging.getLogger(__name__)
SOURCES = ("MusicBrainz", "Discogs", "Last.fm")
WEIGHT = {"MusicBrainz": 1.0, "Discogs": 1.0, "Last.fm": 0.8}
SUGGESTED = 3  # genres ticked by default; the rest are offered


def combine(found):
    """[(source, [genre, ...])] → the genres ranked, main one first."""
    score, first = {}, {}
    names = {}
    for order, (source, genres) in enumerate(found):
        for pos, g in enumerate(genres):
            key = genre_names.fold(g)
            names.setdefault(key, g)
            score[key] = score.get(key, 0.0) + WEIGHT.get(source, 1.0) / (1 + pos)
            first.setdefault(key, (order, pos))
    return [names[k] for k in sorted(score, key=lambda k: (-score[k], first[k]))]


def find(artist, album, discogs_token="", lastfm_key="", known=None, artist_cache=None, use=SOURCES):
    """{"genre" (the suggested genres as one text), "genres" (every one found, best first), "source": "album"
    | "artist", "sources": [names], "release"} or None."""
    found, release, artist_genres, failed = [], "", None, 0
    tries = []
    if "MusicBrainz" in use:
        tries.append(("MusicBrainz", lambda: musicbrainz.find_genre(artist, album, artist_cache)))
    if "Discogs" in use and discogs_token:
        tries.append(("Discogs", lambda: discogs.find_genre(artist, album, discogs_token)))
    if "Last.fm" in use and lastfm_key:
        tries.append(("Last.fm", lambda: lastfm.find_genre(artist, album, lastfm_key, known)))
    for source, look in tries:
        try:
            hit = look()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.info("%s had no genre for an album: %s", source, exc)
            failed += 1
            continue
        if not hit:
            continue
        if hit["source"] == "artist":
            artist_genres = hit
            continue
        found.append((source, hit["genres"]))
        release = release or hit.get("release", "")
    if failed and failed == len(tries):
        raise OSError("no source could be reached")
    if found:
        ranked = combine(found)
        return {"genre": genre_names.join(ranked[:SUGGESTED]), "genres": ranked[:10], "source": "album",
                "sources": [s for s, _ in found], "release": release}
    if artist_genres:
        return {"genre": artist_genres["genres"][0], "genres": artist_genres["genres"], "source": "artist",
                "sources": ["MusicBrainz"], "release": artist_genres.get("release", "")}
    return None
