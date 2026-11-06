"""Discover's online parts, each off until switched on: new releases by the artists you play (MusicBrainz),
artists like yours that aren't in your library (ListenBrainz, Deezer or Last.fm), and short previews of them
(Deezer or Apple).

Only artist names (and MusicBrainz's ids for them) are sent; nothing about what you play. Every request goes
through core.net, so offline mode stops it, and MusicBrainz is asked at most once a second, as it asks. A
preview link is asked for when it's played (they expire), never kept."""
import json
import os
import re
import urllib.parse
import urllib.request

from .. import __version__
from . import net
from .db import fold
from .musicbrainz import _get as mb_get
from .musicbrainz import _same

USER_AGENT = f"Hallucinate/{__version__} ( https://github.com/Phosphene-dev/Hallucinate )"
LB_SIMILAR = "https://labs.api.listenbrainz.org/similar-artists/json"
# ListenBrainz's own choice for its similar artists (what its site uses)
LB_ALGORITHM = "session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30"
DEEZER = "https://api.deezer.com/"
ITUNES = "https://itunes.apple.com/search"
COVER = "https://coverartarchive.org/release-group/{}/front-250"
MBID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
KINDS = ("Album", "EP", "Single")
MAX_IMAGE = 2_000_000


def _json(url, timeout=15, limit=2_000_000):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with net.urlopen(request, timeout=timeout, limit=limit) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _text(value, limit=300):
    return str(value or "").strip()[:limit]


def _web(url):
    """`url` when it's an https link (a link to show or open), else ""."""
    url = _text(url, 1000)
    return url if url.startswith("https://") else ""


# --- MusicBrainz: who an artist is, and what they've put out lately ----------------------------------------
def artist_id(name):
    """The MusicBrainz id of the artist called `name`, or "" when there's no confident match (a wrong artist's
    releases are worse than none)."""
    if not _text(name):
        return ""
    data = mb_get("artist/", {"query": f'artist:"{_quote(name)}"', "limit": "5"})
    for a in data.get("artists") or []:
        if int(a.get("score") or 0) < 90:
            continue
        names = [a.get("name", "")] + [x.get("name", "") for x in a.get("aliases") or []]
        if any(_same(n, name) for n in names) and MBID.match(str(a.get("id", ""))):
            return a["id"]
    return ""


def _quote(text):
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", text)


def releases_since(mbid, since):
    """Release groups the artist `mbid` put out on or after `since` ("YYYY-MM-DD"), newest first:
    [{"id", "title", "kind" (Album, EP, Single), "extra" (["Live", "Compilation"…]), "date", "artist"}]. Only
    albums, EPs and singles; ones they're only a guest on are left out."""
    if not MBID.match(mbid or ""):
        return []
    data = mb_get("release-group/", {"query": f"arid:{mbid} AND firstreleasedate:[{since} TO *]", "limit": "50"})
    out = []
    for g in data.get("release-groups") or []:
        kind, date = g.get("primary-type") or "", _text(g.get("first-release-date"), 10)
        credits = g.get("artist-credit") or []
        first = (credits[0].get("artist") or {}).get("id") if credits else ""
        if kind not in KINDS or not date or padded(date) < since or first != mbid or not MBID.match(str(g.get("id", ""))):
            continue
        out.append({"id": g["id"], "title": _text(g.get("title")), "kind": kind,
                    "extra": [_text(x, 40) for x in g.get("secondary-types") or []][:6], "date": date,
                    "artist": _text("".join(c.get("name", "") + c.get("joinphrase", "") for c in credits))})
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def padded(date):
    """"2025-08" as "2025-08-01" and "2025" as "2025-01-01", for comparing (MusicBrainz may know only the month or
    the year)."""
    return date + "-01-01"[len(date) - 4:] if len(date) in (4, 7) else date


def release_link(mbid):
    return f"https://musicbrainz.org/release-group/{mbid}" if MBID.match(mbid or "") else ""


def cover_url(mbid):
    return COVER.format(mbid) if MBID.match(mbid or "") else ""


# --- similar artists -----------------------------------------------------------------------------------------
def similar_listenbrainz(mbid, limit=30):
    """[{"name", "score" (0–1), "mbid", "url"}] from ListenBrainz, for the artist `mbid`."""
    if not MBID.match(mbid or ""):
        return []
    data = _json(LB_SIMILAR + "?" + urllib.parse.urlencode({"artist_mbids": mbid, "algorithm": LB_ALGORITHM}))
    rows = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
    top = max((float(r.get("score") or 0) for r in rows), default=0) or 1.0
    out = []
    for r in rows[:limit]:
        name, other = _text(r.get("name"), 200), str(r.get("artist_mbid") or "")
        if name and MBID.match(other) and other != mbid:
            out.append({"name": name, "score": round(float(r.get("score") or 0) / top, 3), "mbid": other,
                        "url": f"https://listenbrainz.org/artist/{other}/"})
    return out


