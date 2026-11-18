"""Songs identified by how they sound, through AcoustID (https://acoustid.org): a song's fingerprint (see
chromaprint.py) and length go to AcoustID, which answers with the MusicBrainz recordings that sound like it, and
the releases they're on. Only the fingerprint and length are sent, never a file name or a tag.

AcoustID asks every application for a key of its own (free, at https://acoustid.org/new-application) and no
more than three requests a second; both are kept here. Every request goes through core.net, so offline mode
stops it."""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import __version__
from . import net

API = "https://api.acoustid.org/v2/lookup"
USER_AGENT = f"Hallucinate/{__version__} ( https://github.com/Phosphene-dev/Hallucinate )"
# Hallucinate's own application key (https://acoustid.org/new-application); one set in Settings → Online &
# privacy is used instead when there is one
APP_KEY = ""
MIN_SCORE = 0.5  # (below this AcoustID's own match is a guess)
_lock = threading.Lock()
_last = [0.0]


class AcoustIDError(Exception):
    """AcoustID turned the request down: `code` is its error code (4: the key isn't valid)."""

    def __init__(self, message, code=0):
        super().__init__(message)
        self.code = code


def key_in_use(settings_key=""):
    """The key requests go with: yours from Settings, else Hallucinate's own ("" when there's neither)."""
    return (settings_key or "").strip() or APP_KEY


def lookup(key, fingerprint, duration, timeout=20):
    """AcoustID's answer for one fingerprint: its "results" list (each {"score", "recordings": [...]})."""
    with _lock:  # at most three requests a second, as AcoustID asks
        wait = 0.34 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
    body = urllib.parse.urlencode({
        "client": key, "duration": str(int(round(duration))), "fingerprint": fingerprint, "format": "json",
        "meta": "recordings releasegroups releases tracks",
    }).encode("ascii")
    request = urllib.request.Request(API, data=body, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with net.urlopen(request, timeout=timeout, limit=4_000_000) as resp:
            answer = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # AcoustID explains a refusal in the body
        try:
            answer = json.loads(exc.read().decode("utf-8"))
        except (OSError, ValueError):
            raise exc from None
    if answer.get("status") != "ok":
        err = answer.get("error") or {}
        raise AcoustIDError(err.get("message") or "AcoustID error", int(err.get("code") or 0))
    return answer.get("results") or []


def _names(artists):
    return "".join((a.get("name") or "") + (a.get("joinphrase") or "") for a in artists or []).strip()


def _year(release):
    date = release.get("date") or {}
    try:
        return int(date.get("year") or 0)
    except (TypeError, ValueError):
        return 0


def _releases(recording):
    """[(release group, release)] of a recording, whichever way AcoustID nested them."""
    out = []
    for group in recording.get("releasegroups") or []:
        for rel in group.get("releases") or [{}]:
            out.append((group, rel))
    for rel in recording.get("releases") or []:
        out.append((rel.get("releasegroup") or {}, rel))
    return out


def _track(release):
    """(disc, track number, tracks on that disc) of the recording on a release, or (0, 0, 0). AcoustID lists
    only the recording's own track under each medium."""
    for medium in release.get("mediums") or []:
        for t in medium.get("tracks") or []:
            return int(medium.get("position") or 0), int(t.get("position") or 0), int(medium.get("track_count") or 0)
    return 0, 0, 0


def candidates(results, album_hint="", duration=0.0):
    """What AcoustID's results say a song is, best first: [{"title", "artist", "album", "album_artist", "year",
    "track_no", "disc_no", "discs", "score", "recording_id", "release_id"}]. Of a recording's releases, an
    album of its own beats a compilation, live album or soundtrack; then one named like the song's album now
    (`album_hint`); then the earliest."""
    hint = (album_hint or "").strip().casefold()
    out, seen = [], set()
    for result in sorted(results or [], key=lambda r: -(r.get("score") or 0)):
        score = float(result.get("score") or 0)
        if score < MIN_SCORE:
            continue
        for rec in result.get("recordings") or []:
            title = (rec.get("title") or "").strip()
            if not title or rec.get("id") in seen:
                continue  # (a recording AcoustID knows only by id: nothing to fill in)
            seen.add(rec.get("id"))
            if duration and rec.get("duration") and abs(float(rec["duration"]) - duration) > 15:
                continue  # (another length: an edit or a live take)
            artist = _names(rec.get("artists"))

            def rank(pair):
                group, rel = pair
                kinds = [group.get("type") or ""] + list(group.get("secondarytypes") or [])
                plain_album = kinds == ["Album"] or (kinds[0] in ("Album", "EP") and len(kinds) == 1)
                named = (rel.get("title") or group.get("title") or "").strip().casefold() == hint and bool(hint)
                year = _year(rel) or 9999
                return (not named, not plain_album, year)

            pairs = sorted(_releases(rec), key=rank)
            group, rel = pairs[0] if pairs else ({}, {})
            disc, track, _ = _track(rel)
            album = (rel.get("title") or group.get("title") or "").strip()
            album_artist = _names(rel.get("artists") or group.get("artists")) or artist
            out.append({"title": title, "artist": artist, "album": album, "album_artist": album_artist,
                        "year": _year(rel) or min((_year(r) for _, r in pairs if _year(r)), default=0),
                        "track_no": track, "disc_no": disc, "discs": int(rel.get("medium_count") or 0),
                        "score": round(score, 3), "recording_id": rec.get("id") or "", "release_id": rel.get("id") or ""})
    return out
