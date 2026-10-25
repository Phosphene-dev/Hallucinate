"""`hallucinate cmd …`: control a running Hallucinate from a terminal or a script, the window or the headless
server alike. It talks to the running app over its private control socket (control.py) and has the same
commands as the web remote (api.py): what's playing, playback, the queue, searching and playing the library,
likes and ratings, and the web remote's own settings and pairing.

Output is plain text for people, or JSON with --json for scripts. Exit status: 0 done, 1 Hallucinate isn't
running or the command failed, 2 the command was mistyped."""
import argparse
import json
import sys

from .control import send_control

NOT_RUNNING = ("Hallucinate isn't running. Start it first (on a server without a screen: "
               "hallucinate --headless).")


class CommandError(Exception):
    """A command that couldn't be done; its message is shown."""


def request(command, response_ms=15000, **payload):
    response = send_control(command, timeout_ms=1000, response_ms=response_ms, **payload)
    if response is None:
        raise CommandError(NOT_RUNNING)
    if not response.get("ok"):
        raise CommandError(response.get("error") or "That didn't work")
    return response


def call(method, **params):
    """One of the API's commands on the running app; its result."""
    return request("api", method=method, params=params)["result"]


# --- formatting ---------------------------------------------------------------------------------------------
def clock(ms_or_s, ms=True):
    s = max(0, int((ms_or_s or 0) / 1000 if ms else ms_or_s or 0))
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time(text):
    """Milliseconds from "83", "1:23" or "1:02:03"."""
    try:
        parts = [float(p) for p in text.split(":")]
    except ValueError:
        raise CommandError(f"'{text}' isn't a time (try 90, 1:30 or +10)") from None
    if not 1 <= len(parts) <= 3 or any(p < 0 for p in parts):
        raise CommandError(f"'{text}' isn't a time (try 90, 1:30 or +10)")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + p
    return int(seconds * 1000)


def song_line(s, with_id=True):
    bits = [s.get("title") or "Unknown", s.get("artist") or ""]
    text = " — ".join(b for b in bits if b)
    if s.get("album"):
        text += f"  ({s['album']})"
    if s.get("duration"):
        text += f"  {clock(s['duration'], ms=False)}"
    return f"[{s['id']}] {text}" if with_id and s.get("id") else text


def describe_state(st):
    if not st.get("song"):
        return "Nothing playing"
    song = st["song"]
    title = song.get("streamTitle") or song.get("title") or "Unknown"
    lines = [f"{'▶ Playing' if st['playing'] else '⏸ Paused'}: {title}"]
    who = " · ".join(b for b in (song.get("artist"), song.get("album"), str(song.get("year") or "")) if b)
    if who:
        lines.append("  " + who)
    lines.append(f"  {clock(st['position'])} / {clock(st['duration'])}"
                 f"  ·  song {st['index'] + 1} of {st['queueLength']}")
    extras = [f"volume {round(st['volume'] * 100)}%" + (" (muted)" if st.get("muted") else "")]
    if st.get("shuffle"):
        extras.append("shuffle")
    if st.get("repeat"):
        extras.append("repeat " + ("one" if st["repeat"] == 2 else "all"))
    if st.get("radio"):
        extras.append("radio mode")
    if st.get("sleepRemaining", -1) >= 0:
        extras.append(f"sleep in {clock(st['sleepRemaining'])}")
    elif st.get("sleepAfterTrack"):
        extras.append("sleep after this song")
    elif st.get("sleepAfterAlbum"):
        extras.append("sleep after this album")
    if song.get("liked"):
        extras.append("♥ liked")
    if song.get("rating"):
        extras.append("★" * int(song["rating"]))
    lines.append("  " + " · ".join(extras))
    if st.get("error"):
        lines.append("  ! " + st["error"])
    return "\n".join(lines)


# --- commands -------------------------------------------------------------------------------------------------
def _on_off(value):
    return None if value is None else value == "on"


