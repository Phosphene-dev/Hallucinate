"""Translating text on the Python side, without making the core need Qt.

    from .i18n import translate, QT_TRANSLATE_NOOP
    translate("SmartRules", "All songs")
    translate("Library", "%n song(s)", None, n)       # a count: Qt picks the plural form

lupdate finds these calls by their names, so they stay spelled out like this (no aliases). With Qt and a
catalogue loaded, Qt translates; without (the command line, tests, a core used on its own) the English source is
used, and "(s)" plurals are worked out here so a count still reads "1 song" / "2 songs".
"""

try:
    from PySide6.QtCore import QCoreApplication
except ImportError:  # pragma: no cover - a core without Qt
    QCoreApplication = None


def QT_TRANSLATE_NOOP(context, text):  # noqa: N802 - the name lupdate looks for
    """Marks text to translate later (where it's shown), and returns it as it is."""
    return text


def english_plural(text, n):
    text = text.replace("%n", str(n))
    return text.replace("(s)", "" if n == 1 else "s")


def translate(context, text, disambiguation=None, n=-1):
    out = text
    if QCoreApplication is not None:
        out = QCoreApplication.translate(context, text, disambiguation, n)
    if n >= 0 and ("(s)" in out or "%n" in out):  # nothing translated it: plain English
        out = english_plural(out, n)
    return out


def fill(text, *values):
    """Puts values in for %1, %2… (highest first, so %1 doesn't eat the start of %10)."""
    for i in range(len(values), 0, -1):
        text = text.replace(f"%{i}", str(values[i - 1]))
    return text


def month_name(month, short=False):
    """A month's name in the language chosen ("September", "septembre"), standing alone as in a title."""
    if QCoreApplication is not None:
        from PySide6.QtCore import QLocale

        kind = QLocale.FormatType.ShortFormat if short else QLocale.FormatType.LongFormat
        name = QLocale().standaloneMonthName(month, kind)
        if name:
            return name[:1].upper() + name[1:]
    import calendar

    return (calendar.month_abbr if short else calendar.month_name)[month]


def format_date(day, pattern):
    """`day` (a date) written with a Qt date pattern ("d MMM yyyy") in the language chosen."""
    if QCoreApplication is not None:
        from PySide6.QtCore import QDate, QLocale

        return QLocale().toString(QDate(day.year, day.month, day.day), pattern)
    return day.strftime(pattern.replace("yyyy", "%Y").replace("MMMM", "%B").replace("MMM", "%b").replace("d", "%-d"))
