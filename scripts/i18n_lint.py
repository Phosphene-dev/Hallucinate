"""Find text people read in the interface that isn't marked for translation.

    python scripts/i18n_lint.py [files...]      # list them (file:line: "text"), exit 1 if any

A string literal counts as text people read when it looks like words (a space, or a capital letter followed by a
lower-case one) and isn't a key, a name, a path or a comparison. Lines that are on purpose not translated carry a
trailing `// i18n: keep` (an English command word, say).
"""
import re
import sys
from pathlib import Path

QML = Path(__file__).resolve().parent.parent / "hallucinate" / "qml"

_STRING = re.compile(r'"((?:\\.|[^"\\])*)"')
# where a string is a key, a name or a value compared against, not something shown
_NOT_SHOWN_BEFORE = re.compile(
    r"(objectName|source|icon|name|key|family|fontFamily|mode|kind|role|state|section|sequence|sequences|"
    r"easing\.type|color|Theme\.\w+|shell\.ui\w*|uiValue|setUiValue|setFeature|feature|go|navigate|openSettings|"
    r"emit|Qt\.formatDate|formatDate|formatTime|toLocaleString|indexOf|startsWith|endsWith|split|replace|"
    r"call|runCommand|hasOwnProperty|property|typeof|import|setProperty|findChild|"
    r"===|!==|==|!=|[\w\])]\[|case)\s*[:(=]?\s*$")
# words: two letters together, and a space or a capital or an ellipsis beside them (" plays", "Play", "Edit…")
_LOOKS_LIKE_WORDS = re.compile(r"(?=.*[A-Za-zÀ-ÿ]{2})(?=.*(\s|[A-Z]|…))")
# a count's plural chosen in code (n === 1 ? "song" : "songs"): Qt's plural forms instead, qsTr("%n song(s)", "", n)
_PLURAL = re.compile(r"""===?\s*1\s*\?\s*["'][^"']*["']\s*:\s*["']""")


def offenders(path):
    out = []
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("//")[0] if "i18n: keep" not in line else ""
        if not code.strip() or code.strip().startswith(("import ", "*", "/*")):
            continue
        for m in _STRING.finditer(code):
            text = m.group(1)
            if not _LOOKS_LIKE_WORDS.search(text) or text.startswith(("image://", "file:", "qrc:", "http", "#")):
                continue
            before = code[: m.start()]
            if re.search(r"\bqsTr\s*\(\s*$", before) or re.search(r"\bqsTr\s*\([^()]*$", before):
                continue  # (inside a qsTr call: its text, or its plural's empty comment)
            if _NOT_SHOWN_BEFORE.search(before.rstrip()):
                continue
            out.append(f"{path.name}:{no}: \"{text}\"")
        if _PLURAL.search(code):
            out.append(f"{path.name}:{no}: plural chosen in code")
    return out


def main(argv):
    files = [Path(a) for a in argv] or sorted(QML.glob("*.qml"))
    found = [o for f in files for o in offenders(f)]
    print("\n".join(found))
    print(f"{len(found)} untranslated", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