def _current_song_id():
    st = call("state")
    song = st.get("song") or {}
    if not song.get("id"):
        raise CommandError("Nothing from your library is playing; give a song id (see `hallucinate cmd search`)")
    return song["id"]


def _album_key(name):
    """An album's key from its name (or its key itself)."""
    found = call("search", query=name, limit=5)["albums"]
    if not found:
        raise CommandError(f"No album matches '{name}'")
    exact = [a for a in found if a["title"].casefold() == name.casefold()]
    return (exact or found)[0]["key"]


def _playlist(name):
    lists = call("playlists")["playlists"]
    for want in (lambda p: str(p["id"]) == name, lambda p: p["name"].casefold() == name.casefold(),
                 lambda p: name.casefold() in p["name"].casefold()):
        hit = [p for p in lists if want(p)]
        if hit:
            return hit[0]
    raise CommandError(f"No playlist called '{name}' (see `hallucinate cmd playlists`)")


def playing():
    """What's now playing, in words (after a play command)."""
    st = call("state")
    song = st.get("song") or {}
    if not song:
        return "Nothing to play"
    what = " — ".join(x for x in (song.get("title"), song.get("artist")) if x)
    return f"Playing {what}" + (f" (song {st['index'] + 1} of {st['queueLength']})" if st["queueLength"] > 1 else "")


