"""File-backed application themes and album-art accent extraction."""
import json
import logging
import math
import os
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSize, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QImageReader

from .core.i18n import fill, translate

logger = logging.getLogger(__name__)
COLOR_KEYS = ("bg", "panel", "surface", "surfaceHi", "border", "text", "textDim", "accent", "error", "onAccent")
BUILTIN_THEME_DIR = Path(__file__).with_name("themes")


DEFAULT_THEME = "Hallucinate"


def art_palette(path, count=3):
    """Up to `count` dominant, reasonably saturated colours of an image, most common first.

    Colours closer than ~40 degrees of hue to an earlier pick are skipped so the palette has some range."""
    reader = QImageReader(path)
    reader.setScaledSize(QSize(32, 32))  # decoders like JPEG downscale while decoding: cheap even for big covers
    image = reader.read()
    if image.isNull():
        return []
    counts = Counter()
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.saturationF() >= 0.28 and 0.18 <= color.valueF() <= 0.98:
                counts[(color.red() // 16, color.green() // 16, color.blue() // 16)] += 1
    picks = []
    for (red, green, blue), _n in counts.most_common():
        color = QColor(min(255, red * 16 + 8), min(255, green * 16 + 8), min(255, blue * 16 + 8))
        hue = color.hsvHueF()
        if all(min(abs(hue - p.hsvHueF()), 1 - abs(hue - p.hsvHueF())) > 0.11 for p in picks):
            picks.append(color)
            if len(picks) == count:
                break
    return picks


def _luminance(color):
    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(color.redF()) + 0.7152 * channel(color.greenF()) + 0.0722 * channel(color.blueF())


def contrast(a, b):
    """WCAG contrast ratio of two colours (1 to 21)."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(color, background, ratio=4.5):
    """`color` lightened (on a dark background) or darkened (on a light one) until text in it reads on
    `background`. Accents taken from covers can be nearly black, which would make accent text vanish."""
    color = QColor(color)
    hue, sat, light, _a = color.getHslF()
    step = 0.04 if _luminance(background) < 0.4 else -0.04
    for _ in range(25):
        if contrast(color, background) >= ratio:
            break
        light = min(1.0, max(0.0, light + step))
        color = QColor.fromHslF(max(hue, 0.0), sat, light)
    return color


def cover_color(path):
    """The colour a cover reads as from across the room, for ordering the colour wall.

    Saturated pixels count more than greys, so a mostly-black sleeve with a red title still reads as red only
    when the red is a real part of it. Returns {"color": "#rrggbb", "hue", "sat", "val"} (0..1) or None."""
    reader = QImageReader(path)
    reader.setScaledSize(QSize(24, 24))
    image = reader.read()
    if image.isNull():
        return None
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    try:
        import numpy as np
    except ImportError:  # numpy is optional; fall back to reading pixels one by one
        np = None
    if np is not None:
        raw = np.frombuffer(image.constBits(), np.uint8, image.sizeInBytes())
        px = raw.reshape(image.height(), image.bytesPerLine())[:, : image.width() * 4].reshape(-1, 4)
        rgb = px[:, 2::-1].astype(np.float32) / 255.0  # BGRA in memory
        hi, lo = rgb.max(axis=1), rgb.min(axis=1)
        sat = np.where(hi > 0, (hi - lo) / np.maximum(hi, 1e-6), 0.0)
        w = 0.15 + sat * hi
        red, green, blue = (rgb * w[:, None]).sum(axis=0) / w.sum()
    else:
        red = green = blue = weight = 0.0
        for y in range(image.height()):
            for x in range(image.width()):
                c = image.pixelColor(x, y)
                w = 0.15 + c.saturationF() * c.valueF()
                red, green, blue, weight = red + c.redF() * w, green + c.greenF() * w, blue + c.blueF() * w, weight + w
        red, green, blue = red / weight, green / weight, blue / weight
    color = QColor.fromRgbF(float(red), float(green), float(blue))
    return {"color": color.name(), "hue": max(0.0, color.hsvHueF()), "sat": color.hsvSaturationF(),
            "val": color.valueF()}


class ThemeManager(QObject):
    themeChanged = Signal()
    themesChanged = Signal()
    artColorsChanged = Signal()

    def __init__(self, config_dir, player=None, parent=None):
        super().__init__(parent)
        self._config_dir = Path(config_dir)
        self._user_theme_dir = self._config_dir / "themes"
        self._preferences_path = self._config_dir / "preferences.json"
        self._themes = {}
        self._current_name = DEFAULT_THEME
        self._album_art_accent = False
        self._album_accent = None
        self._art_colors = []
        self._current_art_url = ""
        self._text_scale = 1.0  # your own text size, times the theme's
        self._accent_override = ""  # a colour of your own for the accent, over any theme ("" = the theme's)
        self._follow_system = False  # switch between a light and a dark theme with the system's setting
        self._light_theme, self._dark_theme = "Light", "Hallucinate"
        self._player = player
        app = QGuiApplication.instance()
        self._base_font_size = app.font().pointSizeF() if app is not None else 10.0
        self._load_themes()
        self._load_preferences()
        self._apply_global_font()
        hints = app.styleHints() if app is not None else None
        if hints is not None and hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self._apply_system_scheme())
        self._apply_system_scheme(save=False)
        if player is not None:
            player.trackChanged.connect(self._on_track_changed)
            self._on_track_changed()

    def _load_themes(self):
        themes = {}
        for directory, source in ((BUILTIN_THEME_DIR, "built-in"), (self._user_theme_dir, "user")):
            if source == "user":
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    logger.warning("Could not create user theme directory %s: %s", directory, exc)
                    continue
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    name, valid = self._validate(data)
                    if not valid:
                        raise ValueError("theme has invalid fields or color values")
                    if name in themes:
                        logger.warning("Ignoring duplicate %s theme %s from %s", source, name, path)
                        continue
                    themes[name] = data
                except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
                    logger.warning("Ignoring invalid %s theme %s: %s", source, path, exc)
        if "Dark" not in themes:
            raise RuntimeError("The built-in Dark theme is missing or invalid")
        self._themes = themes
        if self._current_name not in themes:
            self._current_name = DEFAULT_THEME if DEFAULT_THEME in themes else "Dark"
        self.themesChanged.emit()
        self.themeChanged.emit()

    @staticmethod
    def _validate(data):
        if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not data["name"].strip():
            return "", False
        colors = data.get("colors")
        if not isinstance(colors, dict) or any(not isinstance(colors.get(k), str) or not QColor(colors[k]).isValid() for k in COLOR_KEYS):
            return data["name"].strip(), False
        radius = data.get("radius")
        fonts = data.get("fonts")
        if type(radius) is not int or not 0 <= radius <= 32 or not isinstance(fonts, dict):
            return data["name"].strip(), False
        family = fonts.get("family")
        scale = fonts.get("scale")
        if (not isinstance(family, str) or not family.strip() or isinstance(scale, bool)
                or not isinstance(scale, (int, float)) or not math.isfinite(scale) or not 0.75 <= scale <= 1.5):
            return data["name"].strip(), False
        palette = data.get("palette", [])  # optional: the colours a theme is about, e.g. a pride flag's
        if (not isinstance(palette, list) or len(palette) > 8
                or any(not isinstance(c, str) or not QColor(c).isValid() for c in palette)):
            return data["name"].strip(), False
        return data["name"].strip(), True

    def _load_preferences(self):
        try:
            preferences = json.loads(self._preferences_path.read_text(encoding="utf-8"))
            if not isinstance(preferences, dict):
                raise ValueError("theme preferences must be an object")
            name = preferences.get("theme")
            if isinstance(name, str) and name in self._themes:
                self._current_name = name
            self._album_art_accent = preferences.get("album_art_accent") is True
            accent = preferences.get("accent")
            self._accent_override = accent if isinstance(accent, str) and QColor(accent).isValid() else ""
            self._follow_system = preferences.get("follow_system") is True
            scale = preferences.get("text_scale")
            if isinstance(scale, (int, float)) and not isinstance(scale, bool) and 0.8 <= scale <= 1.5:
                self._text_scale = float(scale)
            for key, attr in (("light_theme", "_light_theme"), ("dark_theme", "_dark_theme")):
                if isinstance(preferences.get(key), str) and preferences[key] in self._themes:
                    setattr(self, attr, preferences[key])
        except FileNotFoundError:
            return
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not load theme preferences from %s: %s", self._preferences_path, exc)

    def _save_preferences(self):
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            temporary = self._preferences_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({
                "theme": self._current_name,
                "album_art_accent": self._album_art_accent,
                "accent": self._accent_override,
                "follow_system": self._follow_system,
                "text_scale": self._text_scale,
                "light_theme": self._light_theme,
                "dark_theme": self._dark_theme,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self._preferences_path)
        except OSError:
            logger.exception("Could not save theme preferences to %s", self._preferences_path)

    def _theme(self):
        return self._themes[self._current_name]

    def _apply_global_font(self):
        app = QGuiApplication.instance()
        if app is not None:
            font = QFont(self.fontFamily)
            font.setPointSizeF(max(1.0, self._base_font_size * self.fontScale))
            app.setFont(font)

    def _on_track_changed(self):
        track = self.sender() or self._player
        if track is None:
            return
        try:
            self._current_art_url = str(track.current.get("artUrl", "") or "")
        except (AttributeError, TypeError):
            self._current_art_url = ""
        self._update_album_accent()

    def _update_album_accent(self):
        url = QUrl(self._current_art_url)
        local_path = url.toLocalFile() if url.isLocalFile() else self._current_art_url
        colors = art_palette(local_path) if local_path else []
        if colors != self._art_colors:
            self._art_colors = colors
            self.artColorsChanged.emit()
        accent = readable_on(colors[0], QColor(self._theme()["colors"]["bg"])) if self._album_art_accent and colors else None
        if accent != self._album_accent:
            self._album_accent = accent
            self.themeChanged.emit()

    @Property("QVariantList", notify=artColorsChanged)
    def artColors(self):
        """Dominant colours of the current track's cover (empty without art); drives the ambient backdrop."""
        return list(self._art_colors)

    @Slot(str, result="QVariantList")
    def imagePalette(self, url):
        """Up to three colours from a picture (a podcast's cover, say), for tinting its page."""
        u = QUrl(url)
        path = u.toLocalFile() if u.isLocalFile() else url
        return [c.name() for c in art_palette(path)] if path and not path.startswith(("http:", "https:")) else []

    @Property("QStringList", notify=themesChanged)
    def availableThemes(self):
        return sorted(self._themes, key=str.casefold)

    @Slot(str, result="QVariantMap")
    def themeColors(self, name):
        """A theme's colours by name (for previews such as the welcome's theme picker); {} if unknown."""
        theme = self._themes.get(name)
        return dict(theme["colors"]) if theme else {}

    @Slot(str, result="QStringList")
    def paletteOf(self, name):
        """A theme's own colours (its flag, for the pride themes) in order; [] for themes without one."""
        theme = self._themes.get(name)
        return list(theme.get("palette", [])) if theme else []

    @Property("QStringList", notify=themeChanged)
    def themePalette(self):
        return self.paletteOf(self._current_name)

    @Property("QVariantList", notify=themeChanged)
    def ambientColors(self):
        """Three colours for the drifting backdrop when a theme brings its own (a flag theme): the first, middle
        and last of its colours that read as colour on the background (black, white and grey stripes don't glow).
        Empty when the theme has none, or when album colours are on, so the backdrop follows the cover."""
        if self._album_art_accent:
            return []
        vivid = [QColor(c) for c in self.themePalette
                 if 0.12 <= QColor(c).lightnessF() <= 0.9 and QColor(c).hslSaturationF() >= 0.2]
        if not vivid:
            return []
        picks = [vivid[0], vivid[len(vivid) // 2], vivid[-1]]
        if len(vivid) == 2:  # the deeper colour takes two of the three glows, so a bright one doesn't flood it
            deep, bright = sorted(vivid, key=_luminance)
            picks = [deep, bright, deep]
        toned = []
        for color in picks:  # very bright flag colours (yellow, pastel pink) glow a little softer
            for _ in range(12):
                if _luminance(color) <= 0.35:
                    break
                color = color.darker(108)
            toned.append(color)
        return toned

    @Property(str, notify=themeChanged)
    def currentTheme(self):
        return self._current_name

    @Property(bool, notify=themeChanged)
    def albumArtAccent(self):
        return self._album_art_accent

    @Property(str, notify=themeChanged)
    def fontFamily(self):
        return self._theme()["fonts"]["family"]

    @Property(float, notify=themeChanged)
    def fontScale(self):
        return float(self._theme()["fonts"]["scale"]) * self._text_scale

    TEXT_SIZES = (0.9, 1.0, 1.1, 1.25, 1.4)

    @Property(float, notify=themeChanged)
    def textScale(self):
        """Your own text size (1.0 = as the theme has it), for every theme."""
        return self._text_scale

    @Slot(float)
    def setTextScale(self, scale):
        scale = min(self.TEXT_SIZES, key=lambda s: abs(s - float(scale or 1.0)))
        if scale != self._text_scale:
            self._text_scale = scale
            self._save_preferences()
            self._apply_global_font()
            self.themeChanged.emit()

    @Property(int, notify=themeChanged)
    def radius(self):
        return self._theme()["radius"]

    @Property(bool, notify=themeChanged)
    def retro(self):
        """A theme made after old hardware ("style": "retro"): Now Playing opens as the Deck unless you've chosen."""
        return self._theme().get("style") == "retro"

    @Property(bool, notify=themeChanged)
    def neon(self):
        """A neon-noir theme ("style": "neon"): its HUD frame, scanlines and the cockpit/terminal Now Playing are
        loaded only while one is chosen, so they cost nothing in any other theme."""
        return self._theme().get("style") == "neon"

    @Property(bool, notify=themeChanged)
    def neonLoud(self):
        """A neon theme turned all the way up ("loud": true): glow, scanlines and glitches on by default. A quiet one
        keeps the look with the effects left off (each can still be turned on in Settings)."""
        theme = self._theme()
        return theme.get("style") == "neon" and theme.get("loud") is True

    @Property(str, notify=themesChanged)
    def userThemeDirectory(self):
        return str(self._user_theme_dir)

    @Property(int, notify=themeChanged)
    def sidebarWidth(self):
        return 210

    @Property(int, notify=themeChanged)
    def playerHeight(self):
        return 92

    def _own_accent(self):
        """The accent that replaces the theme's, if any: the album cover's, else the one you picked (made
        readable on the theme's background)."""
        if self._album_accent is not None:
            return self._album_accent
        if self._accent_override:
            return readable_on(self._accent_override, QColor(self._theme()["colors"]["bg"]))
        return None

    def _color(self, name):
        own = self._own_accent()
        if name == "accent" and own is not None:
            return own
        if name == "accentHi":
            return self._color("accent").lighter(115)
        if name == "onAccent" and own is not None:
            luminance = 0.2126 * own.redF() + 0.7152 * own.greenF() + 0.0722 * own.blueF()
            return QColor("#101014" if luminance > 0.48 else "#ffffff")
        return QColor(self._theme()["colors"][name])

    def _color_property(name, changed):
        return Property(QColor, lambda self: self._color(name), notify=changed)

    bg = _color_property("bg", themeChanged)
    panel = _color_property("panel", themeChanged)
    surface = _color_property("surface", themeChanged)
    surfaceHi = _color_property("surfaceHi", themeChanged)
    border = _color_property("border", themeChanged)
    text = _color_property("text", themeChanged)
    textDim = _color_property("textDim", themeChanged)
    accent = _color_property("accent", themeChanged)
    accentHi = _color_property("accentHi", themeChanged)
    error = _color_property("error", themeChanged)
    onAccent = _color_property("onAccent", themeChanged)

    @Slot(str, result=bool)
    def selectTheme(self, name):
        if name not in self._themes or name == self._current_name:
            return name == self._current_name
        self._current_name = name
        self._album_accent = None
        self._update_album_accent()
        self._apply_global_font()
        self._save_preferences()
        self.themeChanged.emit()
        return True

    @Slot(bool)
    def setAlbumArtAccent(self, enabled):
        enabled = bool(enabled)
        if enabled == self._album_art_accent:
            return
        self._album_art_accent = enabled
        self._update_album_accent()
        self._save_preferences()
        self.themeChanged.emit()

    # --- your own touches ---------------------------------------------------------------------------------
    @Property(str, notify=themeChanged)
    def accentOverride(self):
        """The accent colour you picked ("#rrggbb"), or "" for the theme's own."""
        return self._accent_override

    @Slot(str)
    def setAccentOverride(self, color):
        color = color.strip() if isinstance(color, str) else ""
        if color and not QColor(color).isValid():
            return
        color = QColor(color).name() if color else ""
        if color != self._accent_override:
            self._accent_override = color
            self._save_preferences()
            self.themeChanged.emit()

    @Property(bool, notify=themeChanged)
    def followSystem(self):
        """Use lightTheme while the system is in light mode and darkTheme while it's dark."""
        return self._follow_system

    @Property(str, notify=themeChanged)
    def lightTheme(self):
        return self._light_theme

    @Property(str, notify=themeChanged)
    def darkTheme(self):
        return self._dark_theme

    @Slot(bool)
    def setFollowSystem(self, on):
        self._follow_system = bool(on)
        self._save_preferences()
        self._apply_system_scheme()
        self.themeChanged.emit()

    @Slot(str, str)
    def setSystemThemes(self, light, dark):
        if light in self._themes:
            self._light_theme = light
        if dark in self._themes:
            self._dark_theme = dark
        self._save_preferences()
        self._apply_system_scheme()
        self.themeChanged.emit()

    def system_is_dark(self):
        app = QGuiApplication.instance()
        hints = app.styleHints() if app is not None else None
        if hints is None or not hasattr(hints, "colorScheme"):
            return None
        from PySide6.QtCore import Qt

        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
        return None  # the system doesn't say

    def _apply_system_scheme(self, save=True):
        if not self._follow_system:
            return
        dark = self.system_is_dark()
        if dark is None:
            return
        name = self._dark_theme if dark else self._light_theme
        if name in self._themes and name != self._current_name:
            if save:
                self.selectTheme(name)
            else:
                self._current_name = name

    @Slot(str, "QVariantMap", result=str)
    def saveCustomTheme(self, name, colors):
        """Save a theme of your own (in the user theme folder), built on the current one with `colors`
        changed, and switch to it. Returns "" or what went wrong."""
        name = (name or "").strip()
        if not name:
            return translate("Themes", "Give the theme a name")
        builtin = {p.stem for p in BUILTIN_THEME_DIR.glob("*.json")}
        base = json.loads(json.dumps(self._theme()))
        base["name"] = name
        for key, value in (colors or {}).items():
            if key in COLOR_KEYS and QColor(str(value)).isValid():
                base["colors"][key] = QColor(str(value)).name()
        _, valid = self._validate(base)
        if not valid:
            return translate("Themes", "Those colours don't make a valid theme")
        slug = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "my-theme"
        if slug in builtin or (name in self._themes and self._is_builtin(name)):
            return fill(translate("Themes", "“%1” is a built-in theme's name; pick another"), name)
        try:
            self._user_theme_dir.mkdir(parents=True, exist_ok=True)
            from .core.atomic import write_text

            write_text(self._user_theme_dir / f"{slug}.json", json.dumps(base, indent=2) + "\n")
        except OSError as exc:
            return fill(translate("Themes", "Couldn't save the theme: %1"), exc.strerror or exc)
        self._load_themes()
        self.selectTheme(name)
        return ""

    def _is_builtin(self, name):
        for path in BUILTIN_THEME_DIR.glob("*.json"):
            try:
                if json.loads(path.read_text(encoding="utf-8")).get("name") == name:
                    return True
            except (OSError, ValueError):
                continue
        return False

    @Slot()
    def reloadThemes(self):
        previous = self._current_name
        self._load_themes()
        self._apply_global_font()
        if previous != self._current_name:
            self._save_preferences()
