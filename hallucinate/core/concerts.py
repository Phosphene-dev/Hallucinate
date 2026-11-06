"""Concerts nearby, for Discover: upcoming shows by the artists you play, near a place you type in.

Two services, both asked only once the shelf is switched on (and never in offline mode):

- OpenStreetMap's Nominatim turns the place you typed into a point on the map, once (when you type it). Only that
  text is sent.
- Ticketmaster's Discovery API, with a key of your own (free from developer.ticketmaster.com: it's yours, kept in
  the system keyring), lists each artist's shows within the distance you chose of that point. Only the artist's
  name and the point are sent. A show is kept only when the artist is named among its performers, so a keyword
  that happens to match something else doesn't bring in strangers.

What's found is kept in the library, so the shelf shows at once; each artist is asked again every few days."""
import datetime
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .. import __version__
from . import net
from .db import fold

USER_AGENT = f"Hallucinate/{__version__} ( https://github.com/Phosphene-dev/Hallucinate )"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
TICKETMASTER = "https://app.ticketmaster.com/discovery/v2/events.json"
RADII = (25, 50, 100, 250)  # km
GEOHASH = "0123456789bcdefghjkmnpqrstuvwxyz"
LINK_HOSTS = re.compile(r"^https://([a-z0-9-]+\.)*(ticketmaster|livenation|ticketweb|universe)\.[a-z.]+(/|$)")


class BadKey(OSError):
    """Ticketmaster didn't take the key."""


def _json(url, timeout=15, limit=2_000_000):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with net.urlopen(request, timeout=timeout, limit=limit) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _text(value, limit=200):
    return str(value or "").strip()[:limit]


# --- where -----------------------------------------------------------------------------------------------------
def geocode(place):
    """{"lat", "lon", "name"} for a place typed in ("Lyon", "Brooklyn, NY"), or None when it isn't found."""
    place = _text(place, 120)
    if not place:
        return None
    query = urllib.parse.urlencode({"q": place, "format": "jsonv2", "limit": 1, "addressdetails": 0})
    found = _json(f"{NOMINATIM}?{query}", limit=200_000)
    if not isinstance(found, list) or not found or not isinstance(found[0], dict):
        return None
    try:
        lat, lon = float(found[0]["lat"]), float(found[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"lat": lat, "lon": lon, "name": _text(found[0].get("display_name"), 200) or place}


def geohash(lat, lon, precision=9):
    """The point as a geohash (what Ticketmaster takes as geoPoint)."""
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    out, bits, ch, even = [], 0, 0, True
    while len(out) < precision:
        rng, value = (lon_range, lon) if even else (lat_range, lat)
        mid = (rng[0] + rng[1]) / 2
        if value >= mid:
            ch = (ch << 1) | 1
            rng[0] = mid
        else:
            ch <<= 1
            rng[1] = mid
        even = not even
        bits += 1
        if bits == 5:
            out.append(GEOHASH[ch])
            bits, ch = 0, 0
    return "".join(out)


def place_key(lat, lon, radius):
    """What a set of results was looked up for (a new place or distance means looking again)."""
    return f"{geohash(lat, lon, 6)}:{int(radius)}"


# --- Ticketmaster ----------------------------------------------------------------------------------------------
def _ask(params, key):
    query = urllib.parse.urlencode({**params, "apikey": key})
    try:
        return _json(f"{TICKETMASTER}?{query}")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise BadKey("Ticketmaster didn't accept the key") from None
        raise


def check_key(key):
    """Raises BadKey when Ticketmaster doesn't take `key` (and OSError when it can't be asked)."""
    if not _text(key):
        raise BadKey("no key")
    _ask({"size": 1, "classificationName": "music"}, _text(key, 100))


def _link(url):
    url = _text(url, 1000)
    return url if LINK_HOSTS.match(url) else ""


def shows(artist, key, lat, lon, radius, today=None):
    """`artist`'s upcoming shows within `radius` km of the point: [{"id", "artist", "name", "date", "time",
    "venue", "city", "country", "link", "status"}], soonest first ("status": "", "cancelled" or "postponed")."""
    today = today or datetime.date.today()
    params = {"keyword": _text(artist, 100), "classificationName": "music", "geoPoint": geohash(lat, lon),
              "radius": int(radius), "unit": "km", "sort": "date,asc", "size": 50, "locale": "*",
              "startDateTime": f"{today.isoformat()}T00:00:00Z"}
    data = _ask(params, _text(key, 100))
    events = ((data or {}).get("_embedded") or {}).get("events") or []
    wanted = fold(artist).strip()
    out = []
    for e in events:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        inner = e.get("_embedded") or {}
        performers = [fold(a.get("name", "")).strip() for a in inner.get("attractions") or [] if isinstance(a, dict)]
        if wanted not in performers:
            continue  # (a show that only matched the keyword)
        start = (e.get("dates") or {}).get("start") or {}
        date = _text(start.get("localDate"), 10)
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date) or date < today.isoformat():
            continue
        status = _text(((e.get("dates") or {}).get("status") or {}).get("code"), 20)
        venue = (inner.get("venues") or [{}])[0] if inner.get("venues") else {}
        venue = venue if isinstance(venue, dict) else {}
        out.append({"id": _text(e["id"], 64), "artist": _text(artist), "name": _text(e.get("name")),
                    "date": date, "time": _text(start.get("localTime"), 8) if not start.get("timeTBA") else "",
                    "venue": _text(venue.get("name")), "city": _text((venue.get("city") or {}).get("name"), 100),
                    "country": _text((venue.get("country") or {}).get("name"), 100),
                    "link": _link(e.get("url")),
                    "status": "cancelled" if status == "cancelled" else "postponed" if status in (
                        "postponed", "rescheduled") else ""})
    return out