def run(args):
    """Do the command; returns (result for --json, text for people)."""
    c = args.command
    if c == "status":
        st = call("state")
        return st, describe_state(st)
    if c in ("play", "pause", "toggle", "next"):
        call(c)
        return {"ok": True}, ""
    if c in ("prev", "previous"):
        call("previous")
        return {"ok": True}, ""
    if c == "stop":
        call("pause")
        call("seek", position=0)
        return {"ok": True}, ""
    if c == "seek":
        text = args.time
        if text[:1] in "+-":
            st = call("state")
            delta = parse_time(text[1:]) * (1 if text[0] == "+" else -1)
            pos = max(0, st["position"] + delta)
        else:
            pos = parse_time(text)
            st = call("state")
        if st.get("duration"):
            pos = min(pos, st["duration"])
        call("seek", position=pos)
        return {"position": pos}, f"At {clock(pos)}"
    if c == "volume":
        if args.level is None:
            r = call("volume")
        elif args.level[:1] in "+-":
            r = call("volume", change=_number(args.level) / 100)
        else:
            r = call("volume", volume=_number(args.level) / 100)
        return r, f"Volume {round(r['volume'] * 100)}%"
    if c == "mute":
        call("mute")
        st = call("state")
        return {"muted": st["muted"]}, "Muted" if st["muted"] else "Unmuted"
    if c == "shuffle":
        r = call("shuffle", **({} if args.state is None else {"on": _on_off(args.state)}))
        return r, f"Shuffle {'on' if r['shuffle'] else 'off'}"
    if c == "repeat":
        modes = {"off": 0, "all": 1, "one": 2}
        r = call("repeat", **({} if args.mode is None else {"mode": modes[args.mode]}))
        return r, "Repeat " + ["off", "all", "one"][r["repeat"]]
    if c == "radio":
        r = call("radio", **({} if args.state is None else {"on": _on_off(args.state)}))
        return r, f"Radio mode {'on' if r['radio'] else 'off'}"
    if c == "sleep":
        when = args.when
        if when in ("track", "song"):
            call("sleep", end="track")
            return {"ok": True}, "Stopping after this song"
        if when == "album":
            call("sleep", end="album")
            return {"ok": True}, "Stopping after this album"
        minutes = 0 if when == "off" else int(_number(when))
        call("sleep", minutes=minutes)
        return {"minutes": minutes}, f"Stopping in {minutes} minutes" if minutes else "Sleep timer off"
    if c == "queue":
        return _queue(args)
    if c == "search":
        r = call("search", query=" ".join(args.query), limit=args.limit)
        out = []
        if r.get("corrected"):
            out.append(f"(nothing for that; showing \"{r['corrected']}\")")
        if r["artists"]:
            out.append("Artists:")
            out += [f"  {a['name']}  ({a['albums']} albums)" for a in r["artists"][:10]]
        if r["albums"]:
            out.append("Albums:")
            out += [f"  {a['title']} — {a['artist']}" + (f" ({a['year']})" if a["year"] else "") for a in r["albums"][:10]]
        if r["songs"]:
            out.append("Songs:")
            out += ["  " + song_line(s) for s in r["songs"]]
        return r, "\n".join(out) or "Nothing found"
    if c == "play-album":
        key = _album_key(" ".join(args.name))
        call("play.album", key=key, shuffle=args.shuffle)
        return {"ok": True, "key": key}, playing()
    if c in ("play-artist", "play-genre", "play-composer"):
        call("play." + c.split("-")[1], name=" ".join(args.name), shuffle=args.shuffle)
        return {"ok": True}, playing()
    if c == "play-playlist":
        p = _playlist(" ".join(args.name))
        call("play.playlist", id=p["id"], smart=p["smart"], shuffle=args.shuffle)
        return {"ok": True, "playlist": p}, playing()
    if c == "play-liked":
        call("play.liked", shuffle=args.shuffle)
        return {"ok": True}, playing()
    if c == "play-songs":
        call("play.songs", ids=args.ids)
        return {"ok": True}, playing()
    if c == "add":
        r = call("queue.add", ids=args.ids, next=args.next)
        return r, f"Added {r['added']} song{'s' if r['added'] != 1 else ''}" + (" to play next" if args.next else "")
    if c in ("like", "unlike"):
        sid = args.id or _current_song_id()
        r = call("like", id=sid, liked=c == "like")
        return r, "Liked" if r["liked"] else "Not liked"
    if c == "rate":
        sid = args.id or _current_song_id()
        call("rate", id=sid, stars=args.stars)
        return {"ok": True}, f"Rated {args.stars} star{'s' if args.stars != 1 else ''}" if args.stars else "Rating cleared"
    if c == "albums":
        r = call("albums", offset=args.offset, limit=args.limit, sort=args.sort)
        return r, "\n".join(f"{a['title']} — {a['artist']}" + (f" ({a['year']})" if a["year"] else "")
                            for a in r["albums"]) or "No albums"
    if c == "album":
        r = call("album", key=_album_key(" ".join(args.name)))
        head = f"{r['title']} — {r['artist']}" + (f" ({r['year']})" if r["year"] else "")
        return r, "\n".join([head] + [f"  {s['trackNo'] or i + 1:>2}. {song_line(s)}" for i, s in enumerate(r["songs"])])
    if c == "artists":
        r = call("artists", offset=args.offset, limit=args.limit)
        return r, "\n".join(f"{a['name']}  ({a['albums']} albums, {a['songs']} songs)" for a in r["artists"]) or "No artists"
    if c == "genres":
        r = call("genres")
        return r, "\n".join(f"{g['name']}  ({g['songs']} songs)" for g in r["genres"]) or "No genres"
    if c == "playlists":
        r = call("playlists")
        return r, "\n".join(f"[{p['id']}] {p['name']}" + (" (smart)" if p["smart"] else f"  ({p['songs']} songs)")
                            for p in r["playlists"]) or "No playlists"
    if c == "liked":
        r = call("liked", limit=args.limit)
        return r, "\n".join(song_line(s) for s in r["songs"]) or "No liked songs"
    if c == "rescan":
        call("library.rescan")
        return {"ok": True}, "Looking through your music folders again"
    if c == "library":
        r = call("library.info")
        return r, f"{r['songs']} songs on {r['albums']} albums" + (" (scanning…)" if r["scanning"] else "")
    if c == "remote":
        return _remote(args)
    if c == "pair":
        return _pair()
    raise CommandError(f"Unknown command {c}")


