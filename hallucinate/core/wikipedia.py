"""An artist's bio from Wikipedia: the opening of their article, found through MusicBrainz (which links each
artist to their Wikidata entry, and that to the article in each language), so a band isn't confused with
a film or a town of the same name. The text is Wikipedia's (CC BY-SA); the page shows where it came from.
Every request goes through core.net, so offline mode stops it."""
import json
import re
import urllib.parse
import urllib.request

from . import musicbrainz, net

USER_AGENT = musicbrainz.USER_AGENT


def _fetch(url, timeout=15):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with net.urlopen(request, timeout=timeout, limit=3_000_000) as resp:
        return json.loads(resp.read().decode("utf-8"))


def artist_id(name, album=""):
    """The MusicBrainz id of an artist: through one of their albums when there is one (two artists can share
    a name), else the best exact-name match."""
    if album:
        query = f"release:{musicbrainz._quote(album)} AND artist:{musicbrainz._quote(name)}"
        for r in musicbrainz._get("release/", {"query": query, "limit": "5"}).get("releases", []):
            if int(r.get("score") or 0) < 85 or not musicbrainz._same(r.get("title", ""), album):
                continue
            for c in r.get("artist-credit") or []:
                a = c.get("artist") or {}
                if musicbrainz._same(a.get("name", ""), name):
                    return a.get("id")
    data = musicbrainz._get("artist/", {"query": f"artist:{musicbrainz._quote(name)}", "limit": "5"})
    for a in data.get("artists", []):
        if int(a.get("score") or 0) >= 90 and musicbrainz._same(a.get("name", ""), name):
            return a.get("id")
    return None


def _article(mbid, lang):
    """(language, title) of the artist's article, preferring `lang`, else English."""
    data = musicbrainz._get(f"artist/{urllib.parse.quote(mbid)}", {"inc": "url-rels"})
    wikidata, wiki = None, None
    for rel in data.get("relations") or []:
        url = (rel.get("url") or {}).get("resource", "")
        if rel.get("type") == "wikidata":
            wikidata = url.rstrip("/").rsplit("/", 1)[-1]
        elif rel.get("type") == "wikipedia" and not wiki:
            m = re.match(r"https?://([a-z\-]+)\.wikipedia\.org/wiki/(.+)$", url)
            if m:
                wiki = (m.group(1), urllib.parse.unquote(m.group(2)))
    if wikidata and re.fullmatch(r"Q\d+", wikidata):
        wanted = [f"{lang}wiki"] if lang and lang != "en" else []
        sites = "|".join(wanted + ["enwiki"])
        got = _fetch("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": wikidata, "props": "sitelinks", "sitefilter": sites,
             "format": "json"}))
        links = ((got.get("entities") or {}).get(wikidata) or {}).get("sitelinks") or {}
        for site in wanted + ["enwiki"]:
            if site in links and links[site].get("title"):
                return site[:-4], links[site]["title"]
    return wiki


def artist_bio(name, album="", lang="en"):
    """{"text", "url", "source": "Wikipedia"} or None."""
    if not (name or "").strip():
        return None
    mbid = artist_id(name, album)
    if not mbid:
        return None
    found = _article(mbid, lang)
    if not found:
        return None
    lang, title = found
    if not re.fullmatch(r"[a-z\-]{2,12}", lang):
        return None
    data = _fetch(f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "prop": "extracts", "exintro": "1", "explaintext": "1", "redirects": "1",
         "titles": title, "format": "json"}))
    pages = ((data.get("query") or {}).get("pages") or {}).values()
    for page in pages:
        text = re.sub(r"\n{3,}", "\n\n", (page.get("extract") or "").strip())
        if text:
            url = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(page.get("title", title).replace(" ", "_"))
            return {"text": text, "url": url, "source": "Wikipedia"}
    return None
