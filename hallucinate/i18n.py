"""Hallucinate in your language: the translations, and switching between them while it runs.

Every piece of text people read goes through Qt's translation: ``qsTr()`` in the interface and the web remote,
``QCoreApplication.translate(context, text)`` in Python (spelled out, so ``pyside6-lupdate`` finds it). The
catalogues live in ``hallucinate/i18n``: ``hallucinate_<lang>.ts`` is the editable source (Qt Linguist, or any
text editor), ``.qm`` the compiled one the app loads (``scripts/build_translations.py`` makes them, and a test
checks they're current). The web remote gets the same strings as JSON (``web_catalog``), so one translation
covers everything.

Kept in English on purpose: debug info and crash reports (so they can always be read when they're sent in), the
terminal's command words (typed, and part of its look) and the command line's output meant for scripts.
"""
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QLibraryInfo,
    QLocale,
    QObject,
    QSettings,
    QTranslator,
    Signal,
    Slot,
)

HERE = Path(__file__).resolve().parent / "i18n"
log = logging.getLogger(__name__)

# The languages offered, by their own name (a French speaker looks for "Français", not "French"). "pseudo" is for
# development: every string stretched and accented, to find text that isn't translated or doesn't fit.
LANGUAGES = [("en", "English"), ("fr", "Français")]
PSEUDO = "pseudo"


def available():
    """The language codes there is a catalogue for (English is the source text and always there)."""
    have = {p.stem.split("_", 1)[1] for p in HERE.glob("hallucinate_*.qm")}
    return [code for code, _ in LANGUAGES if code == "en" or code in have]


def system_language():
    """The best match among ours for the system's languages, English if none."""
    ours = available()
    for name in QLocale.system().uiLanguages():  # e.g. ["fr-FR", "fr", "en-US"]
        code = name.replace("_", "-").split("-")[0].lower()
        if code in ours:
            return code
    return "en"


class Translations(QObject):
    """The language Hallucinate speaks: "" follows the system. Changing it takes effect at once (the engine
    retranslates every qsTr), and is kept for next time."""

    changed = Signal()

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self._app = app
        self._engine = None
        self._translator = None
        self._settings = QSettings("hallucinate", "hallucinate")
        self._choice = str(self._settings.value("ui/language", "") or "")
        self._apply()

    def setEngine(self, engine):
        self._engine = engine

    @Property(str, notify=changed)
    def choice(self):
        """What was picked in Settings: "" (as the system), or a language code."""
        return self._choice

    @Property(str, notify=changed)
    def language(self):
        """The language in use now."""
        return self._current

    @Property("QVariantList", notify=changed)
    def languages(self):
        """[{code, name}] for Settings, "As the system" first."""
        ours = set(available())
        system = dict(LANGUAGES).get(system_language(), "English")
        follow = QCoreApplication.translate("Language", "As the system (%1)").replace("%1", system)
        return [{"code": "", "name": follow}] + [{"code": c, "name": n} for c, n in LANGUAGES if c in ours]

    @Slot(str)
    def setLanguage(self, code):
        code = str(code or "")
        if code and code != PSEUDO and code not in available():
            return
        self._choice = code
        self._settings.setValue("ui/language", code)
        self._apply()
        if self._engine is not None:
            self._engine.retranslate()
        self.changed.emit()

    def _apply(self):
        code = self._choice or system_language()
        if self._translator is not None:
            self._app.removeTranslator(self._translator)
            self._translator = None
        # (English loads one too: its plurals, "%n song(s)" as "1 song" / "2 songs")
        t = QTranslator(self)
        path = HERE / f"hallucinate_{code}.qm"
        if not t.load(str(path)) and code != "en":
            log.warning("No translation for %s (%s)", code, path)
            code = "en"
            t.load(str(HERE / "hallucinate_en.qm"))
        if not t.isEmpty():
            self._app.installTranslator(t)
            self._translator = t
        # Qt's own words (a dialog's OK and Cancel, a file dialog's buttons) from the catalogues Qt ships with
        for qt in getattr(self, "_qt_translators", []):
            self._app.removeTranslator(qt)
        self._qt_translators = []
        if code not in ("en", PSEUDO):
            folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
            for name in ("qtbase", "qtdeclarative", "qtmultimedia"):
                qt = QTranslator(self)
                if qt.load(f"{name}_{code}", folder):
                    self._app.installTranslator(qt)
                    self._qt_translators.append(qt)
        self._current = code
        # dates, and numbers "as your language writes them", in the language picked (the system's own regional
        # format when following the system, so a Canadian French system keeps its own way of writing them)
        if not hasattr(self, "_system_locale"):
            self._system_locale = QLocale()
        QLocale.setDefault(self._system_locale if not self._choice or code == PSEUDO else QLocale(code))


import functools  # noqa: E402


@functools.lru_cache(maxsize=8)  # the catalogues don't change while it runs
def web_catalog(code):
    """The web remote's strings in `code`, as {English: translated}: read from the same .ts the app uses, the
    "web" context (its app.js and page), "Api" (the errors the control API answers with, in English on the wire) and
    "Equalizer" (the presets' names). Empty for English or an unknown language."""
    if code in ("", "en"):
        return {}
    path = HERE / f"hallucinate_{code}.ts"
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {}
    out = {}
    for ctx in root.iter("context"):
        if ctx.findtext("name") not in ("web", "Api", "Equalizer"):
            continue
        for msg in ctx.iter("message"):
            src = msg.findtext("source") or ""
            tr = msg.find("translation")
            if tr is None or tr.get("type") in ("unfinished", "obsolete", "vanished"):
                continue
            forms = [f.text or "" for f in tr.findall("numerusform")]
            out[src] = forms if forms else (tr.text or "")
    return out


def web_catalog_json(code):
    """What the web remote loads (api/i18n): its words in `code` (English when that isn't one of ours), and the
    languages it can offer, by their own names."""
    ours = available()
    code = code if code in ours else "en"
    return json.dumps({"lang": code, "strings": web_catalog(code), "plural": plural_rule(code),
                       "languages": [{"code": c, "name": n} for c, n in LANGUAGES if c in ours]}, ensure_ascii=False)


def plural_rule(code):
    """Which plural form a count takes, for the web remote (Qt does this itself in the app): "fr" counts 0 and 1
    as one; English only 1."""
    return "fr" if code == "fr" else "en"