def _number(text):
    try:
        return float(text)
    except ValueError:
        raise CommandError(f"'{text}' isn't a number") from None


def _queue(args):
    action = args.action
    if action in (None, "show", "list"):
        r = call("queue")
        lines = []
        for i, s in enumerate(r["songs"]):
            mark = "▶" if i == r["index"] else " "
            lines.append(f"{mark} {i + 1:>3}. {song_line(s, with_id=False)}")
        if r["total"] > len(r["songs"]):
            lines.append(f"  … and {r['total'] - len(r['songs'])} more")
        return r, "\n".join(lines) or "The queue is empty"
    nums = [int(_number(n)) - 1 for n in args.numbers]  # people count from 1
    if action == "jump":
        call("queue.jump", index=_one(nums))
        return {"ok": True}, playing()
    elif action == "remove":
        for n in sorted(nums, reverse=True) or [_one(nums)]:
            call("queue.remove", index=n)
    elif action == "move":
        if len(nums) != 2:
            raise CommandError("Say where from and where to: queue move 7 2")
        call("queue.move", src=nums[0], dst=nums[1])
    elif action == "clear":
        call("queue.clear", upcoming=args.upcoming)
    elif action == "shuffle":
        call("queue.shuffle")
    elif action == "undo":
        return call("queue.undo"), ""
    else:
        raise CommandError(f"Unknown queue action {action}")
    return {"ok": True}, ""


def _one(nums):
    if len(nums) != 1:
        raise CommandError("Give one place in the queue (as `hallucinate cmd queue` numbers them)")
    return nums[0]


def _remote(args):
    payload = {}
    if args.state in ("on", "off"):
        payload["on"] = args.state == "on"
    if args.network is not None:
        payload["lan"] = args.network
    if args.port is not None:
        payload["port"] = args.port
    if args.host_name is not None:
        payload["hostNames"] = [n for n in args.host_name.split(",") if n.strip()]
    if args.state == "forget":
        payload["forget"] = args.device or ""
        if not payload["forget"]:
            raise CommandError("Say which device (its id, from `hallucinate cmd remote`) or `all`")
    r = request("remote", **payload)["remote"]
    lines = [f"Web remote: {'on' if r['on'] else 'off'}"
             + (f", {'your network' if r['lan'] else 'this computer only'}, port {r['port']}" if r["on"] else "")]
    if r.get("problem"):
        lines.append("  ! " + r["problem"])
    lines += [f"  {link}" for link in r["links"]]
    if r.get("hostNames"):
        lines.append("Also answers to: " + ", ".join(r["hostNames"]))
    if r["devices"]:
        lines.append("Paired devices:")
        lines += [f"  {d['id']}  {d['name']}" for d in r["devices"]]
    elif r["on"]:
        lines.append("No devices paired yet: hallucinate --pair")
    return r, "\n".join(lines)


def _pair():
    r = request("pair")
    links = r.get("links") or []
    text = [f"Pairing code: {r['code']}  (works once, for {r['minutes']} minutes)"]
    if links:
        text.append("Open one of these on your phone or another computer and enter it:")
        text += [f"  {link}" for link in links]
    return r, "\n".join(text)


