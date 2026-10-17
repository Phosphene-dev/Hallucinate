"""Music servers (Settings → Music servers): your Navidrome or other Subsonic server's songs in the library.

Their songs go in the library like your own files (albums, artists, search, playlists, stats), with paths
that hold no login (core/remote.py). The password is kept in the system keyring only, never in settings or
the library, and is refused if there's no keyring to keep it safe. A sync reads every song the server has,
adds what's new, updates what changed and takes out what the server no longer has; covers are fetched once
and kept with the others. A server that can't be reached makes its songs unavailable (the player moves past
them) and is tried again every few minutes. Switched off in Settings → Features, every server song leaves the
library (your plays, ratings and playlists keep them, and they come back when it's switched on)."""
import datetime
import json
import logging
import os
import time

from PySide6.QtCore import Property, QObject, QSettings, QTimer, Signal, Slot

from .core import net, remote, subsonic, tags
from .core.atomic import write_atomic
from .library import _Reader

logger = logging.getLogger(__name__)
KEYRING_SERVICE = "Hallucinate Music servers"
RETRY_MS = 5 * 60 * 1000  # a server that didn't answer is tried again this often
SYNC_EVERY_S = 12 * 3600  # synced again on start when the last sync is older than this


def _when(text):
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() if text else 0.0
    except ValueError:
        return 0.0


def track_row(server_id, song):
    """A library row for a song a Subsonic server listed (see subsonic.song_from)."""
    album_artist = song["album_artist"] or song["artist"]
    # Its own album, not merged with a copy you have as files (or one on another server)
    key_base = f"{album_artist}\x1esubsonic:{server_id}" if album_artist else f"\x1esubsonic:{server_id}:{song['album_id']}"
    fmt = song["suffix"].upper() or "STREAM"
    return {
        "path": remote.make_path("subsonic", server_id, song["id"]),
        "mtime": _when(song["changed"]), "size": song["size"],
        "title": song["title"], "artist": song["artist"] or album_artist, "album_artist": album_artist,
        "aa_tag": 1 if album_artist else 0, "album": song["album"],
        "album_key": tags.album_key(key_base, song["album"], ""),
        "track_no": song["track_no"], "disc_no": song["disc_no"], "year": song["year"], "genre": song["genre"],
        "duration": song["duration"], "fmt": fmt, "codec": fmt, "bitrate": song["bitrate"],
        "sample_rate": song["sample_rate"], "art": None, "rg_track": song["rg_track"],
        "rg_album": song["rg_album"], "rg_peak": song["rg_peak"], "file": None, "rating": song["rating"],
    }


def _keyring():
    import keyring

    return keyring


