"""Internet radio without Qt: playlist files (.pls, .m3u), the song titles a stream sends (ICY metadata), and the
Radio Browser directory (https://www.radio-browser.info, free and open, no account).

Every request goes through core.net, so offline mode stops all of it."""
import json
import re
import socket
import urllib.parse
import urllib.request

from .. import __version__
from . import net

USER_AGENT = f"Hallucinate/{__version__}"
PLAYLIST_TYPES = ("audio/x-scpls", "audio/scpls", "audio/x-mpegurl", "audio/mpegurl", "application/pls+xml",
                  "application/xspf+xml")
FALLBACK_SERVERS = ("de1.api.radio-browser.info", "de2.api.radio-browser.info", "fi1.api.radio-browser.info")
MAX_META = 255 * 16  # the largest ICY metadata block


def is_stream_url(text):
    parts = urllib.parse.urlsplit((text or "").strip())
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def parse_playlist(text):
    """Stream links in a .pls, .m3u/.m3u8 or .xspf playlist, in order. HLS playlists (#EXT-X-…) are streams
    themselves, not lists of them, and give []."""
    text = text or ""
    if "#EXT-X-" in text:
        return []
    urls = []
    if re.search(r"^\s*\[playlist\]", text, re.I | re.M):
        entries = sorted((int(n), u.strip()) for n, u in re.findall(r"^\s*File(\d+)\s*=\s*(.+)$", text, re.I | re.M))
        urls = [u for _, u in entries]
    elif "<location>" in text.lower():
        urls = [u.strip() for u in re.findall(r"<location>\s*([^<]+?)\s*</location>", text, re.I)]
    else:
        urls = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    return [u for u in urls if is_stream_url(u)]


def playlist_titles(text):
    """{url: title} from a .pls (TitleN=) or extended .m3u (#EXTINF:…,title) playlist."""
    titles = {}
    if re.search(r"^\s*\[playlist\]", text or "", re.I | re.M):
        files = dict(re.findall(r"^\s*File(\d+)\s*=\s*(.+)$", text, re.I | re.M))
        for n, title in re.findall(r"^\s*Title(\d+)\s*=\s*(.+)$", text, re.I | re.M):
            if n in files:
                titles[files[n].strip()] = title.strip()
    else:
        pending = ""
        for line in (text or "").splitlines():
            line = line.strip()
            if line.upper().startswith("#EXTINF:"):
                pending = line.split(",", 1)[1].strip() if "," in line else ""
            elif line and not line.startswith("#"):
                if pending:
                    titles[line] = pending
                pending = ""
    return titles


def parse_icy_block(block):
    """The song title in an ICY metadata block (b"StreamTitle='Artist - Song';…"), or ""."""
    text = block.rstrip(b"\0").decode("utf-8", errors="replace")
    if "�" in text:
        text = block.rstrip(b"\0").decode("latin-1")
    m = re.search(r"StreamTitle='(.*?)';", text, re.S)
    if not m:
        m = re.search(r"StreamTitle='(.*)'", text, re.S)
    return m.group(1).strip() if m else ""


def split_title(stream_title, station=""):
    """(artist, title) from a stream title. Most stations send "Artist - Song"; anything else is all title.
    A title that's only the station's own name (or empty) says nothing about the song: ("", "")."""
    t = re.sub(r"\s+", " ", stream_title or "").strip()
    if not t or t.lower() == (station or "").strip().lower():
        return "", ""
    for sep in (" - ", " – ", " — ", " ~ "):
        if sep in t:
            artist, title = t.split(sep, 1)
            if artist.strip() and title.strip():
                return artist.strip(), title.strip()
    return "", t


def _request(url, icy=False):
    headers = {"User-Agent": USER_AGENT}
    if icy:
        headers["Icy-MetaData"] = "1"
    return urllib.request.Request(url, headers=headers)


def read_stream_title(url, timeout=8):
    """Connect to a stream just long enough to read its first metadata block: (title, headers). title is ""
    when the stream sends none; headers are the lower-cased response headers (icy-name, icy-genre, …)."""
    with net.urlopen(_request(url, icy=True), timeout=timeout, limit=1_000_000) as resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        try:
            metaint = int(headers.get("icy-metaint", "0"))
        except ValueError:
            metaint = 0
        if metaint <= 0 or metaint > 500_000:
            return "", headers
        left = metaint
        while left > 0:
            chunk = resp.read(min(left, 65536))
            if not chunk:
                return "", headers
            left -= len(chunk)
        size = resp.read(1)
        if not size:
            return "", headers
        block = resp.read(size[0] * 16) if size[0] else b""
        return parse_icy_block(block), headers