def parser():
    ap = argparse.ArgumentParser(prog="hallucinate cmd", description="Control a running Hallucinate.",
                                 epilog="Add --json for output a script can read.")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    sub = ap.add_subparsers(dest="command", metavar="command", required=True)
    sub.add_parser("status", help="what's playing")
    for name, help_ in (("play", "play"), ("pause", "pause"), ("toggle", "play or pause"), ("stop", "pause and go to the start"),
                        ("next", "the next song"), ("prev", "the previous song")):
        sub.add_parser(name, help=help_)
    p = sub.add_parser("seek", help="go to a time in the song: 1:30, 90, +10 or -10")
    p.add_argument("time")
    p = sub.add_parser("volume", help="show or set the volume: 50, +5 or -5")
    p.add_argument("level", nargs="?")
    sub.add_parser("mute", help="mute or unmute")
    p = sub.add_parser("shuffle", help="shuffle on or off (or switch it)")
    p.add_argument("state", nargs="?", choices=["on", "off"])
    p = sub.add_parser("repeat", help="repeat off, all or one (or the next of them)")
    p.add_argument("mode", nargs="?", choices=["off", "all", "one"])
    p = sub.add_parser("radio", help="radio mode on or off (or switch it)")
    p.add_argument("state", nargs="?", choices=["on", "off"])
    p = sub.add_parser("sleep", help="stop after MINUTES, after this song (track) or album, or off")
    p.add_argument("when")
    p = sub.add_parser("queue", help="show the queue, or: jump N, remove N…, move FROM TO, clear, shuffle, undo")
    p.add_argument("action", nargs="?", choices=["show", "list", "jump", "remove", "move", "clear", "shuffle", "undo"])
    p.add_argument("numbers", nargs="*")
    p.add_argument("--upcoming", action="store_true", help="clear: only what's coming up")
    p = sub.add_parser("search", help="search the library (songs show their id)")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=20)
    for what in ("album", "artist", "genre", "composer", "playlist"):
        p = sub.add_parser(f"play-{what}", help=f"play a{'n' if what[0] in 'aeiou' else ''} {what} by name")
        p.add_argument("name", nargs="+")
        p.add_argument("--shuffle", action="store_true")
    p = sub.add_parser("play-liked", help="play your liked songs")
    p.add_argument("--shuffle", action="store_true")
    p = sub.add_parser("play-songs", help="play songs by id")
    p.add_argument("ids", nargs="+", type=int)
    p = sub.add_parser("add", help="add songs (by id) to the queue")
    p.add_argument("ids", nargs="+", type=int)
    p.add_argument("--next", action="store_true", help="right after the playing song")
    for name in ("like", "unlike"):
        p = sub.add_parser(name, help=f"{name} a song (the playing one unless you give an id)")
        p.add_argument("id", nargs="?", type=int)
    p = sub.add_parser("rate", help="rate a song 0–5 stars (the playing one unless you give an id)")
    p.add_argument("stars", type=int, choices=range(6))
    p.add_argument("id", nargs="?", type=int)
    p = sub.add_parser("albums", help="list albums")
    p.add_argument("--sort", choices=["title", "artist", "year", "added"], default="title")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=100)
    p = sub.add_parser("album", help="an album's songs")
    p.add_argument("name", nargs="+")
    p = sub.add_parser("artists", help="list artists")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=200)
    sub.add_parser("genres", help="list genres")
    sub.add_parser("playlists", help="list playlists")
    p = sub.add_parser("liked", help="list liked songs")
    p.add_argument("--limit", type=int, default=200)
    sub.add_parser("library", help="how many songs and albums there are")
    sub.add_parser("rescan", help="look through the music folders again")
    p = sub.add_parser("remote", help="the web remote: on, off, or forget DEVICE|all; --network / --local, --port")
    p.add_argument("state", nargs="?", choices=["on", "off", "forget"])
    p.add_argument("device", nargs="?")
    net = p.add_mutually_exclusive_group()
    net.add_argument("--network", dest="network", action="store_const", const=True,
                     help="let other devices on your network reach it")
    net.add_argument("--local", dest="network", action="store_const", const=False, help="this computer only")
    p.add_argument("--port", type=int)
    p.add_argument("--host-name", metavar="NAMES",
                   help="other names it answers to, comma-separated (a reverse proxy, music.example.lan); \"\" for none")
    sub.add_parser("pair", help="a code to pair a phone or browser with the web remote")
    return ap


def main(argv):
    args = parser().parse_args(argv)
    try:
        result, text = run(args)
    except CommandError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    elif text:
        print(text)
    return 0