def deezer_artist(name):
    """{"id", "name", "picture", "url"} for the artist called `name` on Deezer, or None."""
    if not _text(name):
        return None
    data = _json(DEEZER + "search/artist?" + urllib.parse.urlencode({"q": name, "limit": "5"}))
    for a in data.get("data") or []:
        if _same(a.get("name", ""), name) and isinstance(a.get("id"), int):
            return {"id": a["id"], "name": _text(a.get("name"), 200), "picture": _web(a.get("picture_medium")),
                    "url": _web(a.get("link"))}
    return None


def similar_deezer(name, limit=30):
    """[{"name", "score", "picture", "url"}] of artists Deezer relates to `name`, closest first."""
    a = deezer_artist(name)
    if a is None:
        return []
    data = _json(DEEZER + f"artist/{a['id']}/related?" + urllib.parse.urlencode({"limit": str(limit)}))
    rows = data.get("data") or []
    return [{"name": _text(r.get("name"), 200), "score": round(1 - i / max(1, len(rows)), 3),
             "picture": _web(r.get("picture_medium")), "url": _web(r.get("link"))}
            for i, r in enumerate(rows) if _text(r.get("name"))]


def similar_lastfm(name, api_key, limit=30):
    from . import lastfm

    return [{"name": s["name"], "score": s["match"], "url": "https://www.last.fm/music/" + urllib.parse.quote_plus(s["name"])}
            for s in lastfm.similar_artists(name, api_key, limit)]


# --- previews --------------------------------------------------------------------------------------------------
def preview(artist, source="deezer"):
    """A 30-second preview of the artist's best known song: {"title", "artist", "url" (the audio), "link" (its
    page)}, or None. Asked for when it's played: the links expire."""
    if not _text(artist):
        return None
    if source == "itunes":
        data = _json(ITUNES + "?" + urllib.parse.urlencode({"term": artist, "entity": "song", "limit": "10",
                                                            "media": "music"}))
        for r in data.get("results") or []:
            if _same(r.get("artistName", ""), artist) and _web(r.get("previewUrl")):
                return {"title": _text(r.get("trackName")), "artist": _text(r.get("artistName")),
                        "url": _web(r["previewUrl"]), "link": _web(r.get("trackViewUrl"))}
        return None
    a = deezer_artist(artist)
    if a is None:
        return None
    data = _json(DEEZER + f"artist/{a['id']}/top?limit=5")
    for r in data.get("data") or []:
        if _web(r.get("preview")):
            return {"title": _text(r.get("title")), "artist": a["name"], "url": _web(r["preview"]),
                    "link": _web(r.get("link"))}
    return None


# --- pictures ----------------------------------------------------------------------------------------------------
def fetch_image(url, folder):
    """Downloads a cover or artist picture (https, at most MAX_IMAGE, a JPEG, PNG or WebP) into `folder`, named
    for its link; returns the file's path, or "" when it couldn't be had. Already there: not fetched again."""
    import hashlib

    url = _web(url)
    if not url:
        return ""
    path = os.path.join(folder, hashlib.sha1(url.encode("utf-8")).hexdigest()[:24] + ".img")
    if os.path.exists(path):
        return path
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with net.urlopen(request, timeout=15, limit=MAX_IMAGE) as resp:
            data = resp.read()
    except (OSError, ValueError):
        return ""
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        return ""
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


# --- stores, for the wishlist ---------------------------------------------------------------------------------
STORES = {
    "bandcamp": ("Bandcamp", "https://bandcamp.com/search?q={q}"),
    "qobuz": ("Qobuz", "https://www.qobuz.com/search?q={q}"),
    "apple": ("Apple Music", "https://music.apple.com/search?term={q}"),
    "amazon": ("Amazon", "https://www.amazon.com/s?k={q}&i=digital-music"),
    "discogs": ("Discogs", "https://www.discogs.com/search/?q={q}&type=all"),
    "hdtracks": ("HDtracks", "https://www.hdtracks.com/#/search?q={q}"),
    "7digital": ("7digital", "https://www.7digital.com/search?q={q}"),
    "web": ("The web", "https://duckduckgo.com/?q={q}"),
}


def store_link(store, artist, title=""):
    """A search for the artist (and album) on `store` (one of STORES)."""
    _name, pattern = STORES.get(store) or STORES["bandcamp"]
    q = " ".join(t for t in (_text(artist, 200), _text(title, 200)) if t)
    return pattern.format(q=urllib.parse.quote_plus(q))


# --- the wishlist (the library's own table) ---------------------------------------------------------------------
def wish_key(kind, artist, title=""):
    return f"{kind}|{fold(artist).strip()}|{fold(title).strip()}"


