# Translating Hallucinate

Hallucinate speaks English and French, and can speak your language too. You don't need to know how to program:
a translation is one text file, and you can work on it in Qt Linguist (a free editor made for this) or in any text
editor.

Everything goes in one file per language: the desktop app, its messages, and the web remote on your phone.

## What you need

- A copy of Hallucinate's source: `git clone https://github.com/Phosphene-dev/Hallucinate`. You can also download
  just the file you need from GitHub (see below).
- Python 3.10 or newer with PySide6 (`pip install PySide6`). This gives you `pyside6-linguist`, the editor, and
  the tools that build translations.

## Starting a new language

1. Add the language to the list in `hallucinate/i18n.py`. Use its code and its name *in that language*, because
   people look for "Deutsch", not "German":

   ```python
   LANGUAGES = [("en", "English"), ("fr", "Français"), ("de", "Deutsch")]
   ```

   Also add the code to `LANGS` in `scripts/build_translations.py`, and its plural rule to `plural_rule()` in
   `hallucinate/i18n.py` if it counts differently from English or French (see "Counts" below).
2. Run `python scripts/build_translations.py`. This creates `hallucinate/i18n/hallucinate_de.ts` with every string,
   all marked as not translated yet.
3. Translate (see below), then run `python scripts/build_translations.py` again to build the `.qm` file the app
   loads.
4. Try it: Settings → Appearance → Language. The app changes at once, with no restart.

## Translating

Open the file in the editor:

```sh
pyside6-linguist hallucinate/i18n/hallucinate_de.ts
```

Strings are grouped by where they appear. The group's name is the screen or file they come from, for example
`SettingsPage`, `NowPlayingView`, `web` (the phone remote) or `Health` (Library health). Mark each string done (the
tick, or Ctrl+Enter) when you're happy with it. Strings that aren't marked done aren't used: people see the English
instead.

If you'd rather use a text editor, each string looks like this. Put your text in `<translation>` and delete
`type="unfinished"`:

```xml
<message>
    <source>Add to queue</source>
    <translation type="unfinished"></translation>
</message>
```

### Things to keep as they are

- **Placeholders**: `%1`, `%2`… are filled in by the app (a song's name, a number). Keep each one, in whatever
  place your sentence needs it: `“%1” will play next` can become `« %1 » sera lu ensuite`. A test checks that none
  go missing.
- **`%n`** is a count, in strings with a plural (see below).
- **Markup**: in the few strings that have `<b>…</b>` or `<code>…</code>`, keep the tags around the matching words.
- **Terminal commands**: in the Afterimage theme's terminal, the commands people type (`play`, `queue rm <n>`,
  `help`) stay in English. They're shown in English in the help, and translators only see the explanations.
- **Padded labels**: some terminal and readout lines line up in columns with spaces (`  title    : %1`). Keep them
  lined up in yours: count the characters.
- **Date and time formats**: strings like `dddd d MMMM yyyy` (marked "date format (Qt)") are patterns, not words.
  Reorder them for your language (`dddd, d. MMMM yyyy` in German); month and day names are filled in by the
  language itself. The format characters are listed in
  [Qt's documentation](https://doc.qt.io/qt-6/qlocale.html#toString-2).
- **Names**: Hallucinate, Last.fm, ListenBrainz, MusicBrainz, Discogs, Jellyfin and the like stay as they are.

The grey notes some strings carry ("an album's title in quotes", "under a big number") say where the text appears.
Keep sentences natural rather than word for word: Hallucinate talks to people plainly, and so should yours.

### Counts

A string with `%n` changes with the number: `%n song(s)` becomes "1 song" and "2 songs" in English. In the editor
these have a box for each form your language has: French uses the first for 0 and 1 and the second for 2 and up;
some languages have three or more forms, and the editor shows the right number of boxes.

The web remote works out which form to use itself, from `plural_rule()` in `hallucinate/i18n.py`. If your
language has more than two forms, it also needs a rule in `pluralForm()` in `hallucinate/web/app.js`, next to the
French one. Ask in an issue if you'd like a hand with it.

## Checking your work

- **Try every page.** Settings → Appearance → Language switches straight away. Long words are the usual problem: if
  something is cut off or spills out of its card, find a shorter way to say it.
- **The phone remote** picks the phone's language by itself, or you can pick one in its Settings.
- **Tests**: `python -m pytest tests/test_i18n.py` checks placeholders. `tests/test_screens.py -k another_language`
  goes through every page in French and in the pseudo-language and looks for text spilling out.
- **The pseudo-language** (`pseudo`, for development) stretches every string by about 40% and accents it. Text that
  shows up plain is text the app forgot to translate: please report it.

## Sending it in

Open a pull request with your `.ts` and `.qm` files and the two small changes from "Starting a new language". If
you'd rather not use git, attach the `.ts` file to an issue and it'll be added for you.

When the app's text changes, new and changed strings show up in your file as unfinished the next time someone runs
`scripts/build_translations.py`. Strings that no longer exist are removed.

## For developers

- In QML, wrap text in `qsTr("…")`. Put values in with `.arg()`, never by joining pieces:
  `qsTr("%1 will play next").arg(title)`, not `title + " will play next"`. Other languages put words in other
  orders.
- For counts, use `Theme.counted(qsTr("%n song(s)", "", n), n)`. Qt picks the plural form, and `counted` writes the
  number the way Settings → Numbers says.
- Write dates with `Theme.date(d, "long")` and hours with `Theme.hourOfDay(h)`, never a fixed pattern.
- In Python, use `translate("Context", "…")` from `hallucinate.core.i18n`, spelled out so lupdate finds it, and
  `fill()` for `%1`. Text kept in a constant and shown later uses `QT_TRANSLATE_NOOP("Context", "…")`, translated
  where it's shown.
- In the web remote, use `t("…")`, `tn("… %n …(s)", n)` and `fill()`. Words in `index.html` get `data-i18n` (plain
  text) or `data-i18n-html` (with `<b>`/`<code>`). `aria-label`, `placeholder` and `title` are picked up by
  themselves.
- Never translate a settings key, a file name, an `objectName` or anything compared against: only what people read.
  `scripts/i18n_lint.py` flags text that isn't marked. A line ending in `// i18n: keep` is left alone on purpose (a
  unit on a display, a date pattern built elsewhere).
- Kept in English on purpose: debug info and crash reports (so they can always be read when they're sent in), the
  command line's output (scripts read it), and the terminal's command words.
- After changing text, run `python scripts/build_translations.py`. A test fails until the catalogues are current.
