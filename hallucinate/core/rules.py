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
from .i18n import QT_TRANSLATE_NOOP, translate

# field -> (kind, SQL expression, label)
FIELDS = {
    "title": ("text", "t.title", QT_TRANSLATE_NOOP("SmartRules", "Title")),
    "artist": ("text", "t.artist", QT_TRANSLATE_NOOP("SmartRules", "Artist")),
    "album": ("text", "t.album", QT_TRANSLATE_NOOP("SmartRules", "Album")),
    "album_artist": ("text", "t.album_artist", QT_TRANSLATE_NOOP("SmartRules", "Album artist")),
    "genre": ("text", "t.genre", QT_TRANSLATE_NOOP("SmartRules", "Genre")),
    "composer": ("text", "t.composer", QT_TRANSLATE_NOOP("SmartRules", "Composer")),
    "work": ("text", "t.work", QT_TRANSLATE_NOOP("SmartRules", "Work")),
    "music_key": ("text", "t.music_key", QT_TRANSLATE_NOOP("SmartRules", "Key")),
    "format": ("text", "t.codec", QT_TRANSLATE_NOOP("SmartRules", "Format")),
    "path": ("text", "t.path", QT_TRANSLATE_NOOP("SmartRules", "File path")),
    "year": ("number", "t.year", QT_TRANSLATE_NOOP("SmartRules", "Year")),
    "track_no": ("number", "t.track_no", QT_TRANSLATE_NOOP("SmartRules", "Track number")),
    "disc_no": ("number", "t.disc_no", QT_TRANSLATE_NOOP("SmartRules", "Disc number")),
    "duration": ("number", "t.duration / 60.0", QT_TRANSLATE_NOOP("SmartRules", "Length (minutes)")),
    "bpm": ("number", "NULLIF(t.bpm, 0)", QT_TRANSLATE_NOOP("SmartRules", "Tempo (BPM)")),  # 0 is "not known": it matches no number
    "bitrate": ("number", "t.bitrate / 1000.0", QT_TRANSLATE_NOOP("SmartRules", "Bitrate (kb/s)")),
    "plays": ("number", "COALESCE(p.count, 0)", QT_TRANSLATE_NOOP("SmartRules", "Play count")),
    "added": ("date", "t.added", QT_TRANSLATE_NOOP("SmartRules", "Date added")),
    "last_played": ("date", "p.last", QT_TRANSLATE_NOOP("SmartRules", "Last played")),
    "liked": ("bool", "l.path IS NOT NULL", QT_TRANSLATE_NOOP("SmartRules", "Liked")),
    "rating": ("number", "COALESCE(r.stars, 0)", QT_TRANSLATE_NOOP("SmartRules", "Rating (stars)")),
    "skips": ("number", "COALESCE(s.count, 0)", QT_TRANSLATE_NOOP("SmartRules", "Skip count")),
    "lossless": ("bool", "UPPER(COALESCE(t.codec, '')) IN ({lossless})", QT_TRANSLATE_NOOP("SmartRules", "Lossless")),
    "sample_rate": ("number", "t.sample_rate / 1000.0", QT_TRANSLATE_NOOP("SmartRules", "Sample rate (kHz)")),
    "bit_depth": ("number", "NULLIF(t.bit_depth, 0)", QT_TRANSLATE_NOOP("SmartRules", "Bit depth")),  # 0: lossy, or not known
    "explicit": ("bool", "t.explicit = 1", QT_TRANSLATE_NOOP("SmartRules", "Explicit")),
    "liked_at": ("date", "l.liked_at", QT_TRANSLATE_NOOP("SmartRules", "Date liked")),
}

def _lossless_list():
    from .insights import LOSSLESS

    return ", ".join("'" + c.upper().replace("'", "''") + "'" for c in sorted(LOSSLESS))


FIELDS["lossless"] = (FIELDS["lossless"][0], FIELDS["lossless"][1].format(lossless=_lossless_list()), FIELDS["lossless"][2])

# kind -> {op: label}
OPS = {
    "text": {"contains": QT_TRANSLATE_NOOP("SmartRules", "contains"), "not_contains": QT_TRANSLATE_NOOP("SmartRules", "does not contain"), "is": QT_TRANSLATE_NOOP("SmartRules", "is"), "is_not": QT_TRANSLATE_NOOP("SmartRules", "is not"),
             "starts_with": QT_TRANSLATE_NOOP("SmartRules", "starts with"), "ends_with": QT_TRANSLATE_NOOP("SmartRules", "ends with"), "is_empty": QT_TRANSLATE_NOOP("SmartRules", "is empty"),
             "is_not_empty": QT_TRANSLATE_NOOP("SmartRules", "is not empty")},
    "number": {"eq": QT_TRANSLATE_NOOP("SmartRules", "is"), "ne": QT_TRANSLATE_NOOP("SmartRules", "is not"), "gt": QT_TRANSLATE_NOOP("SmartRules", "is more than"), "lt": QT_TRANSLATE_NOOP("SmartRules", "is less than"),
               "ge": QT_TRANSLATE_NOOP("SmartRules", "is at least"), "le": QT_TRANSLATE_NOOP("SmartRules", "is at most"), "between": QT_TRANSLATE_NOOP("SmartRules", "is between")},
    "date": {"in_last": QT_TRANSLATE_NOOP("SmartRules", "in the last (days)"), "not_in_last": QT_TRANSLATE_NOOP("SmartRules", "not in the last (days)"), "never": QT_TRANSLATE_NOOP("SmartRules", "never")},
    "bool": {"is_true": QT_TRANSLATE_NOOP("SmartRules", "is yes"), "is_false": QT_TRANSLATE_NOOP("SmartRules", "is no")},
}

