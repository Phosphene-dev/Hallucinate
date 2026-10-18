"""An album's genres: several of them, the main one first.

They're written to every song of the album as separate values (several GENRE fields in FLAC and Ogg, one
ID3 genre frame holding several, and so on), so other players see the same list. In the library a song's
genres are one text, "IDM; Ambient; Electronic": the first is the main genre, the rest come after it. A tag
written by another program as one text with separators ("Rock/Pop", "Hip-Hop; Rap") counts as the same list.
"""
import re
import unicodedata

SEPARATOR = "; "


def fold(s):
    """Case- and accent-insensitive form (as db.fold, which this module mustn't import)."""
    s = unicodedata.normalize("NFKD", (s or "").casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


# (not commas: "Folk, World, & Country" is one genre)
_SPLIT = re.compile(r"\s*[;/|\x00]\s*")


def split(text):
    """The genres in a tag's text (or a list of texts), main one first, each once."""
    if isinstance(text, (list, tuple)):
        parts = [p for t in text for p in _SPLIT.split(str(t or ""))]
    else:
        parts = _SPLIT.split(text or "")
    out, seen = [], set()
    for part in parts:
        name = " ".join(part.split())
        if name and fold(name) not in seen:
            seen.add(fold(name))
            out.append(name)
    return out


def join(names):
    """Several genres as one text, the main one first."""
    return SEPARATOR.join(split(list(names)))


def main(text):
    """The main genre (the first), or ""."""
    names = split(text)
    return names[0] if names else ""


def has(text, name):
    """Whether `name` is one of the genres in `text` (case and accents aside)."""
    wanted = fold(name or "").strip()
    if not wanted:
        return False
    # the whole text too: a smart playlist saved before as "Genre is Rock/Pop" still finds "Rock/Pop"
    return fold(text or "").strip() == wanted or any(fold(g) == wanted for g in split(text))


def key(name):
    """For matching spellings of one genre: "Hip-Hop", "hip hop" and "HipHop" are the same."""
    return re.sub(r"[\s\-_.&]+", "", fold(name)).replace("and", "")


def starts(text, prefix):
    """Whether one of the genres in `text` begins with `prefix` (case and accents aside)."""
    wanted = fold(prefix or "").strip()
    if not wanted:
        return True
    return fold(text or "").startswith(wanted) or any(fold(g).startswith(wanted) for g in split(text))


def prefilter(name, column="s_genre"):
    """(SQL, params): a cheap test on the folded genre text that every song has() would find passes, so
    the Python genre_has() runs only for the few rows left. Every word of `name` must be in the text."""
    words = fold(name or "").split()
    if not words:
        return "1", []
    like = [f"{column} LIKE ? ESCAPE '\\'"] * len(words)
    return " AND ".join(like), ["%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                                for w in words]
