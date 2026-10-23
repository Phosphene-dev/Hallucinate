"""CUE sheets: a whole album in one audio file, with a .cue that says where each song starts.

Each song becomes its own library entry with a virtual path, "<audio file>#<track number>", so likes, ratings,
history and playlists work as for any other song. The entry remembers the real file and where the song starts
and ends in it; the player plays that slice.

Only sheets that split a file into two or more songs matter here: a sheet with one FILE per song describes
files that are already separate."""
import os
import re

from . import genres, tags

FRAMES = 75  # CD frames per second, the unit of INDEX times


def _decode(data):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _arg(rest):
    """The value of a CUE command: a quoted string, or the first word."""
    rest = rest.strip()
    if rest.startswith('"'):
        end = rest.find('"', 1)
        return rest[1:end] if end > 0 else rest[1:]
    return rest.split()[0] if rest else ""


def _time(text):
    m = re.match(r"(\d+):(\d+):(\d+)", text.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / FRAMES


def _gain(text):
    m = re.match(r"\s*([-+]?\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def parse(text):
    """{"title", "performer", "songwriter", "genre", "date", "disc", "rg_album", "rg_album_peak",
    "files": [{"name", "tracks": [{"number", "title", "performer", "songwriter", "start", "rg_track", "rg_peak"}]}]}."""
    sheet = {"title": "", "performer": "", "songwriter": "", "genre": "", "date": "", "disc": 0, "rg_album": None,
             "rg_album_peak": None, "files": []}
    track = None
    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line:
            continue
        cmd, _, rest = line.partition(" ")
        cmd = cmd.upper()
        target = track if track is not None else sheet
        if cmd == "FILE":
            sheet["files"].append({"name": _arg(rest), "tracks": []})
            track = None
        elif cmd == "TRACK":
            parts = rest.split()
            if not sheet["files"] or len(parts) < 2 or parts[1].upper() != "AUDIO":
                track = {}  # a data track: collect and drop
                continue
            try:
                number = int(parts[0])
            except ValueError:
                number = len(sheet["files"][-1]["tracks"]) + 1
            track = {"number": number, "title": "", "performer": "", "songwriter": "", "start": None, "rg_track": None,
                     "rg_peak": None}
            sheet["files"][-1]["tracks"].append(track)
        elif cmd in ("TITLE", "PERFORMER", "SONGWRITER"):
            target[cmd.lower()] = _arg(rest)
        elif cmd == "INDEX" and track:
            parts = rest.split()
            if len(parts) >= 2 and parts[0] in ("01", "1"):
                track["start"] = _time(parts[1])
        elif cmd == "REM":
            key, _, value = rest.strip().partition(" ")
            key = key.upper()
            if key == "GENRE" and track is None:
                sheet["genre"] = genres.join(genres.split(_arg(value)))  # "Rock / Pop" as the library writes it
            elif key == "DATE" and track is None:
                sheet["date"] = _arg(value)
            elif key == "DISCNUMBER" and track is None:
                try:
                    sheet["disc"] = int(_arg(value).split("/")[0])
                except ValueError:
                    pass
            elif key == "REPLAYGAIN_ALBUM_GAIN":
                sheet["rg_album"] = _gain(value)
            elif key == "REPLAYGAIN_ALBUM_PEAK":
                sheet["rg_album_peak"] = _gain(value)
            elif key == "REPLAYGAIN_TRACK_GAIN" and track:
                track["rg_track"] = _gain(value)
            elif key == "REPLAYGAIN_TRACK_PEAK" and track:
                track["rg_peak"] = _gain(value)
    for f in sheet["files"]:
        f["tracks"] = [t for t in f["tracks"] if t.get("start") is not None]
    return sheet


def read(path):
    with open(path, "rb") as fh:
        return parse(_decode(fh.read()))


def resolve_file(name, cue_path, audio_files):
    """The audio file a FILE line means. Sheets often name the WAV a rip was made from although the album was
    then encoded to FLAC, so the same name with another audio extension counts too, and as a last resort the
    one audio file named like the sheet itself. `audio_files`: names of the audio files in the sheet's folder."""
    directory = os.path.dirname(cue_path)
    name = os.path.basename(name.replace("\\", "/"))
    by_lower = {a.lower(): a for a in audio_files}
    if name.lower() in by_lower:
        return os.path.join(directory, by_lower[name.lower()])
    stem = os.path.splitext(name)[0].lower()
    for a in audio_files:
        if os.path.splitext(a)[0].lower() == stem:
            return os.path.join(directory, a)
    cue_stem = os.path.splitext(os.path.basename(cue_path))[0].lower()
    same = [a for a in audio_files if os.path.splitext(a)[0].lower() == cue_stem]
    return os.path.join(directory, same[0]) if len(same) == 1 else None


def split_files(cue_path, audio_files):
    """{audio path: (sheet, file entry)} for each file the sheet splits into two or more songs."""
    try:
        sheet = read(cue_path)
    except OSError:
        return {}
    out = {}
    for f in sheet["files"]:
        if len(f["tracks"]) < 2:
            continue
        audio = resolve_file(f["name"], cue_path, audio_files)
        if audio and audio not in out:
            out[audio] = (sheet, f)
    return out


def virtual_path(audio, number):
    return f"{audio}#{number:02d}"


_VIRTUAL = re.compile(r"\.[A-Za-z0-9]+#\d+$")


def is_virtual(path):
    """Whether `path` names a CUE sheet song rather than a file of its own."""
    return bool(_VIRTUAL.search(path or "")) and not os.path.exists(path)


def tracks(audio_track, sheet, entry, cue_mtime=0.0):
    """Library rows for each song of `entry`, from the whole file's row (`tags.read_track`) and the sheet.

    The sheet's titles and performers win; the file's own tags fill in album, artist, year and genre when the
    sheet has none. mtime is the newer of the audio file's and the sheet's, so editing either rescans."""
    songs = sorted(entry["tracks"], key=lambda t: t["start"])
    total = audio_track.get("duration") or 0.0
    album = sheet["title"] or audio_track.get("album") or ""
    album_artist = sheet["performer"] or audio_track.get("album_artist") or audio_track.get("artist") or ""
    year = audio_track.get("year") or 0
    m = re.search(r"\d{4}", sheet["date"] or "")
    if m:
        year = int(m.group(0))
    rows = []
    for i, song in enumerate(songs):
        end = songs[i + 1]["start"] if i + 1 < len(songs) else 0.0
        length = (end or total) - song["start"]
        if length <= 0:
            continue
        artist = song["performer"] or album_artist
        row = dict(audio_track)
        row.pop("_art", None)
        row.update({
            "path": virtual_path(audio_track["path"], song["number"]),
            "file": audio_track["path"],
            "cue_start": round(song["start"], 4),
            "cue_end": round(end, 4),
            "mtime": max(audio_track.get("mtime") or 0, cue_mtime),
            "title": song["title"] or f"Track {song['number']}",
            "artist": artist,
            "album_artist": album_artist,
            "aa_tag": 1 if sheet["performer"] else audio_track.get("aa_tag", 0),
            "album": album,
            "album_key": tags.album_key(album_artist, album, os.path.dirname(audio_track["path"])),
            "track_no": song["number"],
            "disc_no": sheet["disc"] or audio_track.get("disc_no") or 0,
            "year": year,
            "genre": sheet["genre"] or audio_track.get("genre") or "",
            "duration": round(length, 3),
            "rating": 0,  # a rating in the file's tags is for the whole file
            "composer": song.get("songwriter") or sheet.get("songwriter") or audio_track.get("composer") or "",
            # the whole file's movement, tempo and key aren't any one song's
            "movement": "", "movement_no": 0, "bpm": 0, "music_key": "",
        })
        if song["rg_track"] is not None or sheet["rg_album"] is not None:
            row["rg_track"] = song["rg_track"] if song["rg_track"] is not None else sheet["rg_album"]
            row["rg_album"] = sheet["rg_album"] if sheet["rg_album"] is not None else row["rg_track"]
            row["rg_peak"] = song["rg_peak"] or sheet["rg_album_peak"]
        elif audio_track.get("rg_album") is not None:
            # the file's own gain describes the whole album, which is right for album gain and close for each song
            row["rg_track"] = row["rg_album"] = audio_track["rg_album"]
        rows.append(row)
    return rows
