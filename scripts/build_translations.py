"""Bring the translation catalogues up to date and compile them.

    python scripts/build_translations.py            # extract new strings into every .ts, then compile all .qm
    python scripts/build_translations.py --check    # exit 1 if a .ts is missing strings or a .qm is stale

Strings come from the interface (qsTr in hallucinate/qml), the Python side (QCoreApplication.translate) and the
web remote (qsTr in hallucinate/web/app.js), all into one hallucinate_<lang>.ts per language. English has a
catalogue too, only for plurals ("%n song(s)" → "1 song" / "2 songs"). The pseudo-language is made here from the
English source: every string stretched and accented, to spot text that isn't translated or doesn't fit.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "hallucinate"
OUT = PKG / "i18n"
LANGS = ["en", "fr"]
PSEUDO = "pseudo"


# The web remote's app.js marks its text with t("…") and tn("… %n …", n). lupdate can't read modern JavaScript
# (async functions), so those strings are copied into a plain file of qsTr calls named web.js: context "web".
_WEB_T = re.compile(r"""\bt(n?)\(\s*(["'`])((?:\\.|(?!\2).)*)\2""")


def web_strings(tmp):
    text = (PKG / "web" / "app.js").read_text(encoding="utf-8")
    lines = []
    for m in _WEB_T.finditer(text):
        plural, quote, body = m.group(1), m.group(2), m.group(3)
        if quote == "`":
            body = body.replace('"', '\\"')
            quote = '"'
        tail = ', "", 0' if plural else ""
        lines.append(f"qsTr({quote}{body}{quote}{tail});")
    out = Path(tmp) / "web.js"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


_TMP = None


def sources():
    files = sorted(PKG.glob("qml/*.qml")) + sorted(PKG.glob("qml/*.js"))
    files += sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)
    if _TMP is not None:
        files.append(web_strings(_TMP))
    return [str(p) for p in files]


def tool(name):
    found = shutil.which(f"pyside6-{name}") or shutil.which(name)
    if not found:
        sys.exit(f"pyside6-{name} not found (it comes with PySide6)")
    return found


def lupdate(ts, extra=()):
    subprocess.run([tool("lupdate"), "-silent", "-locations", "none", "-no-obsolete", *extra, *sources(),
                    "-ts", str(ts)], check=True)


PSEUDO_MAP = str.maketrans("aceinosuyACEINOSUY", "àçéîñôşüýÀÇÉÎÑÔŞÜÝ")


def pseudo_text(s):
    """Accented and about 40% longer, keeping %1/%n, {…} and markup intact."""
    out, i = [], 0
    while i < len(s):
        if s[i] == "%" and i + 1 < len(s) and (s[i + 1].isdigit() or s[i + 1] in "nL"):
            j = i + 1
            while j < len(s) and (s[j].isdigit() or s[j] in "nL"):
                j += 1
            out.append(s[i:j])
            i = j
        else:
            out.append(s[i].translate(PSEUDO_MAP))
            i += 1
    body = "".join(out)
    return "[" + body + " " + "~" * max(2, len(s) * 2 // 5) + "]"


def make_pseudo(template, target):
    tree = ET.parse(template)
    for msg in tree.getroot().iter("message"):
        src = msg.findtext("source") or ""
        tr = msg.find("translation")
        if tr is None:
            tr = ET.SubElement(msg, "translation")
        tr.attrib.pop("type", None)
        if msg.get("numerus") == "yes":
            for f in list(tr):
                tr.remove(f)
            tr.text = None
            for _ in range(2):
                ET.SubElement(tr, "numerusform").text = pseudo_text(src)
        else:
            tr.text = pseudo_text(src)
    tree.getroot().set("language", "en")
    tree.write(target, encoding="utf-8", xml_declaration=True)


def lrelease(ts, qm):
    subprocess.run([tool("lrelease"), "-silent", "-removeidentical" if ts.stem.endswith("_en") else "-nounfinished",
                    str(ts), "-qm", str(qm)], check=True)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else ""


def build(check=False):
    OUT.mkdir(exist_ok=True)
    stale = []
    global _TMP
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _TMP = tmp
        for lang in LANGS:
            ts = OUT / f"hallucinate_{lang}.ts"
            work = tmp / ts.name
            if ts.exists():
                shutil.copy(ts, work)
            lupdate(work, ["-target-language", lang] + (["-pluralonly"] if lang == "en" else []))
            if check:
                if digest(work) != digest(ts):
                    stale.append(ts.name)
            else:
                shutil.copy(work, ts)
        template = tmp / "template.ts"
        lupdate(template)
        make_pseudo(template, tmp / f"hallucinate_{PSEUDO}.ts")
        for ts in [OUT / f"hallucinate_{lang}.ts" for lang in LANGS] + [tmp / f"hallucinate_{PSEUDO}.ts"]:
            qm = OUT / (ts.stem + ".qm")
            built = tmp / (ts.stem + ".built.qm")
            lrelease(ts if not check or ts.parent == tmp else ts, built)
            if check:
                if digest(built) != digest(qm):
                    stale.append(qm.name)
            else:
                shutil.copy(built, qm)
    if stale:
        print("Out of date (run scripts/build_translations.py): " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    sys.exit(build(ap.parse_args().check))
