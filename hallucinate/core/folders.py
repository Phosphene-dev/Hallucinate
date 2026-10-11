"""Folder view: the library as your folders on disk, one level at a time.

Only folders that hold library songs (directly or further down) are shown. Lookups use the index on
tracks.path with a range query, so a level of a big library is a single indexed scan."""
import os


def _range(directory):
    """Path bounds covering everything below `directory` (the character after the separator closes it)."""
    prefix = directory.rstrip("/\\") + os.sep
    return prefix, prefix[:-1] + chr(ord(os.sep) + 1)


def contents(db, directory, roots):
    """{"path", "name", "parent", "crumbs", "folders", "tracks"} for one folder, or the library roots for "".

    folders: [{"name", "path", "songs", "duration", "art"}] sorted by name; tracks: songs directly inside, in
    disc/track order. crumbs: [{"name", "path"}] from the library root down (empty for the roots)."""
    roots = sorted({os.path.normpath(r) for r in roots}, key=str.casefold)
    if not directory:
        folders = []
        for root in roots:
            lo, hi = _range(root)
            row = db.conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(duration), 0), MAX(art) FROM tracks WHERE path >= ? AND path < ?",
                (lo, hi),
            ).fetchone()
            folders.append({"name": os.path.basename(root) or root, "path": root, "songs": row[0],
                            "duration": float(row[1]), "art": row[2] or "", "root": True})
        return {"path": "", "name": "Folders", "parent": "", "crumbs": [], "folders": folders, "tracks": []}

    directory = os.path.normpath(directory)
    lo, hi = _range(directory)
    sub, direct = {}, []
    for path, duration, art in db.conn.execute(
        "SELECT path, duration, art FROM tracks WHERE path >= ? AND path < ?", (lo, hi)
    ):
        head, sep, _tail = path[len(lo):].partition(os.sep)
        if sep:
            f = sub.setdefault(head, {"name": head, "path": os.path.join(directory, head), "songs": 0,
                                      "duration": 0.0, "art": ""})
            f["songs"] += 1
            f["duration"] += duration or 0
            f["art"] = f["art"] or (art or "")
        else:
            direct.append(path)
    tracks = []
    for i in range(0, len(direct), 500):
        chunk = direct[i:i + 500]
        tracks += db._rows(f"SELECT * FROM tracks WHERE path IN ({','.join('?' * len(chunk))})", chunk)
    tracks.sort(key=lambda t: (t["disc_no"], t["track_no"], t["s_title"]))
    root = next((r for r in roots if directory == r or directory.startswith(r.rstrip(os.sep) + os.sep)), "")
    crumbs = []
    if root:
        crumbs.append({"name": os.path.basename(root) or root, "path": root})
        rel = os.path.relpath(directory, root)
        if rel != ".":
            path = root
            for part in rel.split(os.sep):
                path = os.path.join(path, part)
                crumbs.append({"name": part, "path": path})
    parent = "" if directory in roots or not root else os.path.dirname(directory)
    return {"path": directory, "name": os.path.basename(directory) or directory, "parent": parent,
            "crumbs": crumbs, "folders": sorted(sub.values(), key=lambda f: f["name"].casefold()), "tracks": tracks}


def tracks_below(db, directory):
    """Every song in `directory` and its subfolders, folder by folder, in disc/track order within each."""
    lo, hi = _range(os.path.normpath(directory))
    rows = db._rows("SELECT * FROM tracks WHERE path >= ? AND path < ?", (lo, hi))
    rows.sort(key=lambda t: (os.path.dirname(t["path"]).casefold(), t["disc_no"], t["track_no"], t["s_title"]))
    return rows