SORTS = {
    "random": (QT_TRANSLATE_NOOP("SmartRules", "Random"), "random()"),
    "title": (QT_TRANSLATE_NOOP("SmartRules", "Title"), "t.s_title, t.s_artist"),
    "artist": (QT_TRANSLATE_NOOP("SmartRules", "Artist"), "t.s_artist, t.s_album, t.disc_no, t.track_no"),
    "album": (QT_TRANSLATE_NOOP("SmartRules", "Album"), "t.s_album, t.disc_no, t.track_no"),
    "composer": (QT_TRANSLATE_NOOP("SmartRules", "Composer"), "t.s_composer = '', t.s_composer, t.work, t.movement_no, t.s_album, t.disc_no, t.track_no"),
    "bpm_asc": (QT_TRANSLATE_NOOP("SmartRules", "Slowest first"), "t.bpm = 0, t.bpm, t.s_title"),
    "bpm_desc": (QT_TRANSLATE_NOOP("SmartRules", "Fastest first"), "t.bpm = 0, t.bpm DESC, t.s_title"),
    "year_desc": (QT_TRANSLATE_NOOP("SmartRules", "Newest first"), "t.year DESC, t.s_album, t.disc_no, t.track_no"),
    "year_asc": (QT_TRANSLATE_NOOP("SmartRules", "Oldest first"), "t.year, t.s_album, t.disc_no, t.track_no"),
    "added_desc": (QT_TRANSLATE_NOOP("SmartRules", "Recently added"), "t.added DESC"),
    "plays_desc": (QT_TRANSLATE_NOOP("SmartRules", "Most played"), "COALESCE(p.count, 0) DESC, t.s_title"),
    "rating_desc": (QT_TRANSLATE_NOOP("SmartRules", "Highest rated"), "COALESCE(r.stars, 0) DESC, COALESCE(p.count, 0) DESC, t.s_title"),
    "last_played_desc": (QT_TRANSLATE_NOOP("SmartRules", "Recently played"), "p.last IS NULL, p.last DESC"),
    "last_played_asc": (QT_TRANSLATE_NOOP("SmartRules", "Least recently played"), "p.last IS NOT NULL, p.last"),
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


def _t(text):
    return translate("SmartRules", text)


def describe(rules):
    """Short human-readable summary, e.g. "Liked is yes and Last played not in the last 60 days", in the language
    chosen (the words are translated; the order of field, operator and value is the translator's to change)."""
    rules = normalize(rules)
    parts = []
    for rule in rules["rules"]:
        kind, _expr, label = FIELDS[rule["field"]]
        label = _t(label)
        op_label = _t(OPS[kind][rule["op"]])
        value = rule["value"]
        if kind == "date" and rule["op"] != "never":
            days = int(value) if float(value).is_integer() else value
            if isinstance(days, int):
                text = (translate("SmartRules", "%1 in the last %n day(s)", None, days) if rule["op"] == "in_last"
                        else translate("SmartRules", "%1 not in the last %n day(s)", None, days))
            else:
                text = (_t("%1 in the last %2 days") if rule["op"] == "in_last" else _t("%1 not in the last %2 days"))
                text = text.replace("%2", _format_number(value))
            parts.append(text.replace("%1", label))
        elif rule["op"] == "never":
            parts.append(_t("Never played"))
        elif kind == "bool" or rule["op"] in ("is_empty", "is_not_empty"):
            parts.append(_t("%1 %2").replace("%1", label).replace("%2", op_label))
        elif rule["op"] == "between":
            parts.append(_t("%1 %2 %3 and %4").replace("%1", label).replace("%2", op_label)
                         .replace("%3", _format_number(value[0])).replace("%4", _format_number(value[1])))
        elif kind == "number":
            parts.append(_t("%1 %2 %3").replace("%1", label).replace("%2", op_label).replace("%3", _format_number(value)))
        else:
            parts.append(_t("%1 %2 “%3”").replace("%1", label).replace("%2", op_label).replace("%3", str(value)))
    joiner = _t(" and ") if rules["match"] == "all" else _t(" or ")
    text = joiner.join(parts) or _t("All songs")
    text += " · " + _t(SORTS[rules["sort"]][0]).lower()
    if rules["limit"]:
        text += " · " + translate("SmartRules", "up to %n song(s)", None, rules["limit"])
    return text


def schema():
    """Fields, operators and sorts for the QML editor."""
    return {
        "fields": [{"key": k, "label": _t(v[2]), "kind": v[0]} for k, v in FIELDS.items()],
        "ops": {kind: [{"key": k, "label": _t(v)} for k, v in ops.items()] for kind, ops in OPS.items()},
        "sorts": [{"key": k, "label": _t(v[0])} for k, v in SORTS.items()],
    }