class Servers(QObject):
    changed = Signal()
    message = Signal(str)
    libraryChanged = Signal()  # server songs were added or taken out: reload the library
    _done = Signal(object)

    def __init__(self, db_path, art_dir, player=None, parent=None):
        super().__init__(parent)
        self._settings = QSettings("hallucinate", "hallucinate")
        self._art_dir = str(art_dir)
        self._worker = _Reader(str(db_path), "servers")
        self._enabled = False
        self._applied = False  # the first setEnabled also tidies up after a run that ended with them on
        self._state = {}  # server id -> {"status", "busy", "songs", "error"}
        self._clients = {}  # server id -> subsonic.Server (holding the password, in memory only)
        try:
            self._list = [s for s in json.loads(self._settings.value("servers/list", "[]") or "[]")
                          if isinstance(s, dict) and s.get("id") and s.get("base")]
        except (TypeError, ValueError):
            self._list = []
        self._done.connect(self._finish)
        self._retry = QTimer(self)
        self._retry.setInterval(RETRY_MS)
        self._retry.timeout.connect(self._retry_down)
        self._player = player
        if player is not None and hasattr(player, "played"):
            player.played.connect(self._played)

    # --- what Settings shows -------------------------------------------------------------------------------
    @Property("QVariantList", notify=changed)
    def servers(self):
        out = []
        for s in self._list:
            st = self._state.get(s["id"], {})
            out.append({"id": s["id"], "name": s.get("name") or s["base"], "base": s["base"], "user": s.get("user", ""),
                        "status": st.get("status", "waiting"), "busy": bool(st.get("busy")),
                        "songs": st.get("songs", s.get("songs", 0)), "error": st.get("error", ""),
                        "synced": s.get("synced", 0), "secure": subsonic.is_private_link(s["base"])})
        return out

    @Property(bool, notify=changed)
    def busy(self):
        return any(st.get("busy") for st in self._state.values())

    @Slot(str, result=bool)
    def linkIsSecure(self, base):
        """For the add dialog: whether the typed link is https or on your own network."""
        try:
            return subsonic.is_private_link(subsonic.normalise_base(base))
        except ValueError:
            return True  # nothing to warn about yet

    # --- switching on and off ------------------------------------------------------------------------------
    @Slot(bool)
    def setEnabled(self, on):
        on = bool(on)
        if on == self._enabled and self._applied:
            return
        self._applied = True
        self._enabled = on
        if on:
            for s in self._list:
                self._connect(s, sync=time.time() - s.get("synced", 0) > SYNC_EVERY_S)
        else:
            self._retry.stop()
            for s in self._list:
                self._disconnect(s["id"])
            self._worker.submit(lambda db: self._take_out(db, None))  # every server song, listed server or not
        self.changed.emit()

    def _connect(self, s, sync=False):
        password = self._password(s["id"])
        if password is None:
            self._state[s["id"]] = {"status": "error", "error": "The password isn't in the system keyring"}
            return
        try:
            client = subsonic.Server(s["base"], s.get("user", ""), password)
        except ValueError as exc:
            self._state[s["id"]] = {"status": "error", "error": str(exc)}
            return
        self._clients[s["id"]] = client
        remote.register("subsonic", s["id"], client)
        self._check(s["id"], sync)

    def _disconnect(self, sid):
        remote.forget("subsonic", sid)
        self._clients.pop(sid, None)
        self._state.pop(sid, None)

    # --- adding and removing -------------------------------------------------------------------------------
    @Slot(str, str, str, str)
    def addServer(self, base, user, password, name=""):
        """Check the link and login, keep the password in the keyring, and read the server's songs."""
        try:
            base = subsonic.normalise_base(base)
        except ValueError as exc:
            self.message.emit(str(exc))
            return
        if not user or not password:
            self.message.emit("Type the user name and password you sign in to the server with")
            return
        if any(s["base"] == base and s.get("user") == user for s in self._list):
            self.message.emit("That server is already added")
            return
        if net.is_offline():
            self.message.emit("Offline mode is on, so the server can't be checked")
            return
        sid = str(max([int(s["id"]) for s in self._list if str(s["id"]).isdigit()] + [0]) + 1)
        self._state[sid] = {"status": "checking", "busy": True}
        self.changed.emit()
        entry = {"id": sid, "kind": "subsonic", "base": base, "user": user, "name": (name or "").strip()[:100]}

        def work(_db):
            try:
                info = subsonic.Server(base, user, password).ping()
            except subsonic.SubsonicError as exc:
                return {"op": "add", "id": sid, "error": f"Couldn't sign in: {exc}"}
            except (OSError, ValueError) as exc:
                return {"op": "add", "id": sid, "error": f"Couldn't reach the server: {net.describe(exc)}"}
            return {"op": "add", "id": sid, "entry": entry, "password": password, "info": info}

        self._run(work)

    @Slot(str)
    def removeServer(self, sid):
        """Forget a server: its songs leave the library and its password leaves the keyring."""
        self._list = [s for s in self._list if s["id"] != sid]
        self._save_list()
        self._disconnect(sid)
        try:
            _keyring().delete_password(KEYRING_SERVICE, sid)
        except Exception:  # noqa: BLE001 - not there, or no keyring: nothing to remove
            pass
        self._worker.submit(lambda db: self._take_out(db, [sid]))
        self.changed.emit()

    @Slot(str)
    def sync(self, sid):
        if sid in self._clients and not self._state.get(sid, {}).get("busy"):
            self._check(sid, sync=True)

    @Slot()
    def syncAll(self):
        for s in self._list:
            self.sync(s["id"])

    # --- the work ------------------------------------------------------------------------------------------
    def _check(self, sid, sync):
        client = self._clients.get(sid)
        if client is None:
            return
        self._state[sid] = {**self._state.get(sid, {}), "busy": True, "status": "syncing" if sync else "checking"}
        self.changed.emit()

        def work(db):
            try:
                client.ping()
            except (OSError, ValueError) as exc:
                return {"op": "check", "id": sid, "ok": False, "error": _plain(exc)}
            if not sync:
                return {"op": "check", "id": sid, "ok": True}
            try:
                count = self._sync(db, sid, client)
            except (OSError, ValueError) as exc:
                return {"op": "check", "id": sid, "ok": True, "error": f"The sync stopped: {_plain(exc)}"}
            return {"op": "check", "id": sid, "ok": True, "songs": count, "synced": time.time()}

        self._run(work)

    def _sync(self, db, sid, client):
        prefix = remote.prefix("subsonic", sid)
        before = {r[0] for r in db.conn.execute("SELECT path FROM tracks WHERE substr(path, 1, ?) = ?",
                                                (len(prefix), prefix))}
        hidden = db.hidden_paths()
        seen, covers = set(), {}
        for song in client.songs():
            row = track_row(sid, song)
            if row["path"] in hidden:  # you removed it from the library
                continue
            seen.add(row["path"])
            if song["cover"]:
                covers.setdefault(row["album_key"], song["cover"])
            db.upsert_track(row)
            if len(seen) % 2000 == 0:
                db.commit()
        db.remove_paths(sorted(before - seen))
        db.finalize()
        db.commit()
        self._fetch_covers(db, client, covers)
        return len(seen)

    def _fetch_covers(self, db, client, covers):
        """Each album's cover, fetched once and kept with the others (a cover you chose stays yours)."""
        os.makedirs(self._art_dir, exist_ok=True)
        for key, cover_id in covers.items():
            path = os.path.join(self._art_dir, f"{key}.jpg")
            chosen = db.chosen_art(key)
            if chosen and os.path.isfile(chosen):
                db.set_album_art(key, chosen)
                continue
            if not os.path.isfile(path):
                try:
                    data = client.cover(cover_id)
                except (OSError, ValueError):
                    continue
                if not data:
                    continue
                if data[:8] == b"\x89PNG\r\n\x1a\n":
                    path = os.path.join(self._art_dir, f"{key}.png")
                write_atomic(path, lambda fh, d=data: fh.write(d))
            db.set_album_art(key, path)
        db.commit()

    def _take_out(self, db, ids):
        """Take the songs of servers `ids` (None: of every server) out of the library."""
        if ids is None:
            paths = [r[0] for r in db.conn.execute(f"SELECT path FROM tracks WHERE NOT ({remote.SQL_LOCAL})")]
        else:
            paths = []
            for sid in ids:
                prefix = remote.prefix("subsonic", sid)
                paths += [r[0] for r in db.conn.execute("SELECT path FROM tracks WHERE substr(path, 1, ?) = ?",
                                                        (len(prefix), prefix))]
        if paths:
            db.remove_paths(paths)
            db.commit()
            self._done.emit({"op": "removed"})

    def _run(self, work):
        def wrapped(db):
            try:
                result = work(db)
            except Exception as exc:  # noqa: BLE001 - a worker must always report back
                logger.exception("Music server work failed")
                result = {"op": "failed", "error": _plain(exc)}
            self._done.emit(result)

        self._worker.submit(wrapped)

    @Slot(object)
    def _finish(self, r):
        op, sid = r.get("op"), r.get("id")
        if op == "removed":
            self.libraryChanged.emit()
            return
        if op == "add":
            if r.get("error"):
                self._state.pop(sid, None)
                self.message.emit(r["error"])
                self.changed.emit()
                return
            try:
                _keyring().set_password(KEYRING_SERVICE, sid, r["password"])
            except Exception:  # noqa: BLE001
                self._state.pop(sid, None)
                self.message.emit("The system keyring isn't available, so the password can't be kept safely")
                self.changed.emit()
                return
            entry = r["entry"]
            if not entry["name"]:
                entry["name"] = (r["info"].get("type") or "Server").title()
            self._list.append(entry)
            self._save_list()
            self._state[sid] = {"status": "ok"}
            self.message.emit(f"Added {entry['name']}: reading its songs…")
            if self._enabled:
                self._connect(entry, sync=True)
            self.changed.emit()
            return
        if op == "check":
            st = self._state.setdefault(sid, {})
            st["busy"] = False
            remote.set_reachable("subsonic", sid, r["ok"])
            st["status"] = "ok" if r["ok"] else "down"
            st["error"] = r.get("error", "")
            if not r["ok"]:
                self._retry.start()
            if "songs" in r:
                st["songs"] = r["songs"]
                for s in self._list:
                    if s["id"] == sid:
                        s["songs"], s["synced"] = r["songs"], r["synced"]
                self._save_list()
                self.libraryChanged.emit()
            self.changed.emit()
            return
        if op == "failed":
            for st in self._state.values():
                st["busy"] = False
            self.message.emit(f"Music server: {r['error']}")
            self.changed.emit()

    @Slot()
    def _retry_down(self):
        down = [sid for sid, st in self._state.items() if st.get("status") == "down"]
        if not down:
            self._retry.stop()
        for sid in down:
            self._check(sid, sync=False)

    @Slot(object)
    def _played(self, track):
        """A server song you played counts on the server too (its own play counts and history)."""
        parts = remote.parse(track.get("path", "")) if isinstance(track, dict) else None
        client = self._clients.get(parts[1]) if parts else None
        if client is None or not remote.available(track["path"]):
            return
        self._worker.submit(lambda _db, c=client, i=parts[2]: _quietly(c.scrobble, i, int(time.time() * 1000)))

    # --- keeping things ------------------------------------------------------------------------------------
    def _password(self, sid):
        try:
            return _keyring().get_password(KEYRING_SERVICE, sid)
        except Exception:  # noqa: BLE001
            return None

    def _save_list(self):
        keep = [{k: s.get(k) for k in ("id", "kind", "base", "user", "name", "songs", "synced")} for s in self._list]
        self._settings.setValue("servers/list", json.dumps(keep))

    def shutdown(self):
        self._retry.stop()
        self._worker.close()


def _plain(exc):
    return str(exc) if isinstance(exc, (subsonic.SubsonicError, ValueError)) else net.describe(exc)


def _quietly(fn, *args):
    try:
        fn(*args)
    except (OSError, ValueError):
        pass
