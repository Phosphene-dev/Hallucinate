"""Counts shown in the interface go through Theme.num, so they follow Settings → Appearance → Numbers (12,345 ·
12.345 · 12 345 · 12345). #145 was a page that put raw numbers into its text; this catches the next one before a
tester does. It reads the QML for a count joined straight onto text, the usual way a raw number slips in."""
import pathlib
import re

QML = pathlib.Path(__file__).parent.parent / "hallucinate" / "qml"

# a value whose name says it's a count, joined to a string on either side
_COUNT = r"[A-Za-z_][\w.]*(?:[Cc]ount|[Tt]otal|\.length|[Dd]one|plays|[Ss]een|[Ss]aved|[Aa]dded)"
_JOINED = re.compile(r'"\s*\+\s*(' + _COUNT + r')\b(?!\s*[(\[])|\b(' + _COUNT + r')\s*\+\s*"')
# ... or any value followed by a unit word: `n + " songs"`
_UNIT = re.compile(r'([\w.)\]]+)\s*\+\s*" (?:songs?|albums?|artists?|plays?|tracks?|episodes?|playlists?|genres?|'
                   r'stations?|shows?|copies|files|devices|folders|covers)\b')
# not counts: a file path, a song's own title, a name
ALLOWED = {"spectrograms.saved", "name", "title", "label", "text", "artist", "album"}


def offenders():
    found = []
    for path in sorted(QML.glob("*.qml")):
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in _JOINED.finditer(line):
                expr = m.group(1) or m.group(2)
                if expr not in ALLOWED:
                    found.append(f"{path.name}:{no}: {expr}")
            for m in _UNIT.finditer(line):
                expr = m.group(1)
                tail = expr.split(".")[-1]
                if expr.endswith(")") or expr.startswith('"') or tail in ALLOWED:
                    continue  # num(...) or plural(...), or not a number
                found.append(f"{path.name}:{no}: {expr}")
    return found


def test_counts_in_the_interface_follow_the_numbers_setting():
    assert offenders() == []


def test_the_check_finds_a_raw_count():
    assert _JOINED.search('text: "Play all " + page.tracks.length')
    assert _UNIT.search('text: albumCount + " albums"')
    assert not _JOINED.search('text: "Play all " + Theme.num(page.tracks.length)')
