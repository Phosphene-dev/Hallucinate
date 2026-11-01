"""Translations: every string people read is marked, the catalogues are current, English counts read right, French
loads in the app, the Python side and the web remote (which follows the phone's language)."""
import json
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest
from conftest import wait_for
from test_webremote import remote  # noqa: F401 - the fixture

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_every_string_in_the_interface_is_marked_for_translation(capsys):
    import i18n_lint

    assert i18n_lint.main([]) == 0, capsys.readouterr().out


@pytest.mark.skipif(not (shutil.which("pyside6-lupdate") or shutil.which("lupdate")), reason="needs lupdate")
def test_the_catalogues_are_up_to_date(capsys):
    """Run scripts/build_translations.py after changing text, so translators (and the .qm) see it."""
    import build_translations

    assert build_translations.build(check=True) == 0, capsys.readouterr().out


def test_the_core_reads_english_counts_without_a_catalogue():
    from hallucinate.core.i18n import english_plural, fill

    assert english_plural("%n song(s)", 1) == "1 song"
    assert english_plural("%n song(s)", 0) == "0 songs"
    assert fill("%1 of %2, then %10", "a", "b") == "a of b, then %10"  # (%10 isn't %1 followed by 0)


@pytest.fixture
def translations(qapp):
    from PySide6.QtCore import QSettings

    from hallucinate.i18n import Translations

    t = Translations(qapp)
    yield t
    t.setLanguage("en")
    QSettings().setValue("ui/language", "en")


def test_english_plurals_and_french(translations):
    from hallucinate.core.i18n import translate
    from hallucinate.core.rules import describe

    assert translations.language == "en"
    assert translate("Selection", "%n song(s)", None, 1) == "1 song"
    assert translate("Selection", "%n song(s)", None, 3) == "3 songs"
    assert translate("main", "%n song(s) new to it.", None, 1) == "1 song is new to it."  # an English form "(s)" can't spell

    translations.setLanguage("fr")
    assert translations.language == "fr"
    assert translate("Player", "Playback error") == "Erreur de lecture"
    assert translate("Selection", "%n song(s)", None, 1) == "1 morceau"
    assert translate("Selection", "%n song(s)", None, 0) == "0 morceau"  # French counts 0 as one
    assert translate("Selection", "%n song(s)", None, 2) == "2 morceaux"
    assert describe({"rules": [{"field": "liked", "op": "is_true", "value": True}], "match": "all", "sort": "random",
                     "limit": 0}) == "Aimé est oui · aléatoire"
    names = [entry["name"] for entry in translations.languages]
    assert "Français" in names and "English" in names

    translations.setLanguage("en")
    assert translate("Player", "Playback error") == "Playback error"


def test_every_french_translation_keeps_its_placeholders():
    """A translation that drops %1 or %n shows the wrong thing (or nothing) where the value should be."""
    import re
    import xml.etree.ElementTree as ET

    def marks(text):
        return sorted(set(re.findall(r"%\d|%n", text or "")))

    bad = []
    for msg in ET.parse(ROOT / "hallucinate" / "i18n" / "hallucinate_fr.ts").getroot().iter("message"):
        src, tr = msg.findtext("source"), msg.find("translation")
        if tr is None or tr.get("type") == "unfinished":
            continue
        forms = [f.text for f in tr.findall("numerusform")] or [tr.text]
        for k, form in enumerate(forms):
            want = marks(src)
            got = marks(form)
            if msg.get("numerus") == "yes" and k == 0:
                got = sorted(set(got) | ({"%n"} & set(want)))  # "the one song" may leave the count out
            if got != want:
                bad.append(f"{src!r} → {form!r}")
    assert not bad, "\n".join(bad[:20])


def test_the_web_catalogue():
    from hallucinate.i18n import web_catalog_json

    fr = json.loads(web_catalog_json("fr"))
    assert fr["lang"] == "fr" and fr["plural"] == "fr"
    assert fr["strings"]["Undo"] == "Annuler"
    assert fr["strings"]["Not found"] == "Introuvable"  # the control API's errors (context Api)
    assert fr["strings"]["Flat"] == "Plat"  # the equaliser's presets (context Equalizer)
    assert fr["strings"]["%n song(s)"] == ["%n morceau", "%n morceaux"]
    assert {"code": "fr", "name": "Français"} in fr["languages"]
    for odd in ("", "en", "xx", "../../etc/passwd", "fr\x00"):
        assert json.loads(web_catalog_json(odd))["lang"] == "en"
        assert json.loads(web_catalog_json(odd))["strings"] == {}