def wishes(db):
    rows = db.conn.execute("SELECT * FROM wishlist ORDER BY got IS NOT NULL, added DESC").fetchall()
    return [dict(r) for r in rows]


def wish(db, kind, artist, title="", note="", link="", ref="", now=0.0):
    """Adds an album ("album": `artist`, `title`) or an artist ("artist": `artist`) to the wishlist; already on
    it, it stays as it was. Returns its key."""
    kind = kind if kind in ("album", "artist") else "album"
    artist, title = _text(artist, 300), (_text(title, 300) if kind == "album" else "")
    if not artist:
        return ""
    key = wish_key(kind, artist, title)
    db.conn.execute(
        "INSERT OR IGNORE INTO wishlist(key, kind, artist, title, note, link, ref, added) VALUES (?,?,?,?,?,?,?,?)",
        (key, kind, artist, title, _text(note, 1000), _web(link), _text(ref, 64), now))
    db.conn.commit()
    return key


def unwish(db, key):
    db.conn.execute("DELETE FROM wishlist WHERE key = ?", (key,))
    db.conn.commit()


def set_note(db, key, note):
    db.conn.execute("UPDATE wishlist SET note = ? WHERE key = ?", (_text(note, 1000), key))
    db.conn.commit()


def tick_off(db, now):
    """Marks wishes that are now in the library as got (an album by its artist and title, an artist by name);
    returns those just ticked off."""
    found = []
    for w in db.conn.execute("SELECT * FROM wishlist WHERE got IS NULL").fetchall():
        if w["kind"] == "album":
            rows = db.conn.execute("SELECT album, album_artist, artist FROM tracks WHERE s_album = ? OR s_album = ? LIMIT 50",
                                   (fold(w["title"]), fold(w["title"]).strip())).fetchall()
            hit = any(_same(r["album"], w["title"]) and (_same(r["album_artist"], w["artist"]) or _same(r["artist"], w["artist"]))
                      for r in rows)
            if not hit:  # (an edition's title can differ: "(Deluxe)", so compare loosely)
                rows = db.conn.execute("SELECT album, album_artist, artist FROM tracks WHERE s_aa = ? OR s_artist = ? "
                                       "GROUP BY album LIMIT 500", (fold(w["artist"]), fold(w["artist"]))).fetchall()
                hit = any(_same(r["album"], w["title"]) for r in rows)
        else:
            hit = db.conn.execute("SELECT 1 FROM tracks WHERE s_aa = ? OR s_artist = ? LIMIT 1",
                                  (fold(w["artist"]), fold(w["artist"]))).fetchone() is not None
        if hit:
            db.conn.execute("UPDATE wishlist SET got = ? WHERE key = ?", (now, w["key"]))
            found.append(dict(w))
    if found:
        db.conn.commit()
    return found


# --- what's kept of it ---------------------------------------------------------------------------------------------
NOT_ARTISTS = {"", "various artists", "various", "va", "unknown artist", "[unknown]", "soundtrack"}


def top_artists(db, limit=50):
    """[(folded name, name)]: the album artists you play most (then, past those you've played, the ones with the
    most songs), `limit` of them (0: all of them)."""
    rows = db.conn.execute(
        "SELECT t.s_aa AS key, MAX(t.album_artist) AS name, COALESCE(SUM(p.count), 0) AS plays, COUNT(*) AS n "
        "FROM tracks t LEFT JOIN plays p ON p.path = t.path WHERE t.s_aa != '' GROUP BY t.s_aa "
        "ORDER BY plays DESC, n DESC" + (" LIMIT ?" if limit else ""), (limit + 20,) if limit else ()).fetchall()
    out = [(r["key"], r["name"]) for r in rows if r["key"] not in NOT_ARTISTS and r["name"]]
    return out[:limit] if limit else out


def known_mbid(db, key):
    r = db.conn.execute("SELECT mbid, looked FROM online_artists WHERE s_aa = ?", (key,)).fetchone()
    return (r["mbid"], r["looked"]) if r else (None, 0.0)


def remember_mbid(db, key, name, mbid, now):
    db.conn.execute("INSERT INTO online_artists(s_aa, name, mbid, looked) VALUES (?,?,?,?) ON CONFLICT(s_aa) DO UPDATE "
                    "SET name=excluded.name, mbid=excluded.mbid, looked=excluded.looked", (key, name, mbid, now))
    db.conn.commit()


def releases_checked(db, key):
    r = db.conn.execute("SELECT releases_checked FROM online_artists WHERE s_aa = ?", (key,)).fetchone()
    return r["releases_checked"] if r else 0.0


