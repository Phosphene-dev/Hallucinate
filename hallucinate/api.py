"""The commands the web interface, the phone remote, the terminal version and the command line share: what's
playing, the queue, searching and browsing the library, and controlling playback.

Everything runs on the window's thread (the player and library live there); `call` is the one way in. What it
hands out is plain JSON. Songs are named by their library id, never by their path: a remote has no business
knowing where your files are or what your user name is, and can only ever ask for songs the library holds.

Each method has a scope: "read" (look) or "control" (play, queue, like, rate, playlists). Nothing here edits
tags, deletes or moves files, or changes settings: those stay in the app itself."""
import inspect
import logging
import math

from .core import composers as composer_views
from .core import genre_views
from .core import rules as smart_rules
from .core.db import fold

logger = logging.getLogger(__name__)
MAX_LIST = 500  # the most rows one answer carries (pages beyond with offset)
MAX_IDS = 2000  # the most songs one command acts on


class ApiError(Exception):
    """A request that can't be done; its message is shown to whoever asked."""


def _int(value, default=0, low=None, high=None):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if low is not None:
        v = max(low, v)
    if high is not None:
        v = min(high, v)
    return v


def _str(value, limit=500):
    return str(value or "")[:limit]


class Api:
    """The commands, bound to the running services. `call(name, params)` returns a JSON-safe value or raises
    ApiError; `methods` lists each command's scope."""

    def __init__(self, player=None, library=None, user_lib=None):
        self.player = player
        self.library = library
        self.user_lib = user_lib
        self.stations = None  # internet radio and podcasts, where the app has them (set by the app; #128)
        self.podcasts = None
        self.lyrics = None  # the lyrics of what's playing (set by the app)
        self._methods = {}
        for name in dir(type(self)):  # (names, not bound methods: those would tie the Api to itself)
            if name.startswith("m_"):
                self._methods[name[2:].replace("_", ".")] = (getattr(type(self), name)._api_scope, name)

    @property
    def methods(self):
        return {name: scope for name, (scope, _attr) in self._methods.items()}

    def call(self, name, params=None, allowed=("read", "control")):
        entry = self._methods.get(str(name))
        if entry is None:
            raise ApiError("No such command")
        scope, attr = entry
        if scope not in allowed:
            raise ApiError("Not allowed")
        params = {k: v for k, v in (params if isinstance(params, dict) else {}).items() if isinstance(k, str)}
        fn = getattr(self, attr)
        try:
            inspect.signature(fn).bind(**params)
        except TypeError:
            raise ApiError("Unexpected parameters") from None
        return fn(**params)

    # --- helpers -----------------------------------------------------------------------------------------
    @property
    def _db(self):
        if self.library is None:
            raise ApiError("The library isn't open yet")
        return self.library._db

    def _song(self, t):
        """A song as remotes see it: no path, no cover file, only what's shown."""
        if not t:
            return None
        path = t.get("path") or ""
        liked = rating = None
        if self.user_lib is not None and path:
            liked = self.user_lib.isLiked(path)
            rating = self.user_lib.rating(path)
        return {
            "id": t.get("id"),
            "title": t.get("title") or "",
            "artist": t.get("artist") or "",
            "album": t.get("album") or "",
            "albumArtist": t.get("album_artist") or "",
            "albumKey": t.get("album_key") or "",
            "duration": float(t.get("duration") or 0),
            "year": int(t.get("year") or 0),
            "genre": t.get("genre") or "",
            "composer": t.get("composer") or "",
            "trackNo": int(t.get("track_no") or 0),
            "discNo": int(t.get("disc_no") or 0),
            "liked": liked,
            "rating": rating,
            "explicit": int(t.get("explicit") or 0) == 1,
            "bitDepth": int(t.get("bit_depth") or 0),  # lossless files only; 1 is DSD
            "sampleRate": int(t.get("sample_rate") or 0),
        }

    @staticmethod
    def _album(a):
        return {"key": a.get("album_key") or "", "title": a.get("album") or "", "artist": a.get("album_artist") or "",
                "year": int(a.get("year") or 0), "songs": int(a.get("n") or 0), "duration": float(a.get("duration") or 0)}

    def _tracks_by_ids(self, ids):
        if not isinstance(ids, (list, tuple)):
            raise ApiError("Songs are given as a list of ids")
        ids = [_int(i, -1) for i in ids[:MAX_IDS]]
        ids = [i for i in ids if i > 0]
        if not ids:
            return []
        found = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            for r in self._db._rows(f"SELECT * FROM tracks WHERE id IN ({','.join('?' * len(chunk))})", chunk):
                found[r["id"]] = r
        return [found[i] for i in ids if i in found]

    def _play(self, tracks, index=0, shuffle=False):
        from .library import decorate

        if not tracks:
            raise ApiError("Nothing to play")
        if self.player is None:
            raise ApiError("The player isn't ready yet")
        if shuffle:
            import random

            self.player.setShuffle(True)
            index = random.randrange(len(tracks))
        self.player.playList(decorate([dict(t) for t in tracks]), max(0, min(index, len(tracks) - 1)))
        return {"ok": True}

    def _need_player(self):
        if self.player is None:
            raise ApiError("The player isn't ready yet")
        return self.player

    # --- state ---------------------------------------------------------------------------------------------
    @staticmethod
    def _queue_entry(t):
        kind = t.get("kind") or "music"
        return {"id": t.get("id") if kind == "music" else None, "kind": kind, "title": t.get("title") or "",
                "artist": t.get("artist") or "", "album": t.get("album") or "", "albumKey": t.get("album_key") or "",
                "duration": float(t.get("duration") or 0), "explicit": int(t.get("explicit") or 0) == 1,
                "bitDepth": int(t.get("bit_depth") or 0)}

    def m_state(self):
        """What's playing and how: the song, position, volume, shuffle, repeat, radio and the sleep timer."""
        p = self._need_player()
        cur = p.current if p.hasTrack else {}
        song = None
        if cur:
            song = self._queue_entry(cur)
            if cur.get("kind", "music") == "music" and cur.get("path"):
                full = self._song(cur)
                song.update({k: full[k] for k in ("liked", "rating", "year", "genre", "composer", "sampleRate")})
            if cur.get("stream_title"):
                song["streamTitle"] = cur.get("stream_title")
        return {
            "playing": bool(p.playing), "state": p.state, "song": song,
            "position": int(p.position), "duration": int(p.duration),
            "volume": round(float(p.volume), 3), "muted": bool(p.muted),
            "shuffle": bool(p.shuffle), "repeat": int(p.repeat), "radio": bool(p.radio),
            "index": int(p.currentIndex), "queueLength": int(p.queueLength), "upcoming": int(p.upcomingCount),
            "sleepRemaining": int(p.sleepRemaining), "sleepAfterTrack": bool(p.sleepAfterTrack),
            "sleepAfterAlbum": bool(p.sleepAfterAlbum), "error": p.error or "",
        }

    m_state._api_scope = "read"

    def m_queue(self):
        p = self._need_player()
        q = p.queue
        return {"index": int(p.currentIndex), "songs": [self._queue_entry(t) for t in q[:MAX_LIST * 4]],
                "total": len(q)}

    m_queue._api_scope = "read"

    # --- playback ------------------------------------------------------------------------------------------
    def m_toggle(self):
        self._need_player().toggle()
        return {"ok": True}

    m_toggle._api_scope = "control"

    def m_play(self):
        self._need_player().play()
        return {"ok": True}

    m_play._api_scope = "control"

    def m_pause(self):
        self._need_player().pause()
        return {"ok": True}

    m_pause._api_scope = "control"

    def m_next(self):
        self._need_player().next()
        return {"ok": True}

    m_next._api_scope = "control"

    def m_previous(self):
        self._need_player().previous()
        return {"ok": True}

    m_previous._api_scope = "control"

    def m_seek(self, position=0):
        """To `position` milliseconds into the song."""
        self._need_player().seek(_int(position, 0, 0))
        return {"ok": True}

    m_seek._api_scope = "control"

    def m_volume(self, volume=None, change=None):
        """Set the volume (0–1), or change it by `change`."""
        p = self._need_player()
        if change is not None:
            try:
                delta = float(change)
            except (TypeError, ValueError):
                raise ApiError("change must be a number") from None
            p.setVolume(p.volume + delta if math.isfinite(delta) else p.volume)
        elif volume is not None:
            try:
                v = float(volume)
            except (TypeError, ValueError):
                raise ApiError("volume must be a number") from None
            if not math.isfinite(v):
                raise ApiError("volume must be a number")
            p.setVolume(max(0.0, min(1.0, v)))
        return {"volume": round(float(p.volume), 3)}

    m_volume._api_scope = "control"

    def m_mute(self):
        self._need_player().toggleMute()
        return {"ok": True}

    m_mute._api_scope = "control"

    def m_shuffle(self, on=None):
        p = self._need_player()
        p.toggleShuffle() if on is None else p.setShuffle(bool(on))
        return {"shuffle": bool(p.shuffle)}

    m_shuffle._api_scope = "control"

    def m_repeat(self, mode=None):
        """Cycle repeat, or set it: 0 off, 1 all, 2 one."""
        p = self._need_player()
        p.cycleRepeat() if mode is None else p.setRepeat(_int(mode, 0, 0, 2))
        return {"repeat": int(p.repeat)}

    m_repeat._api_scope = "control"

    def m_radio(self, on=None):
        p = self._need_player()
        p.setRadio(not p.radio if on is None else bool(on))
        return {"radio": bool(p.radio)}

    m_radio._api_scope = "control"

    def m_sleep(self, minutes=None, end=None):
        """Sleep timer: `minutes` (0 off), or end="track" / "album"."""
        p = self._need_player()
        if end == "track":
            p.setSleepAfterTrack(True)
        elif end == "album":
            p.setSleepAfterAlbum(True)
        else:
            p.setSleepMinutes(_int(minutes, 0, 0, 24 * 60))
        return {"ok": True}

    m_sleep._api_scope = "control"

    # --- the queue -----------------------------------------------------------------------------------------
    def m_queue_jump(self, index=0):
        """Play the queue's entry at `index`."""
        p = self._need_player()
        i = _int(index, -1)
        if not 0 <= i < p.queueLength:
            raise ApiError("No such place in the queue")
        p.playIndex(i)
        return {"ok": True}

    m_queue_jump._api_scope = "control"

    def m_queue_remove(self, index=0):
        p = self._need_player()
        i = _int(index, -1)
        if not 0 <= i < p.queueLength:
            raise ApiError("No such place in the queue")
        p.removeAt(i)
        return {"ok": True}

    m_queue_remove._api_scope = "control"

    def m_queue_move(self, src=0, dst=0):
        p = self._need_player()
        a, b = _int(src, -1), _int(dst, -1)
        if not (0 <= a < p.queueLength and 0 <= b < p.queueLength):
            raise ApiError("No such place in the queue")
        p.moveItem(a, b)
        return {"ok": True}

    m_queue_move._api_scope = "control"

    def m_queue_clear(self, upcoming=False):
        p = self._need_player()
        p.clearUpcoming() if upcoming else p.clearQueue()
        return {"ok": True}

    m_queue_clear._api_scope = "control"

    def m_queue_shuffle(self):
        self._need_player().shuffleUpcoming()
        return {"ok": True}

    m_queue_shuffle._api_scope = "control"

    def m_queue_undo(self):
        return {"undone": self._need_player().undoQueue()}

    m_queue_undo._api_scope = "control"

    def m_queue_add(self, ids=(), next=False):  # noqa: A002 - the command's own word
        """Add songs to the end of the queue, or (next=true) right after the playing one."""
        from .library import decorate

        p = self._need_player()
        tracks = decorate([dict(t) for t in self._tracks_by_ids(ids)])
        if not tracks:
            raise ApiError("Nothing to add")
        if next:
            for t in reversed(tracks):
                p.playNext(t)
        else:
            p.enqueueAll(tracks)
        return {"added": len(tracks)}

    m_queue_add._api_scope = "control"

    # --- play things ---------------------------------------------------------------------------------------
    def m_play_songs(self, ids=(), index=0, shuffle=False):
        """Play these songs (in this order), from `index`."""
        return self._play(self._tracks_by_ids(ids), _int(index, 0, 0), bool(shuffle))

    m_play_songs._api_scope = "control"

    def m_play_album(self, key="", index=0, shuffle=False):
        return self._play(self._db.album_tracks(_str(key)), _int(index, 0, 0), bool(shuffle))

    m_play_album._api_scope = "control"

    def m_play_artist(self, name="", shuffle=False):
        return self._play(self._db.artist_tracks(_str(name)), 0, bool(shuffle))

    m_play_artist._api_scope = "control"

    def m_play_genre(self, name="", shuffle=False):
        return self._play(genre_views.tracks(self._db, _str(name)), 0, bool(shuffle))

    m_play_genre._api_scope = "control"

    def m_play_composer(self, name="", shuffle=False):
        return self._play(composer_views.tracks(self._db, _str(name)), 0, bool(shuffle))

    m_play_composer._api_scope = "control"

    def m_play_playlist(self, id=0, index=0, shuffle=False, smart=False):  # noqa: A002
        return self._play(self._playlist_tracks(_int(id), bool(smart)), _int(index, 0, 0), bool(shuffle))

    m_play_playlist._api_scope = "control"

    def m_play_liked(self, index=0, shuffle=False):
        return self._play(self._db.liked_tracks(), _int(index, 0, 0), bool(shuffle))

    m_play_liked._api_scope = "control"

    # --- likes and ratings ---------------------------------------------------------------------------------
    def _path_of(self, song_id):
        rows = self._tracks_by_ids([song_id])
        if not rows:
            raise ApiError("No such song")
        return rows[0]["path"]

    def m_like(self, id=0, liked=None):  # noqa: A002
        """Like or unlike a song (liked omitted: the other way round)."""
        if self.user_lib is None:
            raise ApiError("Not ready yet")
        path = self._path_of(id)
        if liked is None or bool(liked) != self.user_lib.isLiked(path):
            self.user_lib.toggleLike(path)
        return {"liked": self.user_lib.isLiked(path)}

    m_like._api_scope = "control"

    def m_rate(self, id=0, stars=0):  # noqa: A002
        if self.user_lib is None:
            raise ApiError("Not ready yet")
        path = self._path_of(id)
        self.user_lib.setRatingPaths([path], _int(stars, 0, 0, 5))
        return {"ok": True}

    m_rate._api_scope = "control"

    # --- browsing ------------------------------------------------------------------------------------------
    def m_search(self, query="", limit=30):
        q = _str(query, 200).strip()
        if not q:
            return {"songs": [], "albums": [], "artists": [], "corrected": ""}
        limit = _int(limit, 30, 1, 200)
        r = self._db.search(q, track_limit=limit)
        corrected = ""
        if not (r["tracks"] or r["albums"] or r["artists"]) and self.library is not None:
            speller = self.library.speller()  # (None the first time after a reload, while it's made)
            corrected = speller.correct(q) if speller is not None else ""
            if corrected:
                r = self._db.search(corrected, track_limit=limit)
        return {"songs": [self._song(t) for t in r["tracks"]], "albums": [self._album(a) for a in r["albums"]],
                "artists": [{"name": a["name"], "albums": int(a["albums"] or 0), "songs": int(a["tracks"] or 0)}
                            for a in r["artists"]], "corrected": corrected}

    m_search._api_scope = "read"

    def m_albums(self, offset=0, limit=100, sort="title"):
        rows = self._db.albums()
        if sort == "artist":
            rows.sort(key=lambda a: (fold(a.get("album_artist") or ""), -(a.get("year") or 0)))
        elif sort == "year":
            rows.sort(key=lambda a: -(a.get("year") or 0))
        elif sort == "added":
            rows.sort(key=lambda a: -(a.get("added") or 0))
        offset, limit = _int(offset, 0, 0), _int(limit, 100, 1, MAX_LIST)
        return {"total": len(rows), "albums": [self._album(a) for a in rows[offset:offset + limit]]}

    m_albums._api_scope = "read"

    def m_album(self, key=""):
        key = _str(key)
        a = self._db.album(key)
        if not a:
            raise ApiError("No such album")
        return {**self._album(a), "songs": [self._song(t) for t in self._db.album_tracks(key)]}

    m_album._api_scope = "read"

    def m_artists(self, offset=0, limit=200):
        rows = self._db.artists()
        offset, limit = _int(offset, 0, 0), _int(limit, 200, 1, MAX_LIST)
        return {"total": len(rows), "artists": [
            {"name": a["name"], "albums": int(a["albums"] or 0), "songs": int(a["tracks"] or 0),
             "albumKey": ""} for a in rows[offset:offset + limit]]}

    m_artists._api_scope = "read"

    def m_artist(self, name=""):
        name = _str(name)
        albums = self._db.artist_albums(name)
        songs = self._db.artist_tracks(name, limit=MAX_LIST)
        if not albums and not songs:
            raise ApiError("No such artist")
        return {"name": albums[0]["album_artist"] if albums else name, "albums": [self._album(a) for a in albums],
                "songs": [self._song(t) for t in songs]}

    m_artist._api_scope = "read"

    def m_genres(self):
        return {"genres": [{"name": g["name"], "songs": g["tracks"], "albums": g["albums"], "albumKey": g["albumKey"]}
                           for g in genre_views.overview(self._db)]}

    m_genres._api_scope = "read"

    def m_genre(self, name=""):
        page = genre_views.page(self._db, _str(name), top=MAX_LIST)
        return {"name": page["name"], "albums": [self._album({**a, "n": a["n"], "duration": a["duration"]})
                                                 for a in page["albumList"]],
                "songs": [self._song(t) for t in page["songs"]]}

    m_genre._api_scope = "read"

    def m_playlists(self):
        out = [{"id": p["id"], "name": p["name"], "songs": int(p["n"] or 0), "folder": p.get("folder") or "",
                "smart": False} for p in self._db.playlists()]
        for s in self._db.smart_playlists():
            out.append({"id": s["id"], "name": s["name"], "songs": None, "folder": s.get("folder") or "",
                        "smart": True})
        return {"playlists": out}

    m_playlists._api_scope = "read"

    def _playlist_tracks(self, pid, smart):
        if smart:
            row = self._db.smart_playlist(pid)
            if not row:
                raise ApiError("No such playlist")
            try:
                return smart_rules.matching_tracks(self._db, row["rules"])
            except ValueError:
                raise ApiError("This smart playlist's rules can't be read") from None
        if not any(p["id"] == pid for p in self._db.playlists()):
            raise ApiError("No such playlist")
        return self._db.playlist_tracks(pid)

    def m_playlist(self, id=0, smart=False):  # noqa: A002
        tracks = self._playlist_tracks(_int(id), bool(smart))
        return {"songs": [self._song(t) for t in tracks[:MAX_LIST * 4]], "total": len(tracks)}

    m_playlist._api_scope = "read"

    def m_playlist_add(self, id=0, ids=()):  # noqa: A002
        """Add songs to a (plain) playlist."""
        pid = _int(id)
        if self.user_lib is None:
            raise ApiError("Not ready yet")
        if not any(p["id"] == pid for p in self._db.playlists()):
            raise ApiError("No such playlist")
        paths = [t["path"] for t in self._tracks_by_ids(ids)]
        if not paths:
            raise ApiError("Nothing to add")
        self.user_lib.addPathsToPlaylist(pid, paths)
        return {"added": len(paths)}

    m_playlist_add._api_scope = "control"

    def m_liked(self, offset=0, limit=200):
        rows = self._db.liked_tracks()
        offset, limit = _int(offset, 0, 0), _int(limit, 200, 1, MAX_LIST)
        return {"total": len(rows), "songs": [self._song(t) for t in rows[offset:offset + limit]]}

    m_liked._api_scope = "read"

    def m_library_rescan(self):
        """Look through the music folders again for new, changed and removed files (it watches them anyway)."""
        if self.library is None:
            raise ApiError("The library isn't open yet")
        self.library.rescan()
        return {"ok": True}

    m_library_rescan._api_scope = "control"

    def m_library_info(self):
        """How big the library is, and whether it's busy scanning."""
        if self.library is None:
            raise ApiError("The library isn't open yet")
        lib = self.library
        return {"songs": int(lib.trackCount), "albums": int(lib.albumCount), "scanning": bool(lib.scanning)}

    m_library_info._api_scope = "read"

    # --- internet radio and podcasts (#128) ---------------------------------------------------------------
    def _on(self, name):
        """The radio or podcasts service, if it's here and switched on."""
        svc = getattr(self, name)
        if svc is None or not getattr(svc, "_enabled", True):
            raise ApiError("Internet radio is switched off" if name == "stations" else "Podcasts are switched off")
        return svc

    def m_features(self):
        """What this Hallucinate has besides the library, for the remote's pages."""
        return {"stations": self.stations is not None and getattr(self.stations, "_enabled", True),
                "podcasts": self.podcasts is not None and getattr(self.podcasts, "_enabled", True)}

    m_features._api_scope = "read"

    def m_stations(self):
        """Your internet radio stations."""
        from .stations import detail

        out = []
        for st in self._on("stations")._db.stations():
            out.append({"id": int(st["id"]), "name": _str(st.get("name"), 200), "detail": _str(detail(st), 200),
                        "art": f"~station/{int(st['id'])}"})
        return {"stations": out}

    m_stations._api_scope = "read"

    def m_play_station(self, id=0):  # noqa: A002
        """Tune in to one of your stations (the others follow it, so Next changes station)."""
        svc = self._on("stations")
        if not svc._db.station(int(id)):
            raise ApiError("No such station")
        svc.play(int(id))
        return {"ok": True}

    m_play_station._api_scope = "control"

    def m_podcasts(self):
        """The shows you follow, newest episode first."""
        out = []
        for p in self._on("podcasts")._db.podcasts():
            out.append({"id": int(p["id"]), "title": _str(p.get("title"), 200), "author": _str(p.get("author"), 200),
                        "unplayed": int(p.get("unplayed") or 0), "episodes": int(p.get("episodes") or 0),
                        "art": f"~podcast/{int(p['id'])}"})
        return {"podcasts": out}

    m_podcasts._api_scope = "read"

    def m_podcast(self, id=0, offset=0, limit=50):  # noqa: A002
        """A show's episodes, newest first."""
        svc = self._on("podcasts")
        show = svc._db.podcast(int(id))
        if not show:
            raise ApiError("No such show")
        episodes = svc._db.episodes(int(id))
        offset, limit = max(0, int(offset)), max(1, min(200, int(limit)))
        rows = [{"id": int(e["id"]), "title": _str(e.get("title"), 300), "published": float(e.get("published") or 0),
                 "duration": float(e.get("duration") or 0), "played": bool(e.get("played")),
                 "position": float(e.get("position") or 0)} for e in episodes[offset:offset + limit]]
        return {"title": _str(show.get("title"), 200), "author": _str(show.get("author"), 200),
                "art": f"~podcast/{int(id)}", "episodes": rows, "total": len(episodes)}

    m_podcast._api_scope = "read"

    def m_play_episode(self, id=0, next=False, queue=False):  # noqa: A002 - the command's own words
        """Play an episode from where you stopped (or put it next / at the end of the queue)."""
        svc = self._on("podcasts")
        if not svc._db.episode(int(id)):
            raise ApiError("No such episode")
        (svc.playNext if next else svc.enqueue if queue else svc.play)(int(id))
        return {"ok": True}

    m_play_episode._api_scope = "control"

    # --- lyrics, the equaliser, recent plays --------------------------------------------------------------
    def m_lyrics(self):
        """The playing song's lyrics: timed lines ({t: ms, text}) when there are, else plain text. `offset` is the
        timing nudge (a line shows at t - offset)."""
        lc = self.lyrics
        if lc is None:
            return {"status": "none", "synced": False, "lines": [], "plain": "", "offset": 0}
        lines = []
        for line in lc.lines or []:
            try:
                lines.append({"t": int(line.get("t", 0)), "text": str(line.get("text", ""))})
            except (AttributeError, TypeError, ValueError):
                continue
        return {"status": str(lc.status), "synced": bool(lines), "lines": lines, "plain": str(lc.plain or ""),
                "offset": int(lc.offset or 0)}

    m_lyrics._api_scope = "read"

    def m_eq(self):
        """The equaliser: on or off, which preset, and the presets to choose from."""
        p = self._need_player()
        return {"available": bool(p.eqAvailable), "enabled": bool(p.eqEnabled), "preset": str(p.eqPreset or ""),
                "presets": [str(n) for n in p.eqPresets]}

    m_eq._api_scope = "read"

    def m_eq_set(self, preset=None, enabled=None):
        """Choose an equaliser preset, and/or turn the equaliser on or off."""
        p = self._need_player()
        if preset is not None:
            name = _str(preset, 60)
            if name not in [str(n) for n in p.eqPresets]:
                raise ApiError("No such preset")
            p.setEqPreset(name)
            if enabled is None:
                p.setEqEnabled(True)  # picking a preset means wanting to hear it
        if enabled is not None:
            p.setEqEnabled(bool(enabled))
        return self.m_eq()

    m_eq_set._api_scope = "control"

    def m_recent(self, limit=30):
        """What was listened to last, newest first: songs still in the library can be played again (`id`)."""
        from .core import history

        rows = history.plays(self._db, limit=_int(limit, 30, 1, 100))
        out = []
        for r in rows:
            t = self._db.track_by_path(r["path"]) if r.get("available") and r.get("path") else None
            out.append({"id": t.get("id") if t else None, "title": r.get("title") or "", "artist": r.get("artist") or "",
                        "album": r.get("album") or "", "albumKey": r.get("album_key") or "", "day": r.get("day") or "",
                        "time": r.get("time") or ""})
        return {"plays": out}

    m_recent._api_scope = "read"

    def m_top(self, period="month", limit=10):
        """Most played artists, albums and songs over the last week, month or year (or of all time)."""
        import time

        days = {"week": 7, "month": 30, "year": 365, "all": None}
        if period not in days:
            raise ApiError("period is week, month, year or all")
        start = None if days[period] is None else time.time() - days[period] * 86400
        st = self._db.listening_stats(period_start=start, limit=_int(limit, 10, 1, 50))
        return {"period": period,
                "artists": [{"name": a.get("name") or "", "plays": int(a.get("plays") or 0)} for a in st.get("artists", [])],
                "albums": [{"album": a.get("album") or "", "artist": a.get("album_artist") or "", "albumKey": a.get("album_key") or "",
                            "plays": int(a.get("plays") or 0)} for a in st.get("albums", [])],
                "songs": [{"title": t.get("title") or "", "artist": t.get("artist") or "", "plays": int(t.get("plays") or 0)}
                          for t in st.get("tracks", [])]}

    m_top._api_scope = "read"

    def art_file(self, album_key):
        """The cover file for an album key, or a station's or show's picture ("~station/3", "~podcast/7"; for the
        art endpoint, never sent to a client)."""
        key = _str(album_key)
        if key.startswith(("~station/", "~podcast/")):
            kind, _, num = key[1:].partition("/")
            try:
                num = int(num)
            except ValueError:
                return ""
            try:
                if kind == "station":
                    svc = self._on("stations")
                    st = svc._db.station(num)
                    f = svc._icon_file(st) if st else None
                else:
                    svc = self._on("podcasts")
                    p = svc._db.podcast(num)
                    f = svc._image_file(p.get("image")) if p else None
            except ApiError:
                return ""
            return str(f) if f and f.exists() else ""
        a = self._db.album(key)
        return (a or {}).get("art") or ""
