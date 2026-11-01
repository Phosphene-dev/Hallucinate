"""Podcasts without Qt: RSS feeds, OPML subscription lists, the Apple Podcasts directory search, chapters,
folders of episodes on disk, and downloading an episode.

Every request goes through core.net, so offline mode stops all of it."""
import email.utils
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import __version__
from . import net
from .i18n import translate

USER_AGENT = f"Hallucinate/{__version__}"
NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "podcast": "https://podcastindex.org/namespace/1.0",
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
}
FEED_LIMIT = 30 * 1024 * 1024
EPISODE_LIMIT = 4 * 1024 ** 3  # a four-hour lossless episode is still well under this
PERMANENT_REDIRECTS = (301, 308)  # a feed that moved for good; 302, 303 and 307 are only for now
AUDIO_EXTENSIONS = (".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".opus", ".oga", ".flac", ".wav", ".mp4")


def _request(url):
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})


def plain_text(markup, limit=4000):
    """Show notes as plain text: tags dropped, paragraphs kept as blank lines, entities decoded."""
    text = markup or ""
    text = re.sub(r"(?i)<\s*br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|div|li|h\d)\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*(\n\s*)+", "\n\n", text)
    return text.strip()[:limit]


def parse_duration(value):
    """Seconds from an itunes:duration ("1:02:03", "62:03", "3723", "3723.5"); 0 when it can't be read."""
    value = (value or "").strip()
    if not value:
        return 0.0
    try:
        if ":" in value:
            total = 0.0
            for part in value.split(":"):
                total = total * 60 + float(part or 0)
            return total
        return float(value)
    except ValueError:
        return 0.0


def parse_date(value):
    """A Unix time from an RSS (RFC 822) or Atom (ISO 8601) date; 0 when it can't be read."""
    value = (value or "").strip()
    if not value:
        return 0.0
    try:
        return email.utils.parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _text(node, path):
    found = node.find(path, NS)
    return (found.text or "").strip() if found is not None and found.text else ""


def _attr(node, path, name):
    found = node.find(path, NS)
    return (found.get(name) or "").strip() if found is not None else ""


def _xml(data, what):  # what: the error to give ("That isn't a podcast feed")
    """Parse XML from the internet (or a file someone sent). Feeds and OPML never need a DOCTYPE, and one
    that declares entities is the way to make a parser expand a few bytes into gigabytes ("billion laughs"):
    such documents are refused before parsing."""
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    # anywhere in it, not only near the top: comments may come before a DOCTYPE, as many as a feed likes
    if re.search(rb"<!(?:ENTITY|DOCTYPE)", raw, re.IGNORECASE):
        raise ValueError(what)
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(what) from exc