def test_the_web_remote_hands_out_its_words_before_pairing(remote):  # noqa: F811
    server, _lib, _player = remote
    server.configure(enabled=True)
    out = {}

    def get(lang):
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/api/i18n?lang={lang}", timeout=5) as r:
            out[lang] = (r.status, r.headers.get("Content-Type"), json.loads(r.read()))

    for lang in ("fr", "..%2F..%2Fsecret", "de,fr,en"):
        t = threading.Thread(target=get, args=(lang,))
        t.start()
        assert wait_for(lambda: not t.is_alive(), timeout=10)
    status, ctype, body = out["fr"]
    assert status == 200 and ctype.startswith("application/json")
    assert body["strings"]["Connect to Hallucinate"] == "Se connecter à Hallucinate"
    assert out["..%2F..%2Fsecret"][2]["lang"] == "en"
    assert out["de,fr,en"][2]["lang"] == "fr"  # the first of the device's languages there's a catalogue for


NODE = shutil.which("node")


def node_playwright():
    return bool(NODE) and subprocess.run([NODE, "-e", "require('playwright')"], capture_output=True).returncode == 0


STEPS = r"""
const { chromium } = require('playwright');
const [url, code] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ locale: 'fr-FR', viewport: { width: 420, height: 860 } });
  const seen = {};
  try {
    await page.goto(url);
    await page.waitForFunction(() => document.documentElement.lang === 'fr');
    seen.pairTitle = await page.textContent('#pair h1');
    seen.pairHtml = await page.innerHTML('#pair p[data-i18n-html]');
    seen.codeLabel = await page.getAttribute('#pairCode', 'aria-label');
    await page.fill('#pairCode', code);
    await page.press('#pairCode', 'Enter');
    await page.waitForSelector('#app:not([hidden])');
    await page.click('button[data-view=settings]');
    seen.settings = await page.textContent('#view-settings h2');
    seen.chips = await page.$$eval('#langChips .chip', (els) => els.map((e) => e.textContent));
    // picking English turns the page English, and stays picked
    await page.click('#langChips .chip[lang=en]');
    await page.waitForFunction(() => document.documentElement.lang === 'en');
    seen.settingsEn = await page.textContent('#view-settings h2');
    seen.saved = await page.evaluate(() => localStorage.getItem('hallucinate.lang'));
  } catch (e) {
    seen.error = String(e);
  }
  await browser.close();
  console.log(JSON.stringify(seen));
})();
"""


@pytest.mark.skipif(not node_playwright(), reason="needs Node with Playwright")
def test_the_web_remote_follows_the_phones_language(remote, tmp_path):  # noqa: F811
    server, _lib, _player = remote
    server.configure(enabled=True)
    script = tmp_path / "lang.js"
    script.write_text(STEPS)
    out = {}

    def go():
        r = subprocess.run([NODE, str(script), f"http://127.0.0.1:{server.port}/", server.new_code()],
                           capture_output=True, text=True, timeout=90)
        out["stdout"], out["stderr"] = r.stdout, r.stderr

    t = threading.Thread(target=go)
    t.start()
    assert wait_for(lambda: not t.is_alive(), timeout=100)
    seen = json.loads(out["stdout"].strip().splitlines()[-1]) if out.get("stdout") else {"error": out.get("stderr")}
    assert "error" not in seen, seen
    assert seen["pairTitle"] == "Se connecter à Hallucinate"
    assert "<b>Paramètres → Télécommande et web</b>" in seen["pairHtml"] and "<code>hallucinate --pair</code>" in seen["pairHtml"]
    assert seen["codeLabel"] == "Code d’association"
    assert seen["settings"] == "Paramètres"
    assert seen["chips"] == ["Automatique", "English", "Français"]
    assert seen["settingsEn"] == "Settings" and seen["saved"] == "en"
