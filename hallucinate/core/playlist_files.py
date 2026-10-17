"""Playlist files: read M3U / M3U8 / PLS, write M3U8.

Reading gives entries with the file path (resolved against the playlist's folder) and, when the file says so,
artist, title and length, so songs can still be found in the library after a move. Writing uses paths relative
to the playlist when the songs are below its folder (portable to phones and other players), absolute otherwise."""
import os
import re
from urllib.parse import unquote, urlparse

_EXTINF = re.compile(r"#EXTINF:\s*(-?\d+(?:\.\d+)?)\s*(?:[^,]*),(.*)")


def _resolve(location, base_dir):
    location = location.strip()
    if location.lower().startswith("file:"):
        parsed = urlparse(location)
        location = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:", location):  # file:///C:/...
            location = location[1:]
    elif re.match(r"^[a-z][a-z0-9+.-]*://", location, re.I):
        return None  # streams and web links aren't library songs
    windows_drive = re.match(r"^[A-Za-z]:[\\/]", location)
    if os.sep == "/" and not windows_drive:
        location = location.replace("\\", "/")  # relative paths written on Windows
    if not os.path.isabs(location) and not windows_drive:
        location = os.path.join(base_dir, location)
    return os.path.normpath(location)


def _split_artist_title(text):
    if " - " in text:
        artist, title = text.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", text.strip()


def parse_m3u(text, base_dir):
    """Entries [{"path", "artist", "title", "duration"}] from an M3U or M3U8 playlist."""
    out, pending = [], {}
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.startswith("#"):
            m = _EXTINF.match(line)
            if m:
                artist, title = _split_artist_title(m.group(2))
                pending = {"duration": max(0.0, float(m.group(1))), "artist": artist, "title": title}
            continue
        path = _resolve(line, base_dir)
        if path:
            out.append({"path": path, "artist": "", "title": "", "duration": 0.0, **pending})
        pending = {}
    return out


def parse_pls(text, base_dir):
    """Entries from a PLS playlist (File1=…, Title1=…, Length1=…)."""
    fields = {}
    for raw in text.splitlines():
        m = re.match(r"\s*(File|Title|Length)(\d+)\s*=\s*(.*)", raw, re.I)
        if m:
            fields.setdefault(int(m.group(2)), {})[m.group(1).lower()] = m.group(3).strip()
    out = []
    for n in sorted(fields):
        f = fields[n]
        path = _resolve(f.get("file", ""), base_dir) if f.get("file") else None
        if not path:
            continue
        artist, title = _split_artist_title(f.get("title", ""))
        try:
            duration = max(0.0, float(f.get("length", 0)))
        except ValueError:
            duration = 0.0
        out.append({"path": path, "artist": artist, "title": title, "duration": duration})
    return out


def read(path):
    """Entries from a playlist file, chosen by extension (.pls, otherwise M3U)."""
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")  # old .m3u files are often in the system code page
    base = os.path.dirname(os.path.abspath(path))
    return parse_pls(text, base) if path.lower().endswith(".pls") else parse_m3u(text, base)


def write_m3u(tracks, dest):
    """M3U8 text for `tracks` ({path, artist, title, duration}) saved at `dest`."""
    base = os.path.dirname(os.path.abspath(dest))
    lines = ["#EXTM3U"]
    for t in tracks:
        if "://" in t["path"]:
            continue  # a station or streamed episode in the queue isn't a file to list
        path = os.path.abspath(t["path"])
        try:
            rel = os.path.relpath(path, base)
        except ValueError:  # on another drive (Windows): only the full path works
            rel = path
        location = rel if not rel.startswith("..") and not os.path.isabs(rel) else path
        name = " - ".join(x for x in (t.get("artist") or "", t.get("title") or "") if x)
        lines.append(f"#EXTINF:{int(round(t.get('duration') or 0))},{name}")
        lines.append(location.replace(os.sep, "/") if location == rel else location)
    return "\n".join(lines) + "\n"
