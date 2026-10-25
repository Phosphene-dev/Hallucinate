"""`hallucinate tui`: Hallucinate in a terminal. A full-screen player for a running Hallucinate (the window or a
headless server), over the same private control socket as `hallucinate cmd`: what's playing with a progress
bar, and the queue, albums, artists, playlists, liked songs and search, with the keyboard.

Keys (also on screen, and ? for all of them):
  space play/pause   n next   p previous   ← → seek 10 s   + - volume   m mute
  s shuffle   r repeat   R radio mode   l like   1–6 views   / search   enter play or open
  a add to the queue   A play next   d remove from the queue   backspace back   q quit

The view logic (Browser) is separate from the drawing (Screen), so it can be tested without a terminal."""
import sys
import time
import unicodedata

from .cli import CommandError, call, clock, marks

VIEWS = [("queue", "Queue"), ("albums", "Albums"), ("artists", "Artists"), ("playlists", "Playlists"),
         ("liked", "Liked"), ("search", "Search")]
HELP = [
    ("space", "play / pause"), ("n / p", "next / previous song"), ("← / →", "back / forward 10 seconds"),
    ("+ / -", "volume up / down"), ("m", "mute"), ("s", "shuffle"), ("r", "repeat (off, all, one)"),
    ("R", "radio mode"), ("l", "like the playing song"), ("1–6", "queue, albums, artists, playlists, liked, search"),
    ("/", "search"), ("enter", "play the song, or open the album, artist or playlist"),
    ("a", "add to the queue"), ("A", "play next"), ("d", "remove from the queue"), ("u", "undo a queue change"),
    ("backspace", "back"), ("↑ ↓ PgUp PgDn Home End", "move"), ("q", "quit (Hallucinate keeps playing)"),
]


