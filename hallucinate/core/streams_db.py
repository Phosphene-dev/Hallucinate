"""Internet radio stations and podcasts, kept in their own small database (streams.db) next to the library's.

None of it touches the music library: stations and episodes never show up in songs, stats, history or recap.
Each row is small and the tables stay in the hundreds or low thousands, so the GUI thread may use it directly;
anything that needs the network happens elsewhere."""
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    homepage TEXT NOT NULL DEFAULT '',
    favicon TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    codec TEXT NOT NULL DEFAULT '',
    bitrate INTEGER NOT NULL DEFAULT 0,
    uuid TEXT NOT NULL DEFAULT '',
    added REAL NOT NULL,
    last_played REAL NOT NULL DEFAULT 0,
    plays INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS podcasts(
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    feed_url TEXT NOT NULL DEFAULT '',
    folder TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT '',
    image TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    added REAL NOT NULL,
    checked REAL NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    auto_download INTEGER NOT NULL DEFAULT 0,
    keep INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS episodes(
    id INTEGER PRIMARY KEY,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    guid TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    mime TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    published REAL NOT NULL DEFAULT 0,
    duration REAL NOT NULL DEFAULT 0,
    image TEXT NOT NULL DEFAULT '',
    chapters_url TEXT NOT NULL DEFAULT '',
    local_path TEXT NOT NULL DEFAULT '',
    position REAL NOT NULL DEFAULT 0,
    played INTEGER NOT NULL DEFAULT 0,
    played_at REAL NOT NULL DEFAULT 0,
    UNIQUE(podcast_id, guid)
);
CREATE INDEX IF NOT EXISTS idx_episodes_podcast ON episodes(podcast_id, published);
"""

STATION_FIELDS = ("name", "url", "homepage", "favicon", "tags", "country", "codec", "bitrate", "uuid")
PODCAST_FIELDS = ("title", "author", "feed_url", "folder", "link", "image", "description")
EPISODE_FIELDS = ("guid", "title", "description", "url", "mime", "size", "published", "duration", "image",
                  "chapters_url", "local_path")


class StreamsDB:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        ecols = {r["name"] for r in self.conn.execute("PRAGMA table_info(episodes)")}
        if "up_next" not in ecols:  # its place in Up next (0: not in it)
            self.conn.execute("ALTER TABLE episodes ADD COLUMN up_next REAL NOT NULL DEFAULT 0")
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(podcasts)")}
        for name, kind in (("newest_first", "INTEGER NOT NULL DEFAULT 1"), ("hide_played", "INTEGER NOT NULL DEFAULT 0"),
                           ("speed", "REAL NOT NULL DEFAULT 0"), ("skip_intro", "INTEGER NOT NULL DEFAULT 0"),
                           ("skip_outro", "INTEGER NOT NULL DEFAULT 0")):
            if name not in cols:
                self.conn.execute(f"ALTER TABLE podcasts ADD COLUMN {name} {kind}")

    def close(self):
        self.conn.close()

    # --- stations --------------------------------------------------------------------------------------
    def stations(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM stations ORDER BY name COLLATE NOCASE")]

    def station(self, station_id):
        row = self.conn.execute("SELECT * FROM stations WHERE id=?", (station_id,)).fetchone()
        return dict(row) if row else None

    def station_by_url(self, url):
        row = self.conn.execute("SELECT * FROM stations WHERE url=?", (url,)).fetchone()
        return dict(row) if row else None

    def add_station(self, info):
        """Save a station (or, if its stream is already saved, return that one). Returns its id."""
        existing = self.station_by_url(info["url"])
        if existing:
            return existing["id"]
        fields = {k: info.get(k) or ("" if k != "bitrate" else 0) for k in STATION_FIELDS}
        fields["name"] = (fields["name"] or info["url"]).strip()
        cur = self.conn.execute(
            f"INSERT INTO stations({', '.join(fields)}, added) VALUES ({', '.join('?' * len(fields))}, ?)",
            (*fields.values(), time.time()))
        self.conn.commit()
        return cur.lastrowid

    def update_station(self, station_id, **fields):
        fields = {k: v for k, v in fields.items() if k in STATION_FIELDS}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            self.conn.execute(f"UPDATE stations SET {sets} WHERE id=?", (*fields.values(), station_id))
            self.conn.commit()

    def remove_station(self, station_id):
        self.conn.execute("DELETE FROM stations WHERE id=?", (station_id,))
        self.conn.commit()

    def station_played(self, station_id):
        self.conn.execute("UPDATE stations SET last_played=?, plays=plays+1 WHERE id=?", (time.time(), station_id))
        self.conn.commit()

    # --- podcasts --------------------------------------------------------------------------------------
    def podcasts(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM episodes e WHERE e.podcast_id=p.id AND e.played=0) AS unplayed, "
            "(SELECT MAX(published) FROM episodes e WHERE e.podcast_id=p.id) AS latest, "
            "(SELECT COUNT(*) FROM episodes e WHERE e.podcast_id=p.id) AS episodes "
            "FROM podcasts p ORDER BY latest DESC, title COLLATE NOCASE")]

    def podcast(self, podcast_id):
        row = self.conn.execute("SELECT * FROM podcasts WHERE id=?", (podcast_id,)).fetchone()
        return dict(row) if row else None

    def podcast_by(self, feed_url="", folder=""):
        if feed_url:
            row = self.conn.execute("SELECT * FROM podcasts WHERE feed_url=?", (feed_url,)).fetchone()
        else:
            row = self.conn.execute("SELECT * FROM podcasts WHERE folder=? AND folder<>''", (folder,)).fetchone()
        return dict(row) if row else None

    def add_podcast(self, info):
        existing = self.podcast_by(info.get("feed_url", ""), info.get("folder", ""))
        if existing:
            return existing["id"]
        fields = {k: info.get(k) or "" for k in PODCAST_FIELDS}
        fields["title"] = fields["title"] or fields["feed_url"] or fields["folder"]
        cur = self.conn.execute(
            f"INSERT INTO podcasts({', '.join(fields)}, added) VALUES ({', '.join('?' * len(fields))}, ?)",
            (*fields.values(), time.time()))
        self.conn.commit()
        return cur.lastrowid

    def update_podcast(self, podcast_id, **fields):
        allowed = set(PODCAST_FIELDS) | {"checked", "error", "auto_download", "keep", "newest_first", "hide_played",
                                         "speed", "skip_intro", "skip_outro"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            self.conn.execute(f"UPDATE podcasts SET {sets} WHERE id=?", (*fields.values(), podcast_id))
            self.conn.commit()

    def remove_podcast(self, podcast_id):
        self.conn.execute("DELETE FROM podcasts WHERE id=?", (podcast_id,))
        self.conn.commit()

    # --- episodes --------------------------------------------------------------------------------------
    def merge_episodes(self, podcast_id, episodes):
        """Add new episodes and refresh what the feed says about known ones, keeping what's ours (where you
        stopped, played, the downloaded file). Returns the ids of the episodes that are new."""
        new = []
        for ep in episodes:
            fields = {k: ep.get(k) if ep.get(k) is not None else ("" if k not in ("size", "published", "duration") else 0)
                      for k in EPISODE_FIELDS if k != "local_path"}
            if not fields["guid"]:
                continue
            row = self.conn.execute("SELECT id FROM episodes WHERE podcast_id=? AND guid=?",
                                    (podcast_id, fields["guid"])).fetchone()
            if row:
                sets = ", ".join(f"{k}=?" for k in fields if k != "guid")
                self.conn.execute(f"UPDATE episodes SET {sets} WHERE id=?",
                                  (*[v for k, v in fields.items() if k != "guid"], row["id"]))
            else:
                if ep.get("local_path"):
                    fields["local_path"] = ep["local_path"]
                cur = self.conn.execute(
                    f"INSERT INTO episodes(podcast_id, {', '.join(fields)}) VALUES (?, {', '.join('?' * len(fields))})",
                    (podcast_id, *fields.values()))
                new.append(cur.lastrowid)
        self.conn.commit()
        return new

    def episodes(self, podcast_id=None, unplayed_only=False, limit=None, oldest_first=False, text=""):
        sql = ("SELECT e.*, p.title AS podcast, p.image AS podcast_image FROM episodes e "
               "JOIN podcasts p ON p.id=e.podcast_id")
        where, args = [], []
        if podcast_id is not None:
            where.append("e.podcast_id=?")
            args.append(podcast_id)
        if unplayed_only:
            where.append("e.played=0")
        for word in (text or "").split():
            where.append("(e.title LIKE ? ESCAPE '\\' OR e.description LIKE ? ESCAPE '\\')")
            pattern = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            args += [pattern, pattern]
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY e.published ASC, e.id ASC" if oldest_first else " ORDER BY e.published DESC, e.id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in self.conn.execute(sql, args)]

    def episode(self, episode_id):
        row = self.conn.execute(
            "SELECT e.*, p.title AS podcast, p.image AS podcast_image FROM episodes e "
            "JOIN podcasts p ON p.id=e.podcast_id WHERE e.id=?", (episode_id,)).fetchone()
        return dict(row) if row else None

    def in_progress(self, limit=20):
        """Episodes started and not finished, most recently listened first."""
        return [dict(r) for r in self.conn.execute(
            "SELECT e.*, p.title AS podcast, p.image AS podcast_image FROM episodes e "
            "JOIN podcasts p ON p.id=e.podcast_id WHERE e.played=0 AND e.position>0 "
            "ORDER BY e.played_at DESC LIMIT ?", (limit,))]

    def set_position(self, episode_id, seconds):
        self.conn.execute("UPDATE episodes SET position=?, played_at=? WHERE id=?",
                          (max(0.0, float(seconds)), time.time(), episode_id))
        self.conn.commit()

    def set_played(self, episode_ids, played=True):
        ids = list(episode_ids)
        if not ids:
            return
        marks = ",".join("?" * len(ids))
        self.conn.execute(f"UPDATE episodes SET played=?, position=0, played_at=?{', up_next=0' if played else ''} "
                          f"WHERE id IN ({marks})", (1 if played else 0, time.time(), *ids))
        self.conn.commit()

    def up_next(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT e.*, p.title AS podcast, p.image AS podcast_image FROM episodes e "
            "JOIN podcasts p ON p.id=e.podcast_id WHERE e.up_next>0 ORDER BY e.up_next")]

    def set_up_next(self, episode_id, on, first=False):
        if not on:
            self.conn.execute("UPDATE episodes SET up_next=0 WHERE id=?", (episode_id,))
        else:
            row = self.conn.execute("SELECT MIN(up_next), MAX(up_next) FROM episodes WHERE up_next>0").fetchone()
            lo, hi = row[0] or 1.0, row[1] or 0.0
            self.conn.execute("UPDATE episodes SET up_next=? WHERE id=?", (lo / 2 if first else hi + 1, episode_id))
        self.conn.commit()

    def set_local_path(self, episode_id, path):
        self.conn.execute("UPDATE episodes SET local_path=? WHERE id=?", (path or "", episode_id))
        self.conn.commit()

    def downloaded(self, podcast_id=None):
        sql = "SELECT * FROM episodes WHERE local_path<>''"
        args = ()
        if podcast_id is not None:
            sql += " AND podcast_id=?"
            args = (podcast_id,)
        return [dict(r) for r in self.conn.execute(sql, args)]