def parse_feed(data, feed_url=""):
    """(podcast, episodes) from an RSS or Atom feed. Episodes without audio are left out. Raises ValueError
    when it isn't a feed."""
    root = _xml(data, translate("Podcasts", "That isn't a podcast feed"))
    tag = root.tag.split("}")[-1]
    if tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise ValueError(translate("Podcasts", "The feed has no channel"))
        items, atom = channel.findall("item"), False
    elif tag == "feed":
        channel, items, atom = root, root.findall("atom:entry", NS), True
    else:
        raise ValueError(translate("Podcasts", "That isn't a podcast feed"))

    def link_of(node):
        if atom:
            for link in node.findall("atom:link", NS):
                if link.get("rel", "alternate") == "alternate":
                    return link.get("href", "")
            return ""
        return _text(node, "link")

    title_path = "atom:title" if atom else "title"
    image = (_attr(channel, "itunes:image", "href") or _text(channel, "image/url")
             or _text(channel, "atom:logo") or _text(channel, "atom:icon"))
    podcast = {
        "title": html.unescape(_text(channel, title_path)) or feed_url,
        "author": html.unescape(_text(channel, "itunes:author") or _text(channel, "atom:author/atom:name")
                                or _text(channel, "managingEditor")),
        "link": _web_only(link_of(channel)), "image": _web_only(image), "feed_url": feed_url,
        "description": plain_text(_text(channel, "itunes:summary") or _text(channel, "description")
                                  or _text(channel, "atom:subtitle"), 2000),
    }
    episodes = []
    for item in items:
        if atom:
            enclosure = next((ln for ln in item.findall("atom:link", NS) if ln.get("rel") == "enclosure"), None)
            url = enclosure.get("href", "") if enclosure is not None else ""
            mime = enclosure.get("type", "") if enclosure is not None else ""
            size = enclosure.get("length", "0") if enclosure is not None else "0"
            published = parse_date(_text(item, "atom:published") or _text(item, "atom:updated"))
            guid = _text(item, "atom:id") or url
            description = _text(item, "atom:content") or _text(item, "atom:summary")
        else:
            enclosure = item.find("enclosure")
            if enclosure is None:
                enclosure = item.find("media:content", NS)
            url = (enclosure.get("url") or "").strip() if enclosure is not None else ""
            mime = (enclosure.get("type") or "") if enclosure is not None else ""
            size = (enclosure.get("length") or enclosure.get("fileSize") or "0") if enclosure is not None else "0"
            published = parse_date(_text(item, "pubDate"))
            guid = _text(item, "guid") or url
            description = _text(item, "content:encoded") or _text(item, "description") or _text(item, "itunes:summary")
        if not url or (mime and not mime.startswith(("audio/", "video/")) and "mpeg" not in mime):
            continue
        try:
            size = int(size)
        except ValueError:
            size = 0
        url = urllib.parse.urljoin(feed_url, url) if feed_url else url
        if not net.is_web_url(url):
            continue  # file://, ftp://, data:…: a feed only ever points at web addresses
        episodes.append({
            "guid": guid, "title": html.unescape(_text(item, title_path)) or "Untitled episode",
            "description": plain_text(description), "url": url,
            "mime": mime, "size": max(0, size), "published": published,
            "duration": parse_duration(_text(item, "itunes:duration")),
            "image": _web_only(_attr(item, "itunes:image", "href")),
            "chapters_url": _web_only(_attr(item, "podcast:chapters", "url")),
        })
    return podcast, episodes


def _web_only(url):
    """`url` if it's a web address, else "" (a feed's links, images and chapters are never local files)."""
    url = (url or "").strip()
    return url if net.is_web_url(url) else ""


def _feed_link(url):
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        if url.startswith("feed://") or url.startswith("pcast://"):
            url = "https://" + url.split("://", 1)[1]
        else:
            raise OSError(translate("Podcasts", "A feed link starts with http:// or https://"))
    return url


def permanent_url(url, hops):
    """Where a feed lives now for good: its link followed through the redirects `hops` [(status, link)] only
    as long as each one is permanent (301, 308). A temporary one may point somewhere else next time (or be a
    login page or a CDN's), so from there on the link you followed is kept."""
    for code, target in hops:
        if code not in PERMANENT_REDIRECTS:
            break
        url = target
    return url


def fetch_feed(url, timeout=20):
    """(podcast, episodes, url to keep) for a feed link; when the feed moved for good (a permanent redirect)
    its new address is returned so the subscription follows it."""
    got = fetch_feed_if_changed(url, timeout=timeout)
    return got["podcast"], got["episodes"], got["url"]


def fetch_feed_if_changed(url, etag="", modified="", timeout=20):
    """{"podcast", "episodes", "url" (to keep), "etag", "modified"} for a feed link. `etag` and `modified` are
    what the feed's server said last time (its ETag and Last-Modified): given them, a server that has nothing
    new answers "not modified" without sending the feed again, and podcast and episodes are None."""
    url = _feed_link(url)
    request = _request(url)
    if etag:
        request.add_header("If-None-Match", etag)
    if modified:
        request.add_header("If-Modified-Since", modified)
    try:
        with net.urlopen(request, timeout=timeout, limit=FEED_LIMIT) as resp:
            final = resp.geturl() if hasattr(resp, "geturl") else url
            data = resp.read()
            headers = resp.headers
    except urllib.error.HTTPError as exc:
        if exc.code != 304:
            raise
        return {"podcast": None, "episodes": None, "url": permanent_url(url, getattr(request, "redirects", [])),
                "etag": etag, "modified": modified}
    podcast, episodes = parse_feed(data, final or url)
    return {"podcast": podcast, "episodes": episodes, "url": permanent_url(url, getattr(request, "redirects", [])),
            "etag": (headers.get("ETag") or "")[:200], "modified": (headers.get("Last-Modified") or "")[:100]}


