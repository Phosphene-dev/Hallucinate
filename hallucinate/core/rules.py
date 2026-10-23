"""Rule sets for smart playlists, compiled to SQL against the library.

A rule set is plain JSON so it can be stored in the database and edited from QML:

    {"match": "all" | "any",
     "rules": [{"field": "liked", "op": "is_true"},
               {"field": "last_played", "op": "not_in_last", "value": 60}],
     "sort": "random", "limit": 0}

Only whitelisted fields, operators and sort orders are accepted; values are always bound as SQL parameters.
Text comparisons are case- and accent-insensitive. Radio mode can use the same rules to restrict its picks."""
import json
import time

from . import genres
from .db import fold

# field -> (kind, SQL expression, label)
FIELDS = {
    "title": ("text", "t.title", "Title"),
    "artist": ("text", "t.artist", "Artist"),
    "album": ("text", "t.album", "Album"),
    "album_artist": ("text", "t.album_artist", "Album artist"),
    "genre": ("text", "t.genre", "Genre"),
    "composer": ("text", "t.composer", "Composer"),
    "work": ("text", "t.work", "Work"),
    "music_key": ("text", "t.music_key", "Key"),
    "format": ("text", "t.codec", "Format"),
    "path": ("text", "t.path", "File path"),
    "year": ("number", "t.year", "Year"),
    "track_no": ("number", "t.track_no", "Track number"),
    "disc_no": ("number", "t.disc_no", "Disc number"),
    "duration": ("number", "t.duration / 60.0", "Length (minutes)"),
    "bpm": ("number", "NULLIF(t.bpm, 0)", "Tempo (BPM)"),  # 0 is "not known": it matches no number
    "bitrate": ("number", "t.bitrate / 1000.0", "Bitrate (kb/s)"),
    "plays": ("number", "COALESCE(p.count, 0)", "Play count"),
    "added": ("date", "t.added", "Date added"),
    "last_played": ("date", "p.last", "Last played"),
    "liked": ("bool", "l.path IS NOT NULL", "Liked"),
    "rating": ("number", "COALESCE(r.stars, 0)", "Rating (stars)"),
    "skips": ("number", "COALESCE(s.count, 0)", "Skip count"),
    "lossless": ("bool", "UPPER(COALESCE(t.codec, '')) IN ({lossless})", "Lossless"),
    "sample_rate": ("number", "t.sample_rate / 1000.0", "Sample rate (kHz)"),
    "liked_at": ("date", "l.liked_at", "Date liked"),
}

def _lossless_list():
    from .insights import LOSSLESS

    return ", ".join("'" + c.upper().replace("'", "''") + "'" for c in sorted(LOSSLESS))


FIELDS["lossless"] = (FIELDS["lossless"][0], FIELDS["lossless"][1].format(lossless=_lossless_list()), FIELDS["lossless"][2])

# kind -> {op: label}
OPS = {
    "text": {"contains": "contains", "not_contains": "does not contain", "is": "is", "is_not": "is not",
             "starts_with": "starts with", "ends_with": "ends with", "is_empty": "is empty",
             "is_not_empty": "is not empty"},
    "number": {"eq": "is", "ne": "is not", "gt": "is more than", "lt": "is less than",
               "ge": "is at least", "le": "is at most", "between": "is between"},
    "date": {"in_last": "in the last (days)", "not_in_last": "not in the last (days)", "never": "never"},
    "bool": {"is_true": "is yes", "is_false": "is no"},
}

SORTS = {
    "random": ("Random", "random()"),
    "title": ("Title", "t.s_title, t.s_artist"),
    "artist": ("Artist", "t.s_artist, t.s_album, t.disc_no, t.track_no"),
    "album": ("Album", "t.s_album, t.disc_no, t.track_no"),
    "composer": ("Composer", "t.s_composer = '', t.s_composer, t.work, t.movement_no, t.s_album, t.disc_no, t.track_no"),
    "bpm_asc": ("Slowest first", "t.bpm = 0, t.bpm, t.s_title"),
    "bpm_desc": ("Fastest first", "t.bpm = 0, t.bpm DESC, t.s_title"),
    "year_desc": ("Newest first", "t.year DESC, t.s_album, t.disc_no, t.track_no"),
    "year_asc": ("Oldest first", "t.year, t.s_album, t.disc_no, t.track_no"),
    "added_desc": ("Recently added", "t.added DESC"),
    "plays_desc": ("Most played", "COALESCE(p.count, 0) DESC, t.s_title"),
    "rating_desc": ("Highest rated", "COALESCE(r.stars, 0) DESC, COALESCE(p.count, 0) DESC, t.s_title"),
    "last_played_desc": ("Recently played", "p.last IS NULL, p.last DESC"),
    "last_played_asc": ("Least recently played", "p.last IS NOT NULL, p.last"),
}