def resolve(url, timeout=10):
    """Where a link the user pasted actually streams from, with what the server says about it:
    {"url", "name", "tags", "homepage", "codec", "bitrate"}. A playlist link (.pls, .m3u) is opened and its
    first stream used. Raises OSError when nothing playable answers."""
    url = url.strip()
    if not is_stream_url(url):
        raise OSError("That isn't a web link (it should start with http:// or https://)")
    lower = urllib.parse.urlsplit(url).path.lower()
    looks_like_list = lower.endswith((".pls", ".m3u", ".xspf"))
    with net.urlopen(_request(url, icy=True), timeout=timeout, limit=1_000_000) as resp:
        kind = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        headers = {k.lower(): v for k, v in resp.headers.items()}
        if looks_like_list or kind in PLAYLIST_TYPES:
            text = resp.read(200_000).decode("utf-8", errors="replace")
            streams = parse_playlist(text)
            if not streams:
                if "#EXT-X-" in text:
                    return {"url": url, "name": "", "tags": "", "homepage": "", "codec": "HLS", "bitrate": 0}
                raise OSError("The playlist has no stream links in it")
            info = resolve(streams[0], timeout) if streams[0] != url else {"url": streams[0]}
            info["name"] = info.get("name") or playlist_titles(text).get(streams[0], "")
            return info
        if kind.startswith(("text/html", "application/json")):
            raise OSError("That link is a web page, not a stream")
    codec = {"audio/mpeg": "MP3", "audio/aac": "AAC", "audio/aacp": "AAC+", "audio/ogg": "Ogg",
             "application/ogg": "Ogg", "audio/flac": "FLAC", "application/vnd.apple.mpegurl": "HLS",
             "application/x-mpegurl": "HLS"}.get(kind, "")
    try:
        bitrate = int((headers.get("icy-br") or "0").split(",")[0])
    except ValueError:
        bitrate = 0
    return {"url": url, "name": (headers.get("icy-name") or "").strip(), "tags": (headers.get("icy-genre") or "").strip(),
            "homepage": (headers.get("icy-url") or "").strip(), "codec": codec, "bitrate": bitrate}


# --- Radio Browser ---------------------------------------------------------------------------------------
def directory_servers():
    """Radio Browser's API servers, as its docs ask: every address behind all.api.radio-browser.info, by name."""
    if net.is_offline():
        raise net.OfflineError()
    names = []
    try:
        for *_, addr in socket.getaddrinfo("all.api.radio-browser.info", 443, proto=socket.IPPROTO_TCP):
            try:
                name = socket.gethostbyaddr(addr[0])[0]
            except OSError:
                continue
            if name.endswith(".radio-browser.info") and name not in names:
                names.append(name)
    except OSError:
        pass
    return names or list(FALLBACK_SERVERS)


def _station_from_directory(item):
    url = (item.get("url_resolved") or item.get("url") or "").strip()
    return {
        "name": (item.get("name") or "").strip(), "url": url, "homepage": (item.get("homepage") or "").strip(),
        "favicon": (item.get("favicon") or "").strip(), "tags": ", ".join(
            t.strip() for t in (item.get("tags") or "").split(",") if t.strip())[:200],
        "country": (item.get("country") or "").strip(), "codec": (item.get("codec") or "").strip(),
        "bitrate": int(item.get("bitrate") or 0), "uuid": (item.get("stationuuid") or "").strip(),
        "votes": int(item.get("votes") or 0),
    }


def search_directory(query, limit=60, servers=None, timeout=10):
    """Stations in Radio Browser whose name or tag matches `query`, most popular first."""
    params = {"name": query, "limit": str(limit), "hidebroken": "true", "order": "clickcount", "reverse": "true"}
    by_tag = {"tag": query, "limit": str(limit), "hidebroken": "true", "order": "clickcount", "reverse": "true"}
    last_error = None
    for server in servers or directory_servers():
        try:
            seen, results = set(), []
            for p in (params, by_tag):
                url = f"https://{server}/json/stations/search?" + urllib.parse.urlencode(p)
                with net.urlopen(_request(url), timeout=timeout, limit=8_000_000) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for item in data if isinstance(data, list) else []:
                    st = _station_from_directory(item)
                    if st["url"] and is_stream_url(st["url"]) and st["uuid"] not in seen:
                        seen.add(st["uuid"])
                        results.append(st)
            return results[:limit]
        except (OSError, ValueError) as exc:
            last_error = exc
    raise last_error or OSError("Radio Browser didn't answer")


def count_click(uuid, servers=None, timeout=5):
    """Tell Radio Browser a station was played: it's how its directory ranks what people listen to."""
    if not uuid:
        return
    for server in servers or directory_servers():
        try:
            with net.urlopen(_request(f"https://{server}/json/url/{urllib.parse.quote(uuid)}"),
                             timeout=timeout, limit=100_000) as resp:
                resp.read()
            return
        except OSError:
            continue
