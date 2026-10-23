"""Search that forgives a typo: when nothing matches what was typed, the words of the library (song, album, artist,
genre and composer names) suggest what was meant ("radiohed" → "radiohead", "beethovan" → "beethoven").

Only words the library actually holds can be suggested, so it never "corrects" toward something you don't have.
A word that starts a library word ("radioh") is left alone: search already finds by word starts."""
import bisect
import re
import unicodedata
from collections import Counter


def fold(s):
    """As db.fold (which this module mustn't import)."""
    s = unicodedata.normalize("NFKD", (s or "").casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


def words(text):
    return re.findall(r"\w+", fold(text))


def distance(a, b, limit):
    """Edit distance between `a` and `b` (a swap of two neighbouring letters counts as one), or limit + 1 once
    it's sure to be more than `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            d = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                d = min(d, prev2[j - 2] + 1)
            cur[j] = d
            best = min(best, d)
        if best > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


class Speller:
    """The library's words, for suggesting a spelling. Built off the GUI thread at each library load."""

    def __init__(self, texts=()):
        counts = Counter()
        for text in texts:
            counts.update(set(words(text)))
        self.counts = counts
        self.sorted = sorted(counts)
        # by first letter and length: a typo rarely hits the first letter, and only words of about the same
        # length can be close, so each suggestion looks at a few hundred words rather than all of them
        self.buckets = {}
        for w in counts:
            if len(w) >= 3 and not w.isdigit():
                self.buckets.setdefault((w[0], len(w)), []).append(w)

    def known(self, word):
        """Whether `word` is a library word, or the start of one."""
        i = bisect.bisect_left(self.sorted, word)
        return i < len(self.sorted) and self.sorted[i].startswith(word)

    def suggest(self, word):
        """The closest library word to `word`, or "" when there's none near enough (one edit for short words,
        two for long ones). Ties go to the word found in more names."""
        if len(word) < 3 or word.isdigit() or self.known(word):
            return ""
        limit = 1 if len(word) <= 5 else 2
        best, best_key = "", None
        for n in range(len(word) - limit, len(word) + limit + 1):
            for w in self.buckets.get((word[0], n), ()):
                d = distance(word, w, limit)
                if d <= limit:
                    key = (d, -self.counts[w], w)
                    if best_key is None or key < best_key:
                        best, best_key = w, key
        return best

    def correct(self, query):
        """`query` with each word that isn't in the library swapped for its suggestion; "" when nothing changed
        (or a word has no suggestion)."""
        typed = words(query)
        if not typed:
            return ""
        out, changed = [], False
        for w in typed:
            if self.known(w):
                out.append(w)
                continue
            s = self.suggest(w)
            if not s:
                return ""
            out.append(s)
            changed = True
        return " ".join(out) if changed else ""