# --- OPML ------------------------------------------------------------------------------------------------
def parse_opml(text):
    """[{title, feed_url}] from an OPML subscription list (what other podcast apps export)."""
    root = _xml(text, translate("Podcasts", "That isn't an OPML file"))
    feeds, seen = [], set()
    for outline in root.iter("outline"):
        url = (outline.get("xmlUrl") or outline.get("xmlurl") or "").strip()
        if url and url not in seen:
            seen.add(url)
            feeds.append({"title": (outline.get("title") or outline.get("text") or "").strip(), "feed_url": url})
    return feeds


def make_opml(podcasts):
    """An OPML file listing the feeds of `podcasts` (folders on disk have no feed and are left out)."""
    root = ET.Element("opml", version="2.0")
    head = ET.SubElement(root, "head")
    ET.SubElement(head, "title").text = "Podcasts from Hallucinate"
    ET.SubElement(head, "dateCreated").text = email.utils.formatdate(time.time())
    body = ET.SubElement(root, "body")
    for p in podcasts:
        if p.get("feed_url"):
            ET.SubElement(body, "outline", type="rss", text=p.get("title") or "", title=p.get("title") or "",
                          xmlUrl=p["feed_url"])
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


# --- directory -------------------------------------------------------------------------------------------
def search_directory(query, limit=30, timeout=15):
    """Podcasts matching `query` in Apple's free directory (no account): [{title, author, feed_url, image,
    genre}]. Only feeds come back; nothing is sent but the search words."""
    params = urllib.parse.urlencode({"media": "podcast", "entity": "podcast", "term": query, "limit": str(limit)})
    with net.urlopen(_request("https://itunes.apple.com/search?" + params), timeout=timeout, limit=4_000_000) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = []
    for item in data.get("results", []) if isinstance(data, dict) else []:
        url = (item.get("feedUrl") or "").strip()
        if url.startswith(("http://", "https://")):
            out.append({"title": item.get("collectionName") or item.get("trackName") or url,
                        "author": item.get("artistName") or "", "feed_url": url,
                        "image": _web_only(item.get("artworkUrl600") or item.get("artworkUrl100") or ""),
                        "genre": item.get("primaryGenreName") or ""})
    return out


# --- chapters --------------------------------------------------------------------------------------------
def parse_chapters_json(data):
    """[{start, title}] (seconds) from a Podcasting 2.0 chapters file."""
    try:
        doc = json.loads(data)
    except (ValueError, TypeError):
        return []
    out = []
    for ch in doc.get("chapters", []) if isinstance(doc, dict) else []:
        if isinstance(ch, dict) and ch.get("toc", True) is not False and "startTime" in ch:
            try:
                out.append({"start": float(ch["startTime"]), "title": str(ch.get("title") or "").strip()})
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda c: c["start"])
    return [c for c in out if c["title"]]


def fetch_chapters(url, timeout=10):
    with net.urlopen(_request(url), timeout=timeout, limit=2_000_000) as resp:
        return parse_chapters_json(resp.read())


def file_chapters(path):
    """[{start, title}] from an audio file's own chapter marks (ID3 CHAP frames, MP4 chapters)."""
    try:
        import mutagen

        audio = mutagen.File(path)
    except Exception:  # noqa: BLE001 - a file mutagen can't read simply has no chapters
        return []
    out = []
    tags = getattr(audio, "tags", None)
    if tags is not None and hasattr(tags, "getall"):
        for frame in tags.getall("CHAP"):
            title = ""
            sub = getattr(frame, "sub_frames", {}) or {}
            for key in sub:
                if key.startswith("TIT2"):
                    title = str(sub[key].text[0]) if sub[key].text else ""
            out.append({"start": frame.start_time / 1000.0, "title": title.strip()})
    chapters = getattr(audio, "chapters", None)
    if not out and chapters:
        for ch in chapters:
            out.append({"start": float(getattr(ch, "start", 0)), "title": str(getattr(ch, "title", "")).strip()})
    out.sort(key=lambda c: c["start"])
    return [c for c in out if c["title"]]


