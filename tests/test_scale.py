"""Big-library safeguards: folded columns instead of per-row Python calls, slimmer song rows, and reload
bookkeeping that keeps unchanged rows and never compares or frees a whole library in one go."""
import sqlite3

from hallucinate.core import rules as R
from hallucinate.core.db import Database
from hallucinate.library import _differs, _free, share_strings
from hallucinate.models import DictModel


def add(db, path, artist, genre="", album_artist=None, aa_tag=1):
    db.upsert_track({
        "path": path, "mtime": 0, "size": 1, "title": path.rsplit("/", 1)[1], "artist": artist,
        "album_artist": album_artist if album_artist is not None else artist, "aa_tag": aa_tag,
        "album": "LP", "album_key": f"{artist}|lp", "track_no": 0, "disc_no": 0, "year": 2000, "genre": genre,
        "duration": 200, "fmt": "FLAC", "codec": "FLAC", "bitrate": 900_000, "sample_rate": 44100,
    })


def test_text_rules_compare_folded_columns_not_python(db):
    """Every text field with a folded copy is matched against it, so SQLite never calls back into Python per
    row (each call needs the GIL, which crawls while other threads are busy)."""
    for field, (kind, expr, _label) in R.FIELDS.items():
        if kind != "text" or expr not in R.FOLDED:
            continue
        sql, _params = R._condition({"field": field, "op": "contains", "value": "x"}, 0)
        assert "fold(" not in sql, field

    add(db, "/m/a", "Ana", "Électronique")
    add(db, "/m/b", "Bo", "Folk")
    db.commit()
    found = R.matching_tracks(db, {"rules": [{"field": "genre", "op": "contains", "value": "ELECTRO"}],
                                   "sort": "title"}, 0)
    assert [r["path"] for r in found] == ["/m/a"]


def test_old_databases_gain_folded_genres(tmp_path):
    path = tmp_path / "lib.db"
    db = Database(path)
    add(db, "/m/a", "Ana", "Électronique")
    add(db, "/m/b", "Bo", "")
    db.commit()
    db.close()
    con = sqlite3.connect(path)
    con.execute("ALTER TABLE tracks DROP COLUMN s_genre")
    con.commit()
    con.close()

    db = Database(path)
    try:
        got = dict(db.conn.execute("SELECT path, s_genre FROM tracks").fetchall())
    finally:
        db.close()
    assert got == {"/m/a": "electronique", "/m/b": ""}


def test_finalize_folds_derived_album_artists(db):
    add(db, "/m/1", "Ána", album_artist="", aa_tag=0)
    add(db, "/m/2", "Ána", album_artist="", aa_tag=0)
    db.commit()
    db.finalize()
    rows = db.conn.execute("SELECT album_artist, s_aa FROM tracks").fetchall()
    assert {tuple(r) for r in rows} == {("Ána", "ana")}


def test_song_list_drops_only_search_and_housekeeping_columns(db):
    add(db, "/m/a", "Ana", "Jazz")
    db.commit()
    [song] = db.song_list()
    assert not set(Database.SONG_LIST_SKIP) & set(song)
    full = dict(db.tracks()[0])
    assert {k: v for k, v in full.items() if k not in Database.SONG_LIST_SKIP} == song


def test_share_strings_keeps_one_copy_of_repeated_text():
    rows = [{"artist": "".join(["Ana ", "Lee"]), "album": None} for _ in range(3)]
    share_strings(rows)
    assert rows[0]["artist"] is rows[1]["artist"] is rows[2]["artist"]
    assert rows[0]["album"] is None


def test_differs_matches_plain_comparison():
    rows = [{"id": i} for i in range(5000)]
    assert not _differs(rows, [dict(r) for r in rows])
    assert _differs(rows, rows[:-1])
    changed = [dict(r) for r in rows]
    changed[4321]["id"] = -1
    assert _differs(rows, changed)


def test_free_empties_lists_in_place():
    lists = [list(range(12_000)), []]
    _free(lists, chunk=5000)
    assert lists == [[], []]


def test_unchanged_reload_keeps_the_rows_qml_has(qapp):
    model = DictModel(["id"], key_field="id")
    model.set_items([{"id": 1}, {"id": 2}])
    before = model.items()
    revision, _keys = model.snapshot_keys()
    resets = []
    model.modelReset.connect(lambda: resets.append(1))
    unused = model.update_items([{"id": 1}, {"id": 2}], [], revision, changed=False)
    assert model.items() == before and model.items()[0] is before[0]
    assert unused[0] is not before[0] and not resets