# --- kept in the library ---------------------------------------------------------------------------------------
def checked(db, s_aa, place):
    row = db.conn.execute("SELECT checked FROM concerts_checked WHERE s_aa = ? AND place = ?", (s_aa, place)).fetchone()
    return row[0] if row else 0.0


def store(db, s_aa, place, found, now):
    """Replaces what was known of this artist's shows near `place`."""
    db.conn.execute("DELETE FROM concerts WHERE s_aa = ? AND place = ?", (s_aa, place))
    db.conn.executemany(
        "INSERT OR REPLACE INTO concerts(id, s_aa, place, artist, name, date, time, venue, city, country, link,"
        " status, found) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(c["id"], s_aa, place, c["artist"], c["name"], c["date"], c["time"], c["venue"], c["city"], c["country"],
          c["link"], c["status"], now) for c in found])
    db.conn.execute("INSERT OR REPLACE INTO concerts_checked(s_aa, place, checked) VALUES (?, ?, ?)", (s_aa, place, now))
    db.conn.commit()


def upcoming(db, place, today=None, limit=60):
    """The shows kept for `place` from today on, soonest first, leaving out artists marked Not interested."""
    today = (today or datetime.date.today()).isoformat()
    rows = db.conn.execute(
        "SELECT id, artist, name, date, time, venue, city, country, link, status FROM concerts"
        " WHERE place = ? AND date >= ? ORDER BY date, time, artist LIMIT ?", (place, today, limit * 2)).fetchall()
    dismissed = {r[0] for r in db.conn.execute("SELECT key FROM discover_dismissed WHERE kind = 'artist'")}
    keys = ("id", "artist", "name", "date", "time", "venue", "city", "country", "link", "status")
    out = [dict(zip(keys, r)) for r in rows if fold(r[1]).strip() not in dismissed]
    return out[:limit]


def forget(db):
    db.conn.execute("DELETE FROM concerts")
    db.conn.execute("DELETE FROM concerts_checked")
    db.conn.commit()