# --- folders on disk -------------------------------------------------------------------------------------
def scan_folder(folder):
    """(podcast, episodes) for a folder of episode files: the folder is the show, each audio file an episode
    (newest first by its date tag, else when the file was made)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise OSError(f"{folder} isn't a folder")
    try:
        import mutagen
    except ImportError:  # pragma: no cover - mutagen is a dependency
        mutagen = None
    episodes, show_title, author = [], "", ""
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        title, duration, published = path.stem, 0.0, path.stat().st_mtime
        try:
            audio = mutagen.File(str(path), easy=True) if mutagen else None
        except Exception:  # noqa: BLE001
            audio = None
        if audio is not None:
            tags = audio.tags or {}
            title = (tags.get("title") or [title])[0] or title
            show_title = show_title or (tags.get("album") or [""])[0]
            author = author or (tags.get("artist") or [""])[0]
            date = (tags.get("date") or [""])[0]
            if re.match(r"^\d{4}-\d{2}-\d{2}", date):
                published = parse_date(date[:10] + "T12:00:00") or published
            duration = float(getattr(getattr(audio, "info", None), "length", 0) or 0)
        episodes.append({"guid": str(path), "title": title, "description": "", "url": "", "mime": "",
                         "size": path.stat().st_size, "published": published, "duration": duration,
                         "image": "", "chapters_url": "", "local_path": str(path)})
    episodes.sort(key=lambda e: e["published"], reverse=True)
    cover = next((str(folder / n) for n in ("cover.jpg", "cover.png", "folder.jpg", "folder.png", "artwork.jpg")
                  if (folder / n).is_file()), "")
    return {"title": show_title or folder.name, "author": author, "folder": str(folder), "image": cover,
            "description": "", "link": "", "feed_url": ""}, episodes


# --- downloads -------------------------------------------------------------------------------------------
def extension_for(url, mime):
    ext = os.path.splitext(urllib.parse.urlsplit(url).path)[1].lower()
    if ext in AUDIO_EXTENSIONS:
        return ext
    return {"audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
            "audio/aac": ".aac", "audio/ogg": ".ogg", "audio/opus": ".opus", "video/mp4": ".mp4"}.get(mime, ".mp3")


def _resume_from(resp, have):
    """Where a ranged answer carries on from: `have` when the server sent the rest (206 from that byte), else 0
    (it sent the whole file again)."""
    if have and getattr(resp, "status", 200) == 206:
        match = re.match(r"\s*bytes\s+(\d+)-", resp.headers.get("Content-Range") or "")
        if match and int(match.group(1)) == have:
            return have
        raise OSError(translate("Podcasts", "The server sent a different part of the episode than asked for"))
    return 0


def download(url, target, progress=None, cancelled=None, timeout=30, paused=None):
    """Save `url` at `target` (through a .part file, so a broken download never looks finished). A .part left
    by a download that broke off carries on where it stopped (an HTTP Range request) when the server can; a
    server that can't sends it all again. `progress(done, total)` is called as it goes; `cancelled()` returning
    True stops it (raising InterruptedError, and the .part goes); `paused()` returning True stops it the same
    way but keeps the .part, to carry on later."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    keep_part = True  # a download that broke off is carried on next time, from what the .part holds
    try:
        have = part.stat().st_size if part.is_file() else 0
        request = _request(url)
        if have:
            request.add_header("Range", f"bytes={have}-")
        try:
            resp = net.urlopen(request, timeout=timeout, limit=EPISODE_LIMIT)
        except urllib.error.HTTPError as exc:
            if not (have and exc.code == 416):
                raise
            part.unlink()  # what's kept doesn't fit what the server has now: start again
            have, resp = 0, net.urlopen(_request(url), timeout=timeout, limit=EPISODE_LIMIT)
        with resp:
            try:
                start = _resume_from(resp, have)
            except OSError:
                keep_part = False
                raise
            try:
                total = max(0, int(resp.headers.get("Content-Length") or 0))
                total = total + start if total else 0
            except ValueError:  # a garbled header: download anyway, without a percentage
                total = 0
            with open(part, "ab" if start else "wb") as out:
                done, last = start, 0.0
                while True:
                    if cancelled is not None and cancelled():
                        keep_part = False
                        raise InterruptedError(translate("Podcasts", "Download cancelled"))
                    if paused is not None and paused():
                        raise InterruptedError(translate("Podcasts", "Download paused"))
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    now = time.monotonic()
                    if progress is not None and now - last > 0.25:
                        last = now
                        progress(done, total)
        if total and done < total:
            raise OSError(translate("Podcasts", "The download stopped before the end"))
        os.replace(part, target)
        if progress is not None:
            progress(done, total or done)
        return str(target)
    except net.ResponseTooLarge:
        keep_part = False
        raise
    finally:
        if not keep_part and part.exists():
            try:
                part.unlink()
            except OSError:
                pass