FROM = ("FROM tracks t LEFT JOIN plays p ON p.path = t.path LEFT JOIN likes l ON l.path = t.path "
        "LEFT JOIN ratings r ON r.path = t.path LEFT JOIN skips s ON s.path = t.path")
MAX_RULES = 50
MAX_LIMIT = 100_000
DAY_S = 86_400


def _like(text):
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"not a number: {value!r}") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"not a number: {value!r}")
    return number


def normalize(rules):
    """Validated copy of a rule set (dict or JSON text); raises ValueError when it is malformed."""
    if isinstance(rules, str):
        try:
            rules = json.loads(rules) if rules.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid rules: {exc}") from None
    if not isinstance(rules, dict):
        raise ValueError("rules must be an object")
    match = rules.get("match", "all")
    if match not in ("all", "any"):
        raise ValueError(f"unknown match mode: {match!r}")
    items = rules.get("rules", [])
    if not isinstance(items, list) or len(items) > MAX_RULES:
        raise ValueError("rules must be a list of at most 50 rules")
    clean = []
    for rule in items:
        if not isinstance(rule, dict) or rule.get("field") not in FIELDS:
            raise ValueError(f"unknown field in rule: {rule!r}")
        kind = FIELDS[rule["field"]][0]
        op = rule.get("op")
        if op not in OPS[kind] or (op == "never" and rule["field"] != "last_played"):
            raise ValueError(f"operator {op!r} does not apply to {rule['field']}")
        value = rule.get("value")
        if op in ("is_empty", "is_not_empty"):
            value = None
        elif kind == "text":
            value = "" if value is None else str(value)
        elif op == "between":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError("between needs two values")
            value = sorted(_number(v) for v in value)
        elif kind in ("number", "date") and op != "never":
            value = _number(value)
        else:
            value = None
        clean.append({"field": rule["field"], "op": op, "value": value})
    sort = rules.get("sort") or "artist"
    if sort not in SORTS:
        raise ValueError(f"unknown sort: {sort!r}")
    try:
        limit = int(rules.get("limit") or 0)
    except (TypeError, ValueError):
        raise ValueError("limit must be a whole number") from None
    return {"match": match, "rules": clean, "sort": sort, "limit": max(0, min(limit, MAX_LIMIT))}


# Text fields with a folded copy in the table (compare that, not fold() per row: see db.SEARCH_COLS)
FOLDED = {"t.title": "t.s_title", "t.artist": "t.s_artist", "t.album": "t.s_album", "t.album_artist": "t.s_aa",
          "t.genre": "t.s_genre", "t.composer": "t.s_composer"}