def store_releases(db, key, releases, now):
    """Keeps what was found for the artist `key` (the ones already known keep when they were found)."""
    for r in releases:
        db.conn.execute(
            "INSERT INTO new_releases(id, s_aa, artist, title, kind, extra, date, found) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, kind=excluded.kind, extra=excluded.extra, "
            "date=excluded.date, artist=excluded.artist",
            (r["id"], key, r["artist"], r["title"], r["kind"], ",".join(r["extra"]), r["date"], now))
    db.conn.execute("UPDATE online_artists SET releases_checked = ? WHERE s_aa = ?", (now, key))
    db.conn.commit()


def set_release_cover(db, rid, path):
    db.conn.execute("UPDATE new_releases SET cover = ? WHERE id = ?", (path, rid))
    db.conn.commit()


def _owned_albums(db, key):
    return [r[0] for r in db.conn.execute("SELECT DISTINCT album FROM tracks WHERE s_aa = ?", (key,))]


def recent_releases(db, since, kinds=("Album", "EP"), live=False, compilations=False, limit=60):
    """New releases since `since` ("YYYY-MM-DD") of the kinds asked, newest first, leaving out ones you already
    have (by title), ones marked Not interested, and live albums or compilations unless asked for."""
    rows = db.conn.execute(
        "SELECT * FROM new_releases WHERE (date || substr('-01-01', length(date) - 3)) >= ? AND id NOT IN "
        "(SELECT key FROM discover_dismissed WHERE kind = 'release') AND s_aa NOT IN "
        "(SELECT key FROM discover_dismissed WHERE kind = 'artist') ORDER BY date DESC, found DESC",
        (since,)).fetchall()
    owned, out = {}, []
    for r in rows:
        extra = [e for e in r["extra"].split(",") if e]
        if r["kind"] not in kinds or ("Live" in extra and not live) or ("Compilation" in extra and not compilations):
            continue
        if any(e in extra for e in ("Interview", "Audiobook", "Spokenword", "Audio drama")):
            continue
        if r["s_aa"] not in owned:
            owned[r["s_aa"]] = _owned_albums(db, r["s_aa"])
        if any(_same(a, r["title"]) for a in owned[r["s_aa"]]):
            continue
        out.append({**dict(r), "extra": extra})
        if len(out) >= limit:
            break
    return out


def mark_seen(db, ids):
    if ids:
        db.conn.executemany("UPDATE new_releases SET seen = 1 WHERE id = ?", [(i,) for i in ids])
        db.conn.commit()


def similar_fetched(db, seed, source):
    r = db.conn.execute("SELECT fetched FROM online_similar WHERE seed = ? AND source = ?", (seed, source)).fetchone()
    return r["fetched"] if r else 0.0


def store_similar(db, seed, source, names, now):
    db.conn.execute("INSERT OR REPLACE INTO online_similar(seed, source, names, fetched) VALUES (?,?,?,?)",
                    (seed, source, json.dumps(names), now))
    db.conn.commit()


def suggestions(db, seeds, source, limit=30):
    """Artists like the ones you play (`seeds`: [(folded name, name)], most played first) that aren't in your
    library and weren't marked Not interested: [{"name", "key", "score", "because" (up to 3 of yours), "url",
    "picture", "mbid"}], best first. An artist like several of yours counts for more."""
    have = {r[0] for r in db.conn.execute("SELECT DISTINCT s_aa FROM tracks")}
    have |= {r[0] for r in db.conn.execute("SELECT DISTINCT s_artist FROM tracks")}
    left_out = {r[0] for r in db.conn.execute("SELECT key FROM discover_dismissed WHERE kind = 'artist'")}
    found = {}
    for rank, (key, name) in enumerate(seeds):
        r = db.conn.execute("SELECT names FROM online_similar WHERE seed = ? AND source = ?", (key, source)).fetchone()
        if r is None:
            continue
        try:
            names = json.loads(r["names"]) or []
        except ValueError:
            continue
        weight = 1.0 / (1 + rank * 0.15)  # (your most played count a little more)
        for s in names:
            k = fold(s.get("name", "")).strip()
            if not k or k in have or k in left_out or k in NOT_ARTISTS:
                continue
            f = found.setdefault(k, {"name": s["name"], "key": k, "score": 0.0, "because": [], "url": s.get("url", ""),
                                     "picture": s.get("picture", ""), "mbid": s.get("mbid", "")})
            f["score"] += weight * float(s.get("score") or 0)
            if len(f["because"]) < 3:
                f["because"].append(name)
    ranked = sorted(found.values(), key=lambda f: (-len(f["because"]), -f["score"]))
    return ranked[:limit]


def forget(db):
    """Throws away what was found online (not the wishlist)."""
    for table in ("online_artists", "new_releases", "online_similar"):
        db.conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed names
    db.conn.commit()
