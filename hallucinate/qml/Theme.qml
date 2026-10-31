pragma Singleton
import QtQuick

QtObject {
    id: root
    // Colors cross-fade on theme and album-accent changes.
    readonly property int duration: 220
    // Pages of cards and text keep to this width, centred, on ultrawide screens (a row of four stats or a bio
    // stretched across 3000 pixels is hard to read); grids of albums and lists of songs use all of it.
    readonly property int contentMax: 1960
    function contentWidth(avail) { return Math.min(avail - 56, contentMax) }
    function contentX(avail) { return Math.max(28, (avail - contentWidth(avail)) / 2) }
    // Values are plain properties (not bindings) so ColorAnimations can cross-fade them.
    Component.onCompleted: {
        if (neon) neonChanged()
        bg = themeManager.bg
        panel = themeManager.panel
        surface = themeManager.surface
        surfaceHi = themeManager.surfaceHi
        border = themeManager.border
        text = themeManager.text
        textDim = themeManager.textDim
        accent = themeManager.accent
        accentHi = themeManager.accentHi
        error = themeManager.error
        onAccent = themeManager.onAccent
    }
    property list<QtObject> fades: [
        ColorAnimation { id: fade_bg; target: root; property: "bg"; duration: root.duration },
        ColorAnimation { id: fade_panel; target: root; property: "panel"; duration: root.duration },
        ColorAnimation { id: fade_surface; target: root; property: "surface"; duration: root.duration },
        ColorAnimation { id: fade_surfaceHi; target: root; property: "surfaceHi"; duration: root.duration },
        ColorAnimation { id: fade_border; target: root; property: "border"; duration: root.duration },
        ColorAnimation { id: fade_text; target: root; property: "text"; duration: root.duration },
        ColorAnimation { id: fade_textDim; target: root; property: "textDim"; duration: root.duration },
        ColorAnimation { id: fade_accent; target: root; property: "accent"; duration: root.duration },
        ColorAnimation { id: fade_accentHi; target: root; property: "accentHi"; duration: root.duration },
        ColorAnimation { id: fade_error; target: root; property: "error"; duration: root.duration },
        ColorAnimation { id: fade_onAccent; target: root; property: "onAccent"; duration: root.duration }
    ]
    property Connections watcher: Connections {
        target: themeManager
        function onThemeChanged() {
            fade_bg.stop(); fade_bg.to = themeManager.bg; fade_bg.start()
            fade_panel.stop(); fade_panel.to = themeManager.panel; fade_panel.start()
            fade_surface.stop(); fade_surface.to = themeManager.surface; fade_surface.start()
            fade_surfaceHi.stop(); fade_surfaceHi.to = themeManager.surfaceHi; fade_surfaceHi.start()
            fade_border.stop(); fade_border.to = themeManager.border; fade_border.start()
            fade_text.stop(); fade_text.to = themeManager.text; fade_text.start()
            fade_textDim.stop(); fade_textDim.to = themeManager.textDim; fade_textDim.start()
            fade_accent.stop(); fade_accent.to = themeManager.accent; fade_accent.start()
            fade_accentHi.stop(); fade_accentHi.to = themeManager.accentHi; fade_accentHi.start()
            fade_error.stop(); fade_error.to = themeManager.error; fade_error.start()
            fade_onAccent.stop(); fade_onAccent.to = themeManager.onAccent; fade_onAccent.start()
        }
    }
    property color bg: themeManager.bg
    property color panel: themeManager.panel
    property color surface: themeManager.surface
    property color surfaceHi: themeManager.surfaceHi
    property color border: themeManager.border
    property color text: themeManager.text
    property color textDim: themeManager.textDim
    property color accent: themeManager.accent
    property color accentHi: themeManager.accentHi
    property color error: themeManager.error
    property color onAccent: themeManager.onAccent
    readonly property string fontFamily: themeManager.fontFamily

    // Display typeface for headings, numbers and the wordmark (Unbounded, SIL OFL; bundled in assets/fonts).
    property FontLoader displayBold: FontLoader { source: Qt.resolvedUrl("../assets/fonts/Unbounded-Bold.ttf") }
    property FontLoader displaySemiBold: FontLoader { source: Qt.resolvedUrl("../assets/fonts/Unbounded-SemiBold.ttf") }
    property FontLoader pixel: FontLoader { source: Qt.resolvedUrl("../assets/fonts/VT323-Regular.ttf") }
    // A neon theme's faces (Chakra Petch and Share Tech Mono, SIL OFL), loaded only once one is chosen
    // (made the first time one is chosen, so other themes never load them)
    property var neonFonts: null
    onNeonChanged: if (neon && !neonFonts) neonFonts = Qt.createQmlObject('import QtQuick; QtObject {'
        + ' property FontLoader tech: FontLoader { source: "' + Qt.resolvedUrl("../assets/fonts/ChakraPetch-SemiBold.ttf") + '" }'
        + ' property FontLoader mono: FontLoader { source: "' + Qt.resolvedUrl("../assets/fonts/ShareTechMono-Regular.ttf") + '" } }', root)
    readonly property string techFamily: neon && neonFonts && neonFonts.tech.status === FontLoader.Ready ? neonFonts.tech.font.family : ""
    // Readouts and the terminal: the neon theme's monospace, else the system's
    readonly property string monoFamily: neon && neonFonts && neonFonts.mono.status === FontLoader.Ready ? neonFonts.mono.font.family : "Monospace"
    // Headings: Unbounded, or in a retro theme the dot-matrix face of an old display
    // the dot-matrix face is small for its size: headings in it are drawn larger
    readonly property real displayScale: retro && pixel.status === FontLoader.Ready ? 1.45 : 1
    readonly property string displayFamily: retro && pixel.status === FontLoader.Ready ? pixel.font.family
        : techFamily !== "" ? techFamily
        : displayBold.status === FontLoader.Ready ? displayBold.font.family : fontFamily

    // Light themes get softer glass and ambience
    readonly property bool reduceMotion: shell.reduceMotion
    readonly property bool light: (0.2126 * bg.r + 0.7152 * bg.g + 0.0722 * bg.b) > 0.5
    // Translucent surfaces that let the ambient backdrop glow through ("frosted glass")
    // Frosted glass; solid panels in a retro theme (nothing was see-through in 1998)
    readonly property color glass: retro ? panel : Qt.rgba(panel.r, panel.g, panel.b, light ? 0.72 : 0.62)
    readonly property color glassStrong: retro ? panel : Qt.rgba(panel.r, panel.g, panel.b, light ? 0.88 : 0.82)
    readonly property color glassHover: Qt.rgba(surfaceHi.r, surfaceHi.g, surfaceHi.b, 0.55)
    readonly property color stroke: Qt.rgba(text.r, text.g, text.b, light ? 0.10 : 0.08)
    readonly property color strokeHi: Qt.rgba(accent.r, accent.g, accent.b, 0.45)
    // Menus, dialogs and tooltips: nearly opaque glass above the page, a soft accent tint for the item under the
    // pointer (text stays the normal text colour, readable in every theme), and the dim laid over the page
    readonly property color popup: retro ? panel : Qt.rgba(panel.r, panel.g, panel.b, light ? 0.97 : 0.94)
    // A chosen row or item (a menu's highlighted entry, the open page): a tint, or in a retro theme the solid
    // accent with its own text colour, as old desktops marked a selection
    readonly property color selectedBg: retro ? accent : hoverTint
    readonly property color selectedText: retro ? onAccent : text
    readonly property color hoverTint: Qt.rgba(accent.r, accent.g, accent.b, light ? 0.14 : 0.22)
    readonly property color scrim: Qt.rgba(bg.r * 0.35, bg.g * 0.35, bg.b * 0.35, light ? 0.38 : 0.58)

    // Colours of the current cover (or of the theme when nothing has art); they melt slowly between tracks.
    readonly property var artColors: themeManager.artColors
    // The backdrop: a theme's own colours (the flag of a pride theme) when it has them, else the cover's
    readonly property var ambient: themeManager.ambientColors
    readonly property color glow0: ambient.length > 0 ? ambient[0] : art0
    readonly property color glow1: ambient.length > 1 ? ambient[1] : art1
    readonly property color glow2: ambient.length > 2 ? ambient[2] : art2
    readonly property var themePalette: themeManager.themePalette
    property color art0: artColors.length > 0 ? artColors[0] : accent
    property color art1: artColors.length > 1 ? artColors[1] : Qt.tint(accent, "#80f2a7d6")
    property color art2: artColors.length > 2 ? artColors[2] : Qt.tint(accent, "#708fb3ff")
    Behavior on art0 { ColorAnimation { duration: 2400; easing.type: Easing.InOutQuad } }
    Behavior on art1 { ColorAnimation { duration: 2800; easing.type: Easing.InOutQuad } }
    Behavior on art2 { ColorAnimation { duration: 3200; easing.type: Easing.InOutQuad } }
    readonly property real fontScale: themeManager.fontScale
    readonly property int radius: themeManager.radius
    readonly property bool retro: themeManager.retro
    // In a theme made after old hardware, or a neon one, corners are as square as the theme says (it's `r`
    // everywhere else)
    function round(r) { return retro || neon ? Math.min(r, radius) : r }

    // A neon-noir theme ("style": "neon"; Afterimage): glowing hairlines, HUD details, scanlines, glitches and a
    // cockpit or terminal Now Playing. Everything it adds is behind these, and loaded only while it's chosen.
    readonly property bool neon: themeManager.neon
    readonly property bool neonLoud: themeManager.neonLoud
    // its second colour (cyan beside magenta): the theme's own second colour, else the accent's other side
    readonly property color neonB: themePalette.length > 1 ? themePalette[1] : Qt.hsva((accent.hsvHue + 0.5) % 1, 0.8, 1, 1)
    readonly property color neonGlow: Qt.rgba(accent.r, accent.g, accent.b, neonLoud ? 0.55 : 0.32)
    // Your choices for it (Settings → Appearance, shown in a neon theme); a loud theme starts with them on
    function neonOption(key) {
        var v = shell.ui["neon" + key]
        return v === undefined || v === "" ? neonLoud : v === "1"
    }
    readonly property bool neonScanlines: neon && !shell.safeMode && neonOption("Scanlines")
    readonly property bool neonGlitch: neon && !reduceMotion && !shell.safeMode && neonOption("Glitch")
    readonly property bool neonGreebles: neon && (shell.ui.neonGreebles === undefined || shell.ui.neonGreebles === "" || shell.ui.neonGreebles === "1")
    readonly property real radiusSmall: Math.max(2, radius * 0.6)
    readonly property real radiusLarge: radius * 2
    readonly property int sidebarWidth: themeManager.sidebarWidth
    readonly property int playerHeight: themeManager.playerHeight

    function fontSize(pixels) { return pixels * fontScale }

    function fmtBytes(bytes) {
        var units = ["B", "KB", "MB", "GB", "TB"], i = 0, v = bytes
        while (v >= 1000 && i < units.length - 1) { v /= 1000; i++ }
        return (v >= 100 || i === 0 ? Math.round(v) : v.toFixed(1)) + " " + units[i]
    }
    function fmtHours(seconds) {
        var h = seconds / 3600
        if (h >= 48) return num(Math.round(h / 24)) + " days"
        return (h >= 10 ? num(Math.round(h)) : num(h, 1)) + " hours"
    }

    // A count as you read numbers (Settings → Appearance → Numbers): 12,345 · 12.345 · 12 345 · 12345, or as
    // the system's language writes them. `decimals`: places after the point (none unless asked).
    readonly property string numberFormat: shell.ui.numberFormat || "locale"
    function num(n, decimals) {
        var v = Number(n)
        if (n === undefined || n === null || n === "" || !isFinite(v)) return n === undefined || n === null ? "" : String(n)
        var places = decimals || 0
        if (numberFormat === "locale") return v.toLocaleString(Qt.locale(), "f", places)
        var group = ({ comma: ",", period: ".", space: "\u202f", none: "" })[numberFormat]
        if (group === undefined) group = ","
        var point = numberFormat === "period" ? "," : "."
        var fixed = Math.abs(v).toFixed(places).split(".")
        var whole = fixed[0].replace(/\B(?=(\d{3})+(?!\d))/g, group)
        return (v < 0 ? "-" : "") + whole + (fixed.length > 1 ? point + fixed[1] : "")
    }

    // For text shown by Qt's own controls (tooltips, menu items, dialog titles), which can't be told to draw plain
    // text: a look-alike for "<" keeps a tag or file name from being read as formatting. Our own Text is plain.
    function plain(s) { return String(s === undefined || s === null ? "" : s).replace(/</g, "\u2039") }

    function fmtTime(ms) {
        var s = Math.max(0, Math.floor(ms / 1000))
        var m = Math.floor(s / 60)
        s = s % 60
        return m + ":" + (s < 10 ? "0" : "") + s
    }
}