def _condition(rule, now):
    kind, expr, _label = FIELDS[rule["field"]]
    op, value = rule["op"], rule["value"]
    if op in ("is_empty", "is_not_empty"):  # blank or only spaces: no such tag
        return f"TRIM(COALESCE({expr}, '')) {'=' if op == 'is_empty' else '!='} ''", []
    if kind == "text":
        folded = fold(value)
        col = FOLDED.get(expr, f"fold({expr})")
        if op == "contains":
            return f"{col} LIKE ? ESCAPE '\\'", [_like(folded)]
        if op == "not_contains":
            return f"{col} NOT LIKE ? ESCAPE '\\'", [_like(folded)]
        if expr == "t.genre" and op in ("is", "is_not"):  # one of an album's genres (it may have several)
            sql, args = genres.prefilter(value, "t.s_genre")  # the cheap test first: few rows reach Python
            return ("" if op == "is" else "NOT ") + f"({sql} AND genre_has(t.genre, ?))", [*args, value]
        if expr == "t.genre" and op == "starts_with":  # any of them, not only the main one
            sql, args = genres.prefilter(value, "t.s_genre")
            return f"({sql} AND genre_starts(t.genre, ?))", [*args, value]
        if expr == "t.composer" and op in ("is", "is_not"):  # one of the composers a song credits
            return ("" if op == "is" else "NOT ") + "(t.s_composer LIKE ? ESCAPE '\\' AND composer_has(t.composer, ?))", \
                [_like(folded), value]
        if op == "is":
            return f"{col} = ?", [folded]
        if op == "is_not":
            return f"{col} != ?", [folded]
        if op == "starts_with":
            return f"{col} LIKE ? ESCAPE '\\'", [_like(folded)[1:]]
        return f"{col} LIKE ? ESCAPE '\\'", [_like(folded)[:-1]]
    if kind == "number":
        if op == "between":
            return f"{expr} BETWEEN ? AND ?", list(value)
        sql_op = {"eq": "=", "ne": "!=", "gt": ">", "lt": "<", "ge": ">=", "le": "<="}[op]
        return f"{expr} {sql_op} ?", [value]
    if kind == "date":
        if op == "never":
            return f"{expr} IS NULL", []
        since = now - value * DAY_S
        if op == "in_last":
            return f"{expr} >= ?", [since]
        if rule["field"] == "last_played":  # never played counts as "not in the last N days"
            return f"({expr} IS NULL OR {expr} < ?)", [since]
        return f"{expr} < ?", [since]  # a song never liked wasn't liked "more than N days ago"
    return (expr if op == "is_true" else f"NOT ({expr})"), []


def compile_where(rules, now=None):
    """(SQL condition, params) selecting the tracks a rule set matches; use with FROM."""
    rules = normalize(rules)
    now = time.time() if now is None else now
    parts = [_condition(rule, now) for rule in rules["rules"]]
    if not parts:
        return "1", []
    joiner = " AND " if rules["match"] == "all" else " OR "
    return "(" + joiner.join(f"({sql})" for sql, _ in parts) + ")", [p for _, params in parts for p in params]


def matching_tracks(db, rules, now=None):
    """Tracks (dicts, with a `plays` count) matching a rule set, sorted and limited as it says."""
    rules = normalize(rules)
    where, params = compile_where(rules, now)
    sql = f"SELECT t.*, COALESCE(p.count, 0) AS plays {FROM} WHERE {where} ORDER BY {SORTS[rules['sort']][1]}"
    if rules["limit"]:
        sql += " LIMIT ?"
        params = [*params, rules["limit"]]
    return db._rows(sql, params)


def count_matching(db, rules, now=None):
    rules = normalize(rules)
    where, params = compile_where(rules, now)
    total = db.conn.execute(f"SELECT COUNT(*) {FROM} WHERE {where}", params).fetchone()[0]
    return min(total, rules["limit"]) if rules["limit"] else total


def _format_number(value):
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def describe(rules):
    """Short human-readable summary, e.g. "Liked is yes and Last played not in the last 60 days"."""
    rules = normalize(rules)
    parts = []
    for rule in rules["rules"]:
        kind, _expr, label = FIELDS[rule["field"]]
        op_label = OPS[kind][rule["op"]]
        value = rule["value"]
        if kind == "date" and rule["op"] != "never":
            op_label = op_label.replace("(days)", f"{_format_number(value)} days")
            parts.append(f"{label} {op_label}")
        elif rule["op"] == "never":
            parts.append("Never played")
        elif kind == "bool" or rule["op"] in ("is_empty", "is_not_empty"):
            parts.append(f"{label} {op_label}")
        elif rule["op"] == "between":
            parts.append(f"{label} {op_label} {_format_number(value[0])} and {_format_number(value[1])}")
        elif kind == "number":
            parts.append(f"{label} {op_label} {_format_number(value)}")
        else:
            parts.append(f'{label} {op_label} "{value}"')
    text = (" and " if rules["match"] == "all" else " or ").join(parts) or "All songs"
    text += f" · {SORTS[rules['sort']][0].lower()}"
    if rules["limit"]:
        text += f" · up to {rules['limit']} songs"
    return text


def schema():
    """Fields, operators and sorts for the QML editor."""
    return {
        "fields": [{"key": k, "label": v[2], "kind": v[0]} for k, v in FIELDS.items()],
        "ops": {kind: [{"key": k, "label": v} for k, v in ops.items()] for kind, ops in OPS.items()},
        "sorts": [{"key": k, "label": v[0]} for k, v in SORTS.items()],
    }