def width(text):
    """Columns `text` takes in a terminal (wide characters take two)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 0 if unicodedata.combining(c) else 1 for c in text)


def fit(text, cols):
    """`text` cut (with …) or padded to exactly `cols` columns."""
    text = "".join(c for c in str(text) if c.isprintable())  # no escape codes from a tag
    if width(text) <= cols:
        return text + " " * (cols - width(text))
    out, used = "", 0
    for c in text:
        w = width(c)
        if used + w > cols - 1:
            break
        out += c
        used += w
    return out + "…" + " " * (cols - used - 1)


class Row:
    """One line of a list, and what Enter, a and A do with it."""

    def __init__(self, text, right="", song_id=None, open_=None, queue_index=None, current=False):
        self.text, self.right, self.song_id, self.open, self.queue_index, self.current = (
            text, right, song_id, open_, queue_index, current)


class Browser:
    """What the screen shows and what the keys do, without curses. `api(method, **params)` runs a command."""

    def __init__(self, api=call):
        self.api = api
        self.view = "queue"
        self.title = "Queue"
        self.rows = []
        self.cursor = 0
        self.top = 0
        self.stack = []  # where Back goes: (view, title, rows, cursor)
        self.state = None
        self.message = ""
        self.message_at = 0.0
        self.query = ""
        self.searching = False
        self.help = False
        self._queue_seen = None
        self._loader = None

    # --- talking to Hallucinate --------------------------------------------------------------------------
    def say(self, text):
        self.message, self.message_at = text, time.monotonic()

    def do(self, method, **params):
        try:
            return self.api(method, **params)
        except CommandError as exc:
            self.say(str(exc))
            return None

    def poll(self):
        """The latest state; the queue view follows changes to the queue."""
        st = self.do("state")
        if st is None:
            return False
        self.state = st
        if self.view == "queue" and not self.stack:
            seen = (st["queueLength"], st["index"], (st.get("song") or {}).get("title"))
            if seen != self._queue_seen:
                self._queue_seen = seen
                self.load_queue(keep_cursor=True)
        return True

    # --- views ---------------------------------------------------------------------------------------------
    def show(self, view):
        self.stack.clear()
        self.view = view
        self.title = dict(VIEWS)[view]
        self.cursor = self.top = 0
        if view == "queue":
            self.load_queue(follow=True)
        elif view == "albums":
            r = self.do("albums", limit=500, sort="artist")
            self.rows = [Row(f"{a['title']} — {a['artist']}", str(a["year"] or ""), open_=("album", a["key"]))
                         for a in (r or {}).get("albums", [])]
        elif view == "artists":
            r = self.do("artists", limit=500)
            self.rows = [Row(a["name"], f"{a['albums']} albums", open_=("artist", a["name"]))
                         for a in (r or {}).get("artists", [])]
        elif view == "playlists":
            r = self.do("playlists")
            self.rows = [Row(p["name"], "smart" if p["smart"] else f"{p['songs']} songs",
                             open_=("playlist", (p["id"], p["smart"], p["name"])))
                         for p in (r or {}).get("playlists", [])]
        elif view == "liked":
            r = self.do("liked", limit=500)
            self.rows = self.song_rows((r or {}).get("songs", []))
            self._loader = ("liked", {})
        elif view == "search":
            self.rows = []
            self.searching = True

    def song_rows(self, songs):
        return [Row(f"{s['title']}{marks(s)} — {s['artist']}", clock(s["duration"], ms=False) if s.get("duration") else "",
                    song_id=s["id"]) for s in songs]

    def load_queue(self, keep_cursor=False, follow=False):
        r = self.do("queue")
        if r is None:
            return
        self.rows = [Row(f"{s['title']}{marks(s)} — {s['artist']}" if s["artist"] else s["title"] + marks(s),
                         clock(s["duration"], ms=False) if s["duration"] else "", song_id=s["id"], queue_index=i,
                         current=i == r["index"]) for i, s in enumerate(r["songs"])]
        if follow and r["index"] >= 0:
            self.cursor = min(r["index"], max(0, len(self.rows) - 1))
        elif not keep_cursor:
            self.cursor = 0
        self.cursor = min(self.cursor, max(0, len(self.rows) - 1))

    def open(self, row):
        kind, what = row.open
        self.stack.append((self.view, self.title, self.rows, self.cursor))
        if kind == "album":
            r = self.do("album", key=what)
            if r is None:
                return self.back()
            self.title = f"{r['title']} — {r['artist']}"
            self.rows = self.song_rows(r["songs"])
            self._loader = ("album", {"key": what})
        elif kind == "artist":
            r = self.do("artist", name=what)
            if r is None:
                return self.back()
            self.title = r["name"]
            self.rows = ([Row(f"{a['title']}", str(a["year"] or ""), open_=("album", a["key"])) for a in r["albums"]]
                         + self.song_rows(r["songs"]))
            self._loader = ("artist", {"name": what})
        elif kind == "playlist":
            pid, smart, name = what
            r = self.do("playlist", id=pid, smart=smart)
            if r is None:
                return self.back()
            self.title = name
            self.rows = self.song_rows(r["songs"])
            self._loader = ("playlist", {"id": pid, "smart": smart})
        self.view = kind
        self.cursor = self.top = 0

    def back(self):
        if self.stack:
            self.view, self.title, self.rows, self.cursor = self.stack.pop()
            self.top = 0
        return None

    def search(self, query):
        self.query = query
        r = self.do("search", query=query, limit=100)
        if r is None:
            return
        self.rows = ([Row(a["name"], "artist", open_=("artist", a["name"])) for a in r["artists"][:5]]
                     + [Row(f"{a['title']} — {a['artist']}", "album", open_=("album", a["key"])) for a in r["albums"][:10]]
                     + self.song_rows(r["songs"]))
        self.title = f"Search: {query}" + (f"  (showing \"{r['corrected']}\")" if r.get("corrected") else "")
        self.cursor = self.top = 0
        if not self.rows:
            self.say("Nothing found")

    def play_row(self):
        """Enter: play from here (the list's songs, in order), jump in the queue, or open."""
        if not self.rows:
            return
        row = self.rows[self.cursor]
        if row.open:
            return self.open(row)
        if row.queue_index is not None:
            self.do("queue.jump", index=row.queue_index)
            return
        if self._loader and self._loader[0] == "album" and self.view == "album":
            self.do("play.album", key=self._loader[1]["key"], index=self.cursor)
        elif self._loader and self._loader[0] == "playlist" and self.view == "playlist":
            self.do("play.playlist", index=self.cursor, **self._loader[1])
        else:
            songs = [r.song_id for r in self.rows if r.song_id]
            start = sum(1 for r in self.rows[:self.cursor] if r.song_id)
            self.do("play.songs", ids=songs, index=start)

    # --- keys ----------------------------------------------------------------------------------------------
    def key(self, k, page=10):
        """Handle one key (curses' name for it: "KEY_UP", " ", "q"…). Returns False to quit."""
        if self.help:
            self.help = False
            return True
        if k in ("q", "Q"):
            return False
        moves = {"KEY_UP": -1, "k": -1, "KEY_DOWN": 1, "j": 1, "KEY_PPAGE": -page, "KEY_NPAGE": page}
        if k in moves:
            self.cursor = max(0, min(len(self.rows) - 1, self.cursor + moves[k]))
        elif k == "KEY_HOME":
            self.cursor = 0
        elif k == "KEY_END":
            self.cursor = max(0, len(self.rows) - 1)
        elif k in (" ",):
            self.do("toggle")
        elif k == "n":
            self.do("next")
        elif k == "p":
            self.do("previous")
        elif k in ("KEY_LEFT", "KEY_RIGHT"):
            st = self.state or {}
            pos = max(0, st.get("position", 0) + (10000 if k == "KEY_RIGHT" else -10000))
            self.do("seek", position=pos)
        elif k in ("+", "="):
            self.do("volume", change=0.05)
        elif k in ("-", "_"):
            self.do("volume", change=-0.05)
        elif k == "m":
            self.do("mute")
        elif k == "s":
            r = self.do("shuffle")
            if r:
                self.say(f"Shuffle {'on' if r['shuffle'] else 'off'}")
        elif k == "r":
            r = self.do("repeat")
            if r:
                self.say("Repeat " + ["off", "all", "one"][r["repeat"]])
        elif k == "R":
            r = self.do("radio")
            if r:
                self.say(f"Radio mode {'on' if r['radio'] else 'off'}")
        elif k == "l":
            song = (self.state or {}).get("song") or {}
            if song.get("id"):
                r = self.do("like", id=song["id"])
                if r:
                    self.say("♥ Liked" if r["liked"] else "Not liked")
        elif k in "123456" and len(k) == 1:
            self.show(VIEWS[int(k) - 1][0])
        elif k == "/":
            self.show("search")
        elif k in ("\n", "KEY_ENTER", "\r"):
            self.play_row()
        elif k in ("a", "A") and self.rows:
            row = self.rows[self.cursor]
            if row.song_id:
                if self.do("queue.add", ids=[row.song_id], next=k == "A"):
                    self.say("Playing next" if k == "A" else "Added to the queue")
        elif k == "d" and self.rows and self.rows[self.cursor].queue_index is not None:
            if self.do("queue.remove", index=self.rows[self.cursor].queue_index) is not None:
                self.load_queue(keep_cursor=True)
        elif k == "u":
            r = self.do("queue.undo")
            if r is not None:
                self.say("Undone" if r.get("undone") else "Nothing to undo")
        elif k in ("KEY_BACKSPACE", "\x7f", "\b", "h"):
            self.back()
        elif k == "?":
            self.help = True
        return True


class Screen:
    """Draws a Browser with curses and feeds it keys."""

    def __init__(self, scr, browser):
        import curses

        self.curses = curses
        self.scr = scr
        self.b = browser
        curses.curs_set(0)
        scr.timeout(250)
        scr.keypad(True)
        self.color = curses.has_colors()
        if self.color:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_MAGENTA, -1)  # accent
            curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_MAGENTA)  # the cursor
            curses.init_pair(3, curses.COLOR_CYAN, -1)  # the playing song

    def attr(self, n, extra=0):
        return (self.curses.color_pair(n) if self.color else 0) | extra

    def put(self, y, x, text, attr=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and x < w:
            try:
                self.scr.addstr(y, x, fit(text, w - x - (1 if y == h - 1 else 0)), attr)
            except self.curses.error:
                pass

    def draw(self):
        c = self.curses
        scr, b = self.scr, self.b
        scr.erase()
        h, w = scr.getmaxyx()
        st = b.state or {}
        song = st.get("song") or {}
        # what's playing
        if song:
            title = song.get("streamTitle") or ((song.get("title") or "Unknown") + marks(song))
            self.put(0, 0, ("▶ " if st.get("playing") else "⏸ ") + title, self.attr(1, c.A_BOLD))
            self.put(1, 2, " · ".join(x for x in (song.get("artist"), song.get("album"), str(song.get("year") or "")) if x))
            pos, dur = st.get("position", 0), st.get("duration", 0)
            times = f" {clock(pos)} / {clock(dur)} "
            bar_w = max(10, w - len(times) - 4)
            done = int(bar_w * pos / dur) if dur else 0
            self.put(2, 2, "━" * done + "─" * (bar_w - done) + times)
        else:
            self.put(0, 0, "Nothing playing", self.attr(1, c.A_BOLD))
        flags = [f"vol {round(st.get('volume', 0) * 100)}%" + (" muted" if st.get("muted") else "")]
        flags += [n for n, on in (("shuffle", st.get("shuffle")), ("radio", st.get("radio"))) if on]
        if st.get("repeat"):
            flags.append("repeat " + ("one" if st["repeat"] == 2 else "all"))
        if song.get("liked"):
            flags.append("♥")
        self.put(3, 2, "  ".join(flags), c.A_DIM)
        # the views
        x = 0
        for i, (view, name) in enumerate(VIEWS):
            label = f" {i + 1} {name} "
            on = b.view == view or (b.stack and b.stack[0][0] == view)
            self.put(4, x, label, self.attr(2) if on else c.A_DIM)
            x += len(label) + 1
        self.put(5, 0, b.title, c.A_BOLD)
        # the list
        list_top, list_h = 6, max(1, h - 8)
        if b.cursor < b.top:
            b.top = b.cursor
        elif b.cursor >= b.top + list_h:
            b.top = b.cursor - list_h + 1
        for i, row in enumerate(b.rows[b.top:b.top + list_h]):
            n = b.top + i
            right = f" {row.right}" if row.right else ""
            text = fit(("▶ " if row.current else "  ") + row.text, max(1, w - len(right) - 1)) + right
            attr = self.attr(2) if n == b.cursor else self.attr(3, c.A_BOLD) if row.current else 0
            self.put(list_top + i, 0, text, attr)
        if not b.rows and not b.searching:
            self.put(list_top, 2, "Nothing here", c.A_DIM)
        # the bottom line
        if b.message and time.monotonic() - b.message_at < 4:
            self.put(h - 1, 0, b.message, self.attr(1))
        else:
            hint = ("space play/pause · n/p next/prev · ←→ seek · +/- volume · / search · enter play · ? help · q quit"
                    if w >= 100 else "space play/pause · n/p next/prev · / search · ? help · q quit")
            self.put(h - 1, 0, hint, c.A_DIM)
        if b.help:
            self.draw_help()
        scr.refresh()

    def draw_help(self):
        h, w = self.scr.getmaxyx()
        width_ = min(w - 2, 78)
        top = max(0, (h - len(HELP) - 4) // 2)
        left = max(0, (w - width_) // 2)
        self.put(top, left, fit(" Keys", width_), self.attr(2))
        for i, (k, what) in enumerate(HELP):
            self.put(top + 1 + i, left, fit(f" {k:<24}{what}", width_), self.attr(2))
        self.put(top + 1 + len(HELP), left, fit(" Any key closes this", width_), self.attr(2, self.curses.A_DIM))

    def ask(self, prompt):
        """A line of text typed at the bottom (Enter keeps it, Esc gives up)."""
        c = self.curses
        h, w = self.scr.getmaxyx()
        text = ""
        c.curs_set(1)
        self.scr.timeout(-1)
        try:
            while True:
                self.put(h - 1, 0, prompt + text, self.attr(1))
                self.scr.move(h - 1, min(w - 1, width(prompt + text)))
                ch = self.scr.get_wch()
                if ch in ("\n", "\r", c.KEY_ENTER):
                    return text.strip()
                if ch == "\x1b":
                    return ""
                if ch in (c.KEY_BACKSPACE, "\x7f", "\b"):
                    text = text[:-1]
                elif isinstance(ch, str) and ch.isprintable():
                    text += ch
        finally:
            c.curs_set(0)
            self.scr.timeout(250)

    def loop(self):
        b = self.b
        b.poll()
        b.show("queue")
        last_poll = time.monotonic()
        while True:
            if time.monotonic() - last_poll >= 0.5:
                b.poll()
                last_poll = time.monotonic()
            elif b.state and b.state.get("playing"):
                b.state["position"] = min(b.state["position"] + 250, b.state.get("duration") or 0)
            self.draw()
            try:
                ch = self.scr.get_wch()
            except self.curses.error:
                continue  # no key within the timeout
            name = self.curses.keyname(ch).decode() if isinstance(ch, int) else ch
            if name == "KEY_RESIZE":
                continue
            if not b.key(name, page=max(1, self.scr.getmaxyx()[0] - 9)):
                return
            if b.searching:  # the search view was chosen: ask for words straight away
                b.searching = False
                self.draw()
                query = self.ask("Search: ")
                if query:
                    b.search(query)
                elif not b.rows:
                    b.show("queue")


def main(argv):
    import argparse

    argparse.ArgumentParser(prog="hallucinate tui", description="Hallucinate in a terminal: a full-screen player "
                            "for a running Hallucinate (the app or `hallucinate --headless`).").parse_args(argv)
    try:
        import curses
    except ImportError:
        print("The terminal version needs curses, which this Python doesn't have (on Windows: pip install "
              "windows-curses). `hallucinate cmd` and the web interface work here.", file=sys.stderr)
        return 1
    try:
        call("state")
    except CommandError as exc:
        print(exc, file=sys.stderr)
        return 1
    import locale

    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(lambda scr: Screen(scr, Browser()).loop())
    return 0
