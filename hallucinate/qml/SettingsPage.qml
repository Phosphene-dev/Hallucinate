import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "."

Item {
    id: page
    objectName: "settings"
    property string query: ""
    readonly property var sectionIds: ["appearance", "features", "podcasts", "playback", "sound", "library", "servers", "casting", "remote", "sharing", "scrobbling", "desktop", "about"]
    readonly property var sectionTitles: [qsTr("Appearance"), qsTr("Features"), qsTr("Podcasts"), qsTr("Playback"), qsTr("Sound"), qsTr("Library"), qsTr("Music servers"), qsTr("Casting"), qsTr("Remote & web"), qsTr("Online & privacy"), qsTr("Scrobbling & sharing"), qsTr("Desktop"), qsTr("About")]

    function sectionItem(i) { return [sec_appearance, sec_features, sec_podcasts, sec_playback, sec_sound, sec_library, sec_servers, sec_casting, sec_remote, sec_sharing, sec_scrobbling, sec_desktop, sec_about][i] }
    function jumpToId(id) { var i = sectionIds.indexOf(id); if (i >= 0 && sectionItem(i).visible) jumpTo(i) }
    function jumpToSidebar() {
        jumpTo(1)
        sidebarGroup.open = true
        var y = sidebarOrderBox.mapToItem(flick.contentItem, 0, 0).y - 20
        flick.contentY = Math.max(0, Math.min(y, flick.contentHeight - flick.height))
    }
    // the section at the top of the view, lit in the jump list. The last sections are too short to reach the top
    // (issue 99): one jumped to stays lit, and at the very end the last section is.
    property int jumped: -1
    property bool jumping: false
    readonly property int currentSection: {
        if (jumped >= 0) return jumped
        var y = flick.contentY + 40, at = 0, last = 0
        for (var i = 0; i < sectionIds.length; i++) {
            var s = sectionItem(i)
            if (!s || !s.visible) continue
            last = i
            if (s.y <= y) at = i
        }
        return flick.contentHeight > flick.height && flick.contentY >= flick.contentHeight - flick.height - 2 ? last : at
    }
    function jumpTo(i) {
        page.query = ""
        search.text = ""
        jumping = true
        flick.contentY = Math.max(0, Math.min(sectionItem(i).y, flick.contentHeight - flick.height))
        jumping = false
        jumped = i
    }
    Connections { target: flick; function onContentYChanged() { if (!page.jumping) page.jumped = -1 } }
    function focusSearch() { search.forceActiveFocus(); search.selectAll() }
    // Enter in the search: scroll to the first matching setting (its row is marked; see SettingsSection)
    function showFirstMatch() {
        for (var i = 0; i < sectionIds.length; i++) {
            var s = sectionItem(i)
            if (!s || !s.visible) continue
            var row = s.firstMatch()
            var y = (row || s).mapToItem(flick.contentItem, 0, 0).y - 24
            flick.contentY = Math.max(0, Math.min(y, flick.contentHeight - flick.height))
            return
        }
    }

    // Search and jump to a section; the page below scrolls
    Column {
        id: header
        x: Theme.contentX(page.width); y: 20
        width: Theme.contentWidth(page.width)
        spacing: 12
        Row {
            width: parent.width
            spacing: 16
            Text { id: pageTitle; text: qsTr("Settings"); color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale; font.weight: Font.Bold; textFormat: Text.PlainText }
            TextField {
                id: search
                objectName: "settingsSearch"
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(340, parent.width - pageTitle.width - 16)
                height: 36
                placeholderText: qsTr("Search settings   (Ctrl+F)")
                color: Theme.text
                placeholderTextColor: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(14)
                leftPadding: 14
                selectByMouse: true
                background: Rectangle { radius: Theme.round(height / 2); color: Theme.surface; border.color: search.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                onTextChanged: { page.query = text; flick.contentY = 0 }
                Keys.onEscapePressed: text = ""
                Keys.onReturnPressed: page.showFirstMatch()
                Keys.onEnterPressed: page.showFirstMatch()
            }
        }
        Flow {
            width: parent.width
            spacing: 8
            visible: page.query.length === 0
            Repeater {
                model: page.sectionTitles
                Chip {
                    required property string modelData
                    required property int index
                    // (by the section's id: its title is in your language)
                    visible: (page.sectionIds[index] !== "podcasts" || shell.features.podcasts !== false)
                             && (page.sectionIds[index] !== "servers" || shell.features.servers === true)
                             && (page.sectionIds[index] !== "casting" || shell.features.casting !== false)
                    text: modelData
                    selected: index === page.currentSection
                    onClicked: page.jumpTo(index)
                }
            }
        }
        Text {
            textFormat: Text.PlainText
            visible: page.query.length > 0
            text: (noMatches ? qsTr("No settings match “%1”") : qsTr("Showing settings that match “%1”")).arg(page.query)
            // (a section hidden because its feature is off doesn't count, even if it matches)
            readonly property bool noMatches: !(sec_appearance.visible || sec_features.visible || sec_podcasts.visible || sec_playback.visible || sec_sound.visible || sec_library.visible || sec_servers.visible || sec_casting.visible || sec_remote.visible || sec_sharing.visible || sec_scrobbling.visible || sec_desktop.visible || sec_about.visible)
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
        }
    }

    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: flick
        anchors { left: parent.left; right: parent.right; top: header.bottom; topMargin: 14; bottom: parent.bottom }
        contentWidth: width
        contentHeight: settingsColumn.implicitHeight + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

    Column {
        id: settingsColumn
        x: Theme.contentX(page.width)
        width: Theme.contentWidth(page.width)
        spacing: 18

        SettingsSection {
            id: sec_appearance
            objectName: "settings_appearance"
            title: qsTr("Appearance")
            keywords: qsTr("language languages translation français french english terminal panes boot phosphor command spinning spin record disc vinyl rotate neon cyberpunk afterimage scanlines glitch hud greebles cockpit terminal title card marquee scroll scrolling long title titles ticker numbers thousands separator comma commas digits shelf shelves row rows sideways wheel tilt arrows theme colours colors font text size bigger smaller accent album art ambient motion drift paused power battery visualizer background unfocused reduce animation dark light system pride ribbon custom badges bitrate format scroll speed mouse wheel explicit hi-res hires bit depth 24-bit sample rate")
            query: page.query
            Row {
                spacing: 12
                Text { textFormat: Text.PlainText; text: qsTr("Language"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "language"
                    width: 260
                    readonly property var codes: i18n.languages.map(l => l.code)
                    model: i18n.languages.map(l => l.name)
                    selection: Math.max(0, codes.indexOf(i18n.choice))
                    onActivated: function (i) { i18n.setLanguage(codes[i]) }
                    Accessible.name: qsTr("Language")
                }
            }
            Row {
                spacing: 12
                visible: !themeManager.followSystem  // following the system, the Light and Dark choices below apply
                Text {
                    textFormat: Text.PlainText
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Theme")
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(14)
                }
                StyledCombo {
                    id: themePicker
                    objectName: "themePicker"
                    width: 260
                    model: themeManager.availableThemes
                    selection: themeManager.availableThemes.indexOf(themeManager.currentTheme)
                    onActivated: themeManager.selectTheme(currentText)
                    contentItem: Text {
                        textFormat: Text.PlainText
                        objectName: "themePickerText"
                        leftPadding: 12
                        rightPadding: 2
                        text: themePicker.displayText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(14)
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    background: Rectangle {
                        implicitHeight: 38
                        radius: Theme.radius
                        color: Theme.surface
                        border.color: themePicker.activeFocus ? Theme.accent : Theme.border
                    }
                }
            }
            // Your own touches on the theme: an accent colour, light and dark following the system, a theme of your own
            Column {
                width: parent.width
                spacing: 8
                Text { textFormat: Text.PlainText; text: qsTr("Accent colour"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14) }
                Flow {
                    objectName: "accentSwatches"
                    width: parent.width
                    spacing: 8
                    Repeater {
                        model: ["", "#8f7bff", "#c08bff", "#ff7ab6", "#ff6b6b", "#ff9f43", "#f5be9d", "#ffd166",
                                "#5fd38d", "#2ec4b6", "#4cc9f0", "#5b8cff", "#e8e8f0"]
                        Rectangle {
                            required property string modelData
                            readonly property bool chosen: themeManager.accentOverride === modelData
                            width: 30; height: 30; radius: Theme.round(15)
                            color: modelData.length ? modelData : "transparent"
                            border.width: chosen ? 3 : 1
                            border.color: chosen ? Theme.text : Theme.border
                            Text {
                                visible: !modelData.length
                                anchors.centerIn: parent
                                text: "A"; textFormat: Text.PlainText
                                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: Font.Bold
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: themeManager.setAccentOverride(modelData)
                                Accessible.role: Accessible.RadioButton
                                Accessible.name: modelData === "#f5be9d" ? qsTr("Accent Shrimp Boat")  // PPG's paint colour
                                                 : modelData.length ? qsTr("Accent %1").arg(modelData) : qsTr("The theme's own accent")
                                Accessible.checked: chosen
                                Accessible.onPressAction: themeManager.setAccentOverride(modelData)
                            }
                        }
                    }
                    // your own colour (#129): a picker, shown filled with the accent when it's one of yours
                    Rectangle {
                        id: ownAccent
                        objectName: "accentCustom"
                        readonly property var presets: ["", "#8f7bff", "#c08bff", "#ff7ab6", "#ff6b6b", "#ff9f43", "#f5be9d", "#ffd166",
                                                        "#5fd38d", "#2ec4b6", "#4cc9f0", "#5b8cff", "#e8e8f0"]
                        readonly property bool own: themeManager.accentOverride.length > 0 && presets.indexOf(themeManager.accentOverride) < 0
                        width: 30; height: 30; radius: Theme.round(15)
                        color: own ? themeManager.accentOverride : "transparent"
                        border.width: own ? 3 : 1
                        border.color: own ? Theme.text : Theme.border
                        Text {
                            visible: !ownAccent.own
                            anchors.centerIn: parent
                            text: "+"; textFormat: Text.PlainText
                            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(16); font.weight: Font.Bold
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: accentPicker.openWith(themeManager.accentOverride)
                            Accessible.role: Accessible.Button
                            Accessible.name: qsTr("Pick your own accent colour")
                            Accessible.onPressAction: accentPicker.openWith(themeManager.accentOverride)
                        }
                        ToolTip.visible: ownHover.hovered
                        ToolTip.text: qsTr("Your own colour…")
                        ToolTip.delay: 500
                        HoverHandler { id: ownHover }
                        ColorPicker {
                            id: accentPicker
                            parent: Overlay.overlay
                            x: Math.round((parent.width - width) / 2); y: Math.round((parent.height - height) / 2)
                            property string pending: ""
                            // shown live, a few times a second at most: every change of the accent recolours the app
                            onPicked: function (c) { pending = c; livePreview.restart() }
                            onDone: function (c) { if (c) { livePreview.stop(); themeManager.setAccentOverride(c) } }
                            Timer { id: livePreview; interval: 60; onTriggered: themeManager.setAccentOverride(accentPicker.pending) }
                        }
                    }
                    TextField {
                        id: accentHex
                        objectName: "accentHex"
                        width: 120; height: 30
                        placeholderText: "#hex"
                        text: themeManager.accentOverride
                        selectByMouse: true
                        Accessible.name: qsTr("Accent colour as a hex code")
                        // typing breaks the binding above: follow the accent again once it changes elsewhere
                        Connections { target: themeManager; function onThemeChanged() { if (!accentHex.activeFocus) accentHex.text = themeManager.accentOverride } }
                        onAccepted: themeManager.setAccentOverride(text)
                    }
                }
                StyledCheck {
                    objectName: "albumArtAccent"
                    text: qsTr("Tint the accent with each album's cover")
                    checked: themeManager.albumArtAccent
                    onToggled: themeManager.setAlbumArtAccent(checked)
                }
                StyledCheck {
                    objectName: "followSystemTheme"
                    text: qsTr("Follow the system's light or dark mode")
                    checked: themeManager.followSystem
                    onToggled: themeManager.setFollowSystem(checked)
                }
                Flow {
                    visible: themeManager.followSystem
                    width: parent.width
                    spacing: 10
                    Text { textFormat: Text.PlainText; text: qsTr("Light"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        width: 200
                        model: themeManager.availableThemes
                        selection: themeManager.availableThemes.indexOf(themeManager.lightTheme)
                        onActivated: themeManager.setSystemThemes(currentText, themeManager.darkTheme)
                        Accessible.name: qsTr("Theme in light mode")
                    }
                    Text { textFormat: Text.PlainText; text: qsTr("Dark"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        width: 200
                        model: themeManager.availableThemes
                        selection: themeManager.availableThemes.indexOf(themeManager.darkTheme)
                        onActivated: themeManager.setSystemThemes(themeManager.lightTheme, currentText)
                        Accessible.name: qsTr("Theme in dark mode")
                    }
                }
                PillButton { objectName: "makeTheme"; text: qsTr("Make my own theme…"); onClicked: themeEditor.open() }
            }
            ThemeEditor { id: themeEditor }
            // A neon theme's own options (Afterimage): shown only while one is chosen
            Column {
                objectName: "neonOptions"
                visible: Theme.neon
                width: parent.width
                spacing: 8
                Text { textFormat: Text.PlainText; text: qsTr("%1 options").arg(themeManager.currentTheme); color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(15) * Theme.displayScale; font.weight: Font.DemiBold }
                Flow {
                    width: parent.width
                    spacing: 10
                    Text { textFormat: Text.PlainText; text: qsTr("Now Playing"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "neonNowPlaying"
                        readonly property var modes: ["cockpit", "terminal", "classic"]
                        width: 320
                        model: [qsTr("Cockpit (gauges and a hologram)"), qsTr("Terminal (typed out)"), qsTr("Classic (the usual one)")]
                        selection: Math.max(0, modes.indexOf(shell.ui.neonNowPlaying || "cockpit"))
                        onActivated: shell.setUiValue("neonNowPlaying", modes[currentIndex])
                        Accessible.name: qsTr("Now Playing in this theme")
                    }
                    Text { textFormat: Text.PlainText; text: qsTr("Cockpit colours"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "neonTint"
                        readonly property var modes: ["theme", "cover"]
                        width: 200
                        model: [qsTr("The theme's neon"), qsTr("The cover's")]
                        selection: shell.ui.neonTint === "cover" ? 1 : 0
                        onActivated: shell.setUiValue("neonTint", modes[currentIndex])
                        Accessible.name: qsTr("Cockpit colours")
                    }
                    Text { textFormat: Text.PlainText; text: qsTr("Terminal"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "neonPhosphor"
                        readonly property var modes: ["theme", "green", "amber"]
                        width: 200
                        model: [qsTr("The theme's colour"), qsTr("Green phosphor"), qsTr("Amber phosphor")]
                        selection: Math.max(0, modes.indexOf(shell.ui.neonPhosphor || "theme"))
                        onActivated: shell.setUiValue("neonPhosphor", modes[currentIndex])
                        Accessible.name: qsTr("Terminal colour")
                    }
                }
                StyledCheck {
                    objectName: "neonScanlines"
                    text: qsTr("Scanlines and a vignette over the window")
                    checked: Theme.neonOption("Scanlines")
                    onToggled: shell.setUiValue("neonScanlines", checked ? "1" : "0")
                }
                StyledCheck {
                    objectName: "neonGlitch"
                    text: qsTr("A glitch when the song changes (and a hologram's flicker)")
                    checked: Theme.neonOption("Glitch")
                    enabled: !shell.reduceMotion
                    onToggled: shell.setUiValue("neonGlitch", checked ? "1" : "0")
                }
                StyledCheck {
                    objectName: "neonGreebles"
                    text: qsTr("HUD details (corner brackets, ticks, status lights and readouts)")
                    checked: Theme.neonGreebles
                    onToggled: shell.setUiValue("neonGreebles", checked ? "1" : "0")
                }
                StyledCheck {
                    objectName: "neonBoot"
                    text: qsTr("A start-up sequence when the terminal opens")
                    checked: shell.ui.neonBoot !== "0"
                    onToggled: shell.setUiValue("neonBoot", checked ? "1" : "0")
                }
                // the terminal's panes, in the order they show (it can pin and unpin them itself too)
                Text { textFormat: Text.PlainText; text: qsTr("Terminal panes"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13) }
                Flow {
                    objectName: "neonPanes"
                    width: parent.width
                    spacing: 8
                    readonly property var names: ({ now: qsTr("Now playing"), wave: qsTr("Waveform"), spectrum: qsTr("Spectrum"), lyrics: qsTr("Lyrics"),
                        queue: qsTr("Up next"), signal: qsTr("Signal path"), stats: qsTr("Today's stats"), tags: qsTr("Tags"), similar: qsTr("Similar artists"),
                        whoami: qsTr("Your library"), log: qsTr("Log") })
                    readonly property var shown: {
                        var v = shell.ui.neonTermPanes  // (blank: the usual ones; "none": every one unpinned)
                        return (v === undefined || v === "" ? "now,wave,spectrum,lyrics,queue" : v === "none" ? "" : v).split(",").filter(function (p) { return p })
                    }
                    Repeater {
                        model: ["now", "wave", "spectrum", "lyrics", "queue", "signal", "stats", "tags", "similar", "whoami", "log"]
                        Chip {
                            required property string modelData
                            text: parent.names[modelData]
                            selected: parent.shown.indexOf(modelData) >= 0
                            onClicked: {
                                var list = parent.shown.filter(function (p) { return p !== modelData })
                                if (!selected) list.push(modelData)
                                shell.setUiValue("neonTermPanes", list.length ? list.join(",") : "none")
                            }
                        }
                    }
                }
                StyledCheck {
                    objectName: "neonTitleCard"
                    text: qsTr("A title card for each new song in the cockpit")
                    checked: shell.ui.neonTitleCard !== "0"
                    enabled: !shell.reduceMotion
                    onToggled: shell.setUiValue("neonTitleCard", checked ? "1" : "0")
                }
                PillButton {
                    objectName: "neonReset"
                    text: qsTr("Reset these options")
                    onClicked: {
                        var keys = ["neonNowPlaying", "neonTint", "neonPhosphor", "neonScanlines", "neonGlitch", "neonGreebles",
                                    "neonTitleCard", "neonBoot", "neonTermPanes", "neonVisStyle"]
                        for (var i = 0; i < keys.length; i++) shell.setUiValue(keys[i], "")
                        Nav.notify(qsTr("%1's options are back as they came").arg(themeManager.currentTheme))
                    }
                }
            }
            StyledCheck {
                objectName: "ambientMotion"
                text: qsTr("Animated background (slowly drifting colours from the current cover)")
                checked: shell.ambientMotion
                onToggled: shell.setAmbientMotion(checked)
            }
            StyledCheck {
                objectName: "ambientOnlyPlaying"
                visible: shell.ambientMotion
                leftPadding: 28
                text: qsTr("Only while music plays (it rests while paused, using no power)")
                checked: shell.ambientOnlyPlaying
                onToggled: shell.setAmbientOnlyPlaying(checked)
            }
            Flow {
                visible: shell.features.visualizer !== false
                width: parent.width
                spacing: 10
                Text { textFormat: Text.PlainText; text: qsTr("Visualizer while the window is in the background"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "visualizerBackground"
                    readonly property var modes: ["full", "slower", "paused"]
                    width: 220
                    model: [qsTr("Full speed"), qsTr("Slower (saves power)"), qsTr("Paused")]
                    selection: Math.max(0, modes.indexOf(shell.visualizerBackground))
                    onActivated: shell.setVisualizerBackground(modes[currentIndex])
                    Accessible.name: qsTr("Visualizer while the window is in the background")
                }
            }
            Flow {
                width: parent.width
                spacing: 10
                Text { textFormat: Text.PlainText; text: qsTr("Covers in the player bar and mini player"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "spinningArt"
                    width: 260
                    model: [qsTr("Still"), qsTr("A record, spinning while playing")]
                    selection: shell.ui.spinningArt === "1" ? 1 : 0
                    onActivated: shell.setUiValue("spinningArt", currentIndex === 1 ? "1" : "0")  // i18n: keep
                    Accessible.name: qsTr("Covers in the player bar and mini player")
                }
            }
            StyledCheck {
                objectName: "reduceMotion"
                text: qsTr("Reduce motion (no page transitions, zooms, spinning record or growing buttons)")
                checked: shell.reduceMotion
                onToggled: shell.setReduceMotion(checked)
            }
            SettingsGroup {
                key: "appearanceMore"
                title: qsTr("More appearance options")
                summary: qsTr("Text size, track badges, theme files")
                query: page.query
                Flow {
                    width: parent.width
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: qsTr("Text size"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "textSize"
                        width: 200
                        readonly property var sizes: [0.9, 1.0, 1.1, 1.25, 1.4]
                        model: [qsTr("Smaller"), qsTr("As the theme has it"), qsTr("Larger"), qsTr("Larger still"), qsTr("Largest")]
                        selection: sizes.indexOf(themeManager.textScale)
                        onActivated: function (i) { themeManager.setTextScale(sizes[i]) }
                        Accessible.name: qsTr("Text size")
                    }
                }
                Row {
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: qsTr("Scroll speed"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "scrollSpeed"
                        width: 200
                        readonly property var speeds: [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
                        model: [qsTr("Slowest"), qsTr("Slow"), qsTr("Normal"), qsTr("Fast"), qsTr("Faster"), qsTr("Fastest")]
                        selection: speeds.indexOf(shell.scrollSpeed) >= 0 ? speeds.indexOf(shell.scrollSpeed) : 2
                        onActivated: function (i) { shell.setScrollSpeed(speeds[i]) }
                        Accessible.name: qsTr("Scroll speed (mouse wheel)")
                    }
                }
                Row {
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: qsTr("Wheel over a row of albums"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "shelfWheel"
                        width: 260
                        readonly property var modes: ["auto", "row", "page"]
                        model: [qsTr("Moves the row (a page scroll carries on past it)"), qsTr("Always moves the row, then the page"), qsTr("Scrolls the page")]
                        selection: Math.max(0, modes.indexOf(shell.ui.shelfWheel || "auto"))
                        onActivated: function (i) { shell.setUiValue("shelfWheel", modes[i]) }
                        Accessible.name: qsTr("Mouse wheel over a row of albums")
                    }
                }
                Row {
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: qsTr("Long song titles"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "marquee"
                        width: 260
                        readonly property var modes: ["playing", "hover", "off"]
                        model: [qsTr("Scroll while playing"), qsTr("Scroll when pointed at"), qsTr("Don't scroll (end in …)")]
                        selection: Math.max(0, modes.indexOf(shell.ui.marquee || "playing"))
                        onActivated: function (i) { shell.setUiValue("marquee", modes[i]) }
                        Accessible.name: qsTr("Long song titles in the player bar and mini player")
                    }
                }
                Row {
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: qsTr("Numbers"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "numberFormat"
                        width: 260
                        readonly property var formats: ["locale", "comma", "period", "space", "none"]
                        model: [qsTr("As your language writes them (%1)").arg(Number(12345).toLocaleString(Qt.locale(), "f", 0)),
                                "12,345", "12.345", "12\u202f345", "12345"]
                        selection: Math.max(0, formats.indexOf(Theme.numberFormat))
                        onActivated: function (i) { shell.setUiValue("numberFormat", formats[i]) }
                        Accessible.name: qsTr("How numbers are written")
                    }
                }
                StyledCheck {
                    objectName: "shelfArrows"
                    text: qsTr("Show back and forward buttons on rows of albums")
                    checked: shell.ui.shelfArrows !== "false"
                    onToggled: shell.setUiValue("shelfArrows", checked ? "true" : "false")
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: qsTr("Rows that scroll sideways (Home's shelves, search results) always move with Shift+wheel, a tilting wheel or a touchpad swipe. Scrolling down the page doesn't stop at each row: a row takes the wheel when you start turning it over the row.")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
                StyledCheck {
                    text: qsTr("Show audio format and average bitrate on tracks")
                    checked: player.showTrackInfo
                    onToggled: player.setShowTrackInfo(checked)
                    Accessible.name: qsTr("Show track audio format and average bitrate")
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    text: qsTr("Shows compact format and approximate average bitrate badges in song rows and the now-playing bar.")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                    wrapMode: Text.WordWrap
                }
                StyledCheck {
                    objectName: "explicitBadges"
                    text: qsTr("Mark explicit songs with an E")
                    checked: Rows.explicitBadges
                    onToggled: shell.setSongBadge("explicitBadges", checked)
                }
                StyledCheck {
                    objectName: "cleanBadges"
                    text: qsTr("Mark clean (edited) versions with a C")
                    checked: Rows.cleanBadges
                    onToggled: shell.setSongBadge("cleanBadges", checked)
                }
                StyledCheck {
                    objectName: "hiResBadges"
                    text: qsTr("Show a Hi-Res badge on 24-bit and higher songs")
                    checked: Rows.hiResBadges
                    onToggled: shell.setSongBadge("hiResBadges", checked)
                }
                Row {
                    visible: Rows.hiResBadges
                    leftPadding: 28
                    spacing: 12
                    Text { anchors.verticalCenter: parent.verticalCenter; text: qsTr("Hi-Res badge"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                    StyledCombo {
                        objectName: "hiResBadgeStyle"
                        width: 230
                        model: [qsTr("\"Hi-Res\""), qsTr("A gold M (Master)")]
                        selection: Rows.masterBadge ? 1 : 0
                        onActivated: function (i) { shell.setSongBadge("masterBadge", i === 1) }
                        Accessible.name: qsTr("Hi-Res badge style")
                    }
                }
                StyledCheck {
                    objectName: "bitDepthBadges"
                    text: qsTr("Show every song's bit depth and sample rate")
                    checked: Rows.bitDepth
                    onToggled: shell.setSongBadge("bitDepth", checked)
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    text: qsTr("Explicit comes from the files' tags (iTunes advisory or an EXPLICIT tag); bit depth from lossless files (FLAC, ALAC, WAV, AIFF, WavPack, APE, DSD). Songs added before this version get both at the next scan.")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                    wrapMode: Text.WordWrap
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                    text: qsTr("Custom themes: %1").arg(themeManager.userThemeDirectory + "/*.json")
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(12)
                }
                PillButton {
                    text: qsTr("Reload themes")
                    onClicked: themeManager.reloadThemes()
                }
            }

        }
        SettingsSection {
            id: sec_features
            objectName: "settings_features"
            title: qsTr("Features")
            keywords: qsTr("hide show turn off sidebar pages order rearrange move arrange home cards internet radio stations podcasts lyrics stats recap history visualizer health folders liked")
            query: page.query
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: qsTr("Turn off what you don't use. It disappears everywhere (the sidebar, Ctrl+K, menus and shortcuts) and nothing is lost: switch it back on and it's all still there.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                wrapMode: Text.WordWrap
            }
            component FeatureGroup: Column {
                property string heading
                property var items: []
                width: parent ? parent.width : 400
                spacing: 6
                Text {
                    textFormat: Text.PlainText
                    text: parent.heading
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
                }
                Flow {
                    width: parent.width
                    spacing: 4
                    Repeater {
                        model: parent.parent.items
                        StyledCheck {
                            required property var modelData
                            objectName: "feature_" + modelData[0]
                            width: Math.max(220, implicitWidth + 12)
                            text: modelData[1]
                            checked: shell.features[modelData[0]] !== false
                            onToggled: shell.setFeature(modelData[0], checked)
                        }
                    }
                }
            }
            FeatureGroup {
                heading: qsTr("Listening")
                items: [["stations", qsTr("Internet radio")], ["podcasts", qsTr("Podcasts")], ["servers", qsTr("Music servers")],
                        ["lyrics", qsTr("Lyrics")], ["visualizer", qsTr("Visualizer")], ["casting", qsTr("Casting")]]
            }
            FeatureGroup {
                heading: qsTr("Pages")
                items: [["liked", qsTr("Liked Songs")], ["folders", qsTr("Folders")], ["stats", qsTr("Stats")], ["history", qsTr("History")],
                        ["recap", qsTr("Recap")], ["health", qsTr("Library health")]]
            }
            FeatureGroup {
                heading: qsTr("Home")
                items: [["homeRandom", qsTr("Random album")], ["homeListening", qsTr("Listening card")],
                        ["homeFacts", qsTr("Library facts")], ["homeShelves", qsTr("Album shelves")]]
            }
            SettingsGroup {
                id: sidebarGroup
                key: "sidebarOrder"
                title: qsTr("Sidebar order")
                summary: qsTr("Move pages up or down")
                query: page.query
                Column {
                    id: sidebarOrderBox
                    objectName: "sidebarOrder"
                    width: parent.width
                    spacing: 6
                    readonly property var names: ({ home: qsTr("Home"), albums: qsTr("Albums"), artists: qsTr("Artists"), songs: qsTr("Songs"),
                        folders: qsTr("Folders"), liked: qsTr("Liked Songs"), stats: qsTr("Stats"), history: qsTr("History"), recap: qsTr("Recap"),
                        visualizer: qsTr("Visualizer"), stations: qsTr("Internet radio"), podcasts: qsTr("Podcasts") })
                    readonly property var shown: shell.sidebarOrder.filter(function (p) { return shell.features[p] !== false })
                    Row {
                        width: parent.width
                        spacing: 12
                        Text {
                            textFormat: Text.PlainText
                            anchors.verticalCenter: parent.verticalCenter
                            text: qsTr("Sidebar order")
                            color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
                        }
                        PillButton { objectName: "resetSidebarOrder"; height: 30; text: qsTr("Reset"); onClicked: shell.resetSidebarOrder() }
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("Move pages up or down here, drag them in the sidebar, or right-click one there. With a page focused, Alt+Up and Alt+Down move it too.")
                        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                    }
                    Repeater {
                        model: sidebarOrderBox.shown
                        Rectangle {
                            required property string modelData
                            required property int index
                            objectName: "sidebarOrder_" + modelData
                            width: Math.min(380, sidebarOrderBox.width)
                            height: 34
                            radius: Theme.radiusSmall
                            color: Theme.surface
                            Text {
                                textFormat: Text.PlainText
                                anchors { left: parent.left; leftMargin: 14; verticalCenter: parent.verticalCenter }
                                text: (index + 1) + ".  " + sidebarOrderBox.names[modelData]
                                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                            }
                            Row {
                                anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                                spacing: 2
                                IconButton {
                                    icon: "up"; size: 16
                                    enabled: index > 0
                                    opacity: enabled ? 1 : 0.35
                                    tip: qsTr("Move %1 up").arg(sidebarOrderBox.names[modelData])
                                    onClicked: shell.moveSidebarPage(modelData, -1)
                                }
                                IconButton {
                                    icon: "down"; size: 16
                                    enabled: index < sidebarOrderBox.shown.length - 1
                                    opacity: enabled ? 1 : 0.35
                                    tip: qsTr("Move %1 down").arg(sidebarOrderBox.names[modelData])
                                    onClicked: shell.moveSidebarPage(modelData, 1)
                                }
                            }
                        }
                    }
                }
            }
        }

        SettingsSection {
            id: sec_podcasts
            objectName: "settings_podcasts"
            title: qsTr("Podcasts")
            keywords: qsTr("podcast episodes skip back forward seconds feeds check refresh download keep remove storage played speed next")
            query: page.query
            visible: matches && shell.features.podcasts !== false
            readonly property var o: podcasts.options
            function secs(list) { return list.map(function (n) { return Theme.counted(qsTr("%n second(s)", "", n), n) }) }
            OptionCombo {
                label: qsTr("Skip back")
                values: [5, 10, 15, 30, 45, 60]; labels: sec_podcasts.secs(values)
                current: sec_podcasts.o.skipBack
                onPicked: function (v) { podcasts.setOption("skipBack", v) }
            }
            OptionCombo {
                label: qsTr("Skip forward")
                values: [10, 15, 30, 45, 60, 90]; labels: sec_podcasts.secs(values)
                current: sec_podcasts.o.skipForward
                onPicked: function (v) { podcasts.setOption("skipForward", v) }
            }
            OptionCombo {
                label: qsTr("After an episode")
                values: ["next", "stop"]
                labels: [qsTr("Play the show's next one"), qsTr("Stop")]
                current: sec_podcasts.o.afterEpisode
                onPicked: function (v) { podcasts.setOption("afterEpisode", v) }
            }
            StyledCheck {
                objectName: "notifyNewEpisodes"
                text: qsTr("Tell me when a show I follow has a new episode (a desktop notification)")
                checked: sec_podcasts.o.notifyNew === 1
                onToggled: podcasts.setOption("notifyNew", checked ? 1 : 0)
            }
            SettingsGroup {
                key: "podcastsMore"
                title: qsTr("When to check, and when an episode counts as played")
                query: page.query
                OptionCombo {
                    label: qsTr("Check for new episodes")
                    values: [1, 2, 4, 8, 12, 24, 0]
                    labels: [qsTr("Every hour"), qsTr("Every 2 hours"), qsTr("Every 4 hours"), qsTr("Every 8 hours"), qsTr("Twice a day"), qsTr("Once a day"), qsTr("Only when I ask")]
                    current: sec_podcasts.o.refreshHours
                    onPicked: function (v) { podcasts.setOption("refreshHours", v) }
                }
                OptionCombo {
                    label: qsTr("Played when this close to the end")
                    values: [10, 30, 45, 60, 120, 300]
                    labels: [qsTr("10 seconds"), qsTr("30 seconds"), qsTr("45 seconds"), qsTr("1 minute"), qsTr("2 minutes"), qsTr("5 minutes")]
                    current: sec_podcasts.o.playedWindow
                    onPicked: function (v) { podcasts.setOption("playedWindow", v) }
                }
            }
            Text { textFormat: Text.PlainText; text: qsTr("Downloads"); color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
            OptionCombo {
                label: qsTr("A show you follow downloads")
                values: [0, 1, 2, 3, 5]
                labels: [qsTr("Nothing by itself"), qsTr("Its newest episode"), qsTr("Its newest 2"), qsTr("Its newest 3"), qsTr("Its newest 5")]
                current: sec_podcasts.o.newShowDownloads
                onPicked: function (v) { podcasts.setOption("newShowDownloads", v) }
            }
            OptionCombo {
                label: qsTr("Keep downloads")
                values: ["played", "latest", "forever"]
                labels: [qsTr("Until they're played"), qsTr("Only the newest of each show"), qsTr("Until I remove them")]
                current: sec_podcasts.o.keep
                onPicked: function (v) { podcasts.setOption("keep", v) }
            }
            OptionCombo {
                visible: sec_podcasts.o.keep === "latest"
                label: qsTr("Newest to keep per show")
                values: [1, 2, 3, 5, 10]; labels: ["1", "2", "3", "5", "10"]
                current: sec_podcasts.o.keepCount
                onPicked: function (v) { podcasts.setOption("keepCount", v) }
            }
            Row {
                spacing: 12
                Text {
                    textFormat: Text.PlainText
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Downloads take %1").arg(Theme.fmtBytes(podcasts.downloadsSize))
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                }
                PillButton { text: qsTr("Remove all downloads"); enabled: podcasts.downloadsSize > 0; onClicked: removeDownloadsDlg.open() }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Each show can have its own speed, skip its intro or outro, list oldest first and download its newest episodes: open the show and choose Show settings. Episodes in a folder you added are your own files and are never removed.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            ConfirmDialog {
                id: removeDownloadsDlg
                title: qsTr("Remove every downloaded episode?")
                body: qsTr("The files go; the episodes stay, and play from the web until downloaded again.")
                confirmText: qsTr("Remove downloads")
                destructive: true
                onAccepted: podcasts.removeAllDownloads()
            }
        }

        SettingsSection {
            id: sec_playback
            objectName: "settings_playback"
            title: qsTr("Playback")
            keywords: qsTr("unplug unplugged headphones bluetooth disconnect sample rate resample resampling bit perfect signal path pipewire allowed rates 44.1 48 output device audio replaygain loudness preamp measure crossfade gapless album fade pause resume start startup open volume step wheel maximum limit loud speed sleep timer")
            query: page.query
            StyledCheck {
                objectName: "pauseOnUnplug"
                text: qsTr("Pause when the headphones (or the device playing) go away")
                checked: player.pauseOnUnplug
                onToggled: player.setPauseOnUnplug(checked)
            }
            Flow {  // wraps in a narrow window
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: qsTr("Output device"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    id: deviceCombo
                    objectName: "outputDevice"
                    width: Math.min(360, parent.width)
                    model: player.outputDevices
                    textRole: "name"
                    currentIndex: player.outputDevices.findIndex(d => d.key === player.outputDevice)
                    onActivated: player.setOutputDevice(player.outputDevices[currentIndex].key)
                    // Activating breaks the binding above; re-sync when devices come and go.
                    Connections {
                        target: player
                        function onOutputDevicesChanged() {
                            deviceCombo.currentIndex = player.outputDevices.findIndex(d => d.key === player.outputDevice)
                        }
                    }
                }
            }
            Flow {  // wraps in a narrow window
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: qsTr("Output sample rate"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "outputRateMode"
                    width: Math.min(360, parent.width)
                    readonly property var modes: ["auto", "follows", "fixed"]
                    model: [player.pipewireRates ? qsTr("Find out (PipeWire switches: %1)").arg(player.pipewireRates) : qsTr("Find out (the device's own rate)"),
                            qsTr("Follows each song (set up for it)"), qsTr("Fixed at the device's rate")]
                    selection: Math.max(0, modes.indexOf(player.outputRateMode))
                    onActivated: function (i) { player.setOutputRateMode(modes[i]) }
                    Accessible.name: qsTr("Output sample rate, for the signal path")
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("What the signal path assumes the output runs at. Hallucinate plays each song at its own rate; whether the output converts it is up to your system (PipeWire's allowed rates, a DAC's settings).")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Flow {  // wraps in a narrow window
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: qsTr("ReplayGain"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "rgMode"
                    model: [qsTr("Off"), qsTr("Track"), qsTr("Album")]
                    selection: ["off", "track", "album"].indexOf(player.replayGainMode)
                    onActivated: player.setReplayGainMode(["off", "track", "album"][currentIndex])
                }
            }
            SettingsGroup {
                key: "replayGain"
                title: qsTr("ReplayGain details")
                summary: qsTr("Preamp, measuring songs without tags")
                query: page.query
                Flow {
                    width: parent.width
                    spacing: 12
                    Text { height: 38; verticalAlignment: Text.AlignVCenter; text: qsTr("Preamp %1 dB").arg(Theme.num(player.replayGainPreamp, 1)); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                    StyledSlider {
                        width: 140
                        from: -15; to: 15; stepSize: 0.5
                        value: player.replayGainPreamp
                        onMoved: player.setReplayGainPreamp(value)
                    }
                }
                StyledCheck {
                    objectName: "autoReplayGain"
                    text: qsTr("Measure new music by itself after each scan")
                    checked: replayGain.auto
                    onToggled: replayGain.setAuto(checked)
                }
                Flow {  // wraps in a narrow window
                    width: parent.width
                    spacing: 12
                    PillButton {
                        objectName: "analyseReplayGain"
                        text: replayGain.busy ? qsTr("Stop measuring") : qsTr("Measure songs without ReplayGain")
                        onClicked: replayGain.busy ? replayGain.cancel() : replayGain.analyseMissing()
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: Math.min(implicitWidth, parent.width)
                        wrapMode: Text.WordWrap
                        text: replayGain.busy ? Theme.counted(qsTr("Measured %1 of %n song(s)…", "", replayGain.total), replayGain.total).arg(Theme.num(replayGain.done))
                            : qsTr("Measures loudness (EBU R128) for songs whose files have no ReplayGain tags. Files aren't changed.")
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(12)
                    }
                }
            }
            Flow {
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: player.crossfade > 0 ? qsTr("Crossfade %1 s").arg(Theme.num(player.crossfade, player.crossfade % 1 ? 1 : 0)) : qsTr("Crossfade off"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledSlider {
                    objectName: "crossfade"
                    width: 200
                    from: 0; to: 12; stepSize: 1
                    value: player.crossfade
                    onMoved: player.setCrossfade(value)
                }
            }
            Flow {
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: qsTr("Volume step"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "volumeStep"
                    readonly property var steps: [0.01, 0.02, 0.05, 0.1]
                    width: 120
                    model: ["1%", "2%", "5%", "10%"]
                    selection: Math.max(0, steps.findIndex(s => Math.abs(s - player.volumeStep) < 0.001))
                    onActivated: player.setVolumeStep(steps[currentIndex])
                    Accessible.name: qsTr("Volume step for the mouse wheel and arrow keys")
                }
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: qsTr("Maximum volume %1%").arg(Math.round(player.maxVolume * 100)); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledSlider {
                    objectName: "maxVolume"
                    width: 160
                    from: 0.1; to: 1; stepSize: 0.05
                    value: player.maxVolume
                    onMoved: player.setMaxVolume(value)
                    Accessible.name: qsTr("Maximum volume")
                }
            }
            StyledCheck {
                objectName: "resumeOnStart"
                text: qsTr("Start playing when Hallucinate opens (carry on where it was)")
                checked: player.resumeOnStart
                onToggled: player.setResumeOnStart(checked)
            }
            StyledCheck {
                objectName: "crossfadeAlbums"
                visible: player.crossfade > 0
                text: qsTr("Crossfade between songs of the same album too (off: an album plays gaplessly, as it runs)")
                checked: player.crossfadeAlbums
                onToggled: player.setCrossfadeAlbums(checked)
            }
            Flow {
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: qsTr("Fade on pause and play"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "pauseFade"
                    readonly property var lengths: [0, 150, 400, 1000]
                    width: 200
                    model: [qsTr("Off"), qsTr("Quick"), qsTr("Gentle"), qsTr("Slow")]
                    selection: Math.max(0, lengths.indexOf(player.pauseFade))
                    onActivated: player.setPauseFade(lengths[currentIndex])
                    Accessible.name: qsTr("Fade on pause and play")
                }
            }
            Text { width: parent.width; wrapMode: Text.WordWrap; text: qsTr("Gapless playback is always on; with crossfade off, consecutive tracks play back to back. Playback speed and the sleep timer are in the ⋯ menu of the player bar."); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); textFormat: Text.PlainText }
        }
        SettingsSection {
            id: sec_sound
            objectName: "settings_sound"
            title: qsTr("Sound")
            keywords: qsTr("equalizer eq bass treble headphones autoeq crossfeed bit-perfect bitperfect exclusive untouched resample sample rate pipewire audiophile")
            query: page.query
            StyledCheck {
                objectName: "bitPerfect"
                enabled: player.eqAvailable
                text: qsTr("Bit-perfect playback")
                checked: player.bitPerfect
                onToggled: player.setBitPerfect(checked)
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: (player.bitPerfect
                       ? qsTr("Every song goes to your sound output exactly as it's stored, at its own bit depth. The equalizer, crossfeed, ReplayGain, crossfade, fades and speed are set aside, and Hallucinate's volume stays at 100%: use your system's or your amplifier's volume.")
                       : qsTr("Send every song to your sound output exactly as it's stored: the equalizer, crossfeed, ReplayGain, crossfade, fades, speed and Hallucinate's volume step aside while it's on (your settings for them are kept)."))
                      + " " + (player.bitPerfectRates
                       ? qsTr("PipeWire is asked to run at each song's own rate, so nothing is resampled on the way.")
                       : qsTr("To keep each song's own rate too, Linux with PipeWire and its tools (pw-metadata) is needed; elsewhere the system may resample it. The signal path shows what happens."))
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            EqualizerPanel { width: parent.width; opacity: player.bitPerfect ? 0.5 : 1 }
            Flow {
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: qsTr("Headphone crossfeed"); color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "crossfeed"
                    enabled: player.eqAvailable
                    model: [qsTr("Off"), qsTr("Light"), qsTr("Medium"), qsTr("Strong")]
                    selection: player.crossfeedPresets.indexOf(player.crossfeed)
                    onActivated: player.setCrossfeed(player.crossfeedPresets[currentIndex])
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Lets each ear hear a little of the other channel, as from speakers. Old stereo recordings with instruments hard left or right get much easier on the ears over headphones.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }

        }
        SettingsSection {
            id: sec_library
            objectName: "settings_library"
            title: qsTr("Library")
            keywords: qsTr("genres genre music folders scan rescan start startup watch watching health tags files ratings stars cover art cover.jpg embed import strawberry clementine rhythmbox musicbee itunes foobar playlists hidden removed restore albums backup export your data move computer duplicates already sort order sidebar select selection selecting drag multiple")
            query: page.query
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: library.scanAtStart ? (library.watching ? qsTr("Folders are scanned in the background at every start and watched for changes.")
                                                              : qsTr("Folders are scanned in the background at every start. Rescan picks up what's new."))
                                          : (library.watching ? qsTr("Folders are scanned in the background and watched for changes.")
                                                              : qsTr("Folders are scanned in the background. Rescan picks up what's new."))
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            StyledCheck {
                objectName: "scanAtStart"
                text: qsTr("Look for new and changed files when Hallucinate starts")
                checked: library.scanAtStart
                onToggled: library.setScanAtStart(checked)
            }
            StyledCheck {
                objectName: "watchFolders"
                text: qsTr("Watch the folders and pick up changes as they happen")
                checked: library.watching
                onToggled: library.setWatching(checked)
            }
            Repeater {
                model: library.folders
                Rectangle {
                    required property var modelData
                    width: parent.width; height: 48; radius: Theme.radius
                    color: Theme.surface
                    Text {
                        textFormat: Text.PlainText
                        anchors { left: parent.left; leftMargin: 16; right: rm.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                        text: modelData
                        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); elide: Text.ElideMiddle
                    }
                    IconButton {
                        id: rm
                        anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                        icon: "close"; size: 14
                        tip: qsTr("Remove this folder from the library")
                        onClicked: Nav.removeFolder(modelData)
                    }
                }
            }
            Flow {  // wraps in a narrow window
                width: parent.width
                spacing: 10
                TextField {
                    id: pathField
                    width: Math.min(420, parent.width); height: 38
                    placeholderText: "/path/to/music"
                    color: Theme.text
                    placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(14)
                    leftPadding: 14
                    background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: pathField.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                    onAccepted: add.clicked()
                }
                PillButton {
                    id: add
                    primary: true
                    text: qsTr("Add folder")
                    onClicked: { library.addFolder(pathField.text); pathField.text = "" }
                }
                PillButton { text: qsTr("Choose folder…"); onClicked: picker.open() }
                PillButton { text: qsTr("Rescan now"); onClicked: library.rescan() }
                PillButton { objectName: "openHealth"; visible: shell.features.health !== false; text: qsTr("Library health"); onClicked: Nav.openHealth() }
            }
            FolderPicker { id: picker }
            ScanBar { width: parent.width }
            Text {
                textFormat: Text.PlainText
                visible: !library.scanning && library.status.length > 0
                text: library.status
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                visible: library.missingFolders.length > 0
                wrapMode: Text.WordWrap
                text: qsTr("Folder not found or unreadable: %1").arg(library.missingFolders.join(", "))
                color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Text {
                textFormat: Text.PlainText
                visible: library.unreadableFiles > 0 && !library.scanning
                text: Theme.counted(qsTr("%n file(s) could not be read and were skipped.", "", library.unreadableFiles), library.unreadableFiles)
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Flow {
                visible: library.hiddenCount > 0
                width: parent.width
                spacing: 12
                Text {
                    textFormat: Text.PlainText
                    objectName: "hiddenCount"
                    height: 32; verticalAlignment: Text.AlignVCenter
                    text: Theme.counted(qsTr("%n file(s) removed from the library (still on disk)", "", library.hiddenCount), library.hiddenCount)
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                PillButton {
                    objectName: "restoreHidden"
                    height: 32
                    text: qsTr("Bring them back")
                    onClicked: { library.restoreHidden(); Nav.notify(qsTr("Rescanning to bring them back…")) }
                }
            }
            SettingsGroup {
                key: "playlistsSelecting"
                title: qsTr("Playlists and selecting")
                summary: qsTr("Songs already in a playlist, the sidebar's order, how selecting works")
                query: page.query
                OptionCombo {
                    objectName: "playlistDuplicates"
                    label: qsTr("Adding a song a playlist already has")
                    values: ["skip", "ask", "add"]
                    labels: [qsTr("Leave it out (Add anyway is in the note)"), qsTr("Ask each time"), qsTr("Add it again")]
                    current: shell.ui.playlistDuplicates || "skip"
                    onPicked: function (v) { shell.setUiValue("playlistDuplicates", v) }
                }
                OptionCombo {
                    objectName: "playlistSortSetting"
                    label: qsTr("Playlists in the sidebar")
                    values: ["name", "name-desc", "newest", "oldest", "added", "songs", "custom"]
                    labels: [qsTr("By name, A–Z"), qsTr("By name, Z–A"), qsTr("Newest first"), qsTr("Oldest first"), qsTr("Recently added to"), qsTr("Most songs"),
                             qsTr("My own order (Move up and down in a playlist's menu)")]
                    current: shell.ui.playlistSort || "name"
                    onPicked: function (v) { shell.setUiValue("playlistSort", v) }
                }
                StyledCheck {
                    objectName: "keepSelection"
                    text: qsTr("Keep what's selected while I go to other pages (gather songs from several places)")
                    checked: (shell.ui.keepSelection || "true") === "true"
                    onToggled: shell.setUiValue("keepSelection", checked ? "true" : "false")
                }
                StyledCheck {
                    objectName: "dragSelect"
                    text: qsTr("Drag across a list with the mouse to select (from a selected item: carry it to a playlist or the queue)")
                    checked: (shell.ui.dragSelect || "true") === "true"
                    onToggled: shell.setUiValue("dragSelect", checked ? "true" : "false")
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: qsTr("Select with Ctrl+click (one more), Shift+click (everything between), Ctrl+A (the whole list) or Shift+arrow keys. Esc clears it, with Undo.")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
            }
            SettingsGroup {
                key: "libraryFiles"
                title: qsTr("Files and tags")
                summary: qsTr("Ratings and covers in files, how many genres show")
                query: page.query
                StyledCheck {
                    objectName: "ratingsInFiles"
                    text: qsTr("Save star ratings in the songs' own tags too, so other players see them")
                    checked: userLib.ratingsInFiles
                    onToggled: userLib.setRatingsInFiles(checked)
                }
                StyledCheck {
                    objectName: "coversToFolder"
                    text: qsTr("Save covers you add as cover.jpg in the album's folder")
                    checked: metaEditor.coversToFolder
                    onToggled: metaEditor.setCoversToFolder(checked)
                }
                StyledCheck {
                    objectName: "embedCovers"
                    text: qsTr("Also embed covers you add in the songs themselves")
                    checked: metaEditor.embedCovers
                    onToggled: metaEditor.setEmbedCovers(checked)
                }
                StyledCheck {
                    objectName: "allGenresAlbums"
                    text: qsTr("Show every genre on album and artist pages (not just the main one)")
                    checked: shell.allGenresAlbums
                    onToggled: shell.setAllGenresAlbums(checked)
                }
                StyledCheck {
                    objectName: "allGenresSongs"
                    text: qsTr("Show every genre of the playing song (not just the main one)")
                    checked: shell.allGenresSongs
                    onToggled: shell.setAllGenresSongs(checked)
                }
            }
            SettingsGroup {
                key: "otherPlayer"
                title: qsTr("From another player")
                summary: qsTr("Strawberry, Clementine, Rhythmbox, MusicBee, iTunes, foobar2000")
                query: page.query
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: qsTr("Bring over play counts, skips, ratings and playlists from Strawberry, Clementine, Rhythmbox, MusicBee or iTunes. Songs are matched to your library; importing again never counts anything twice, and ratings you set here are kept.")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                Flow {
                    width: parent.width
                    spacing: 10
                    Repeater {
                        id: foundPlayers
                        model: userLib.otherPlayerLibraries()
                        PillButton {
                            required property var modelData
                            text: qsTr("Import from %1").arg(modelData.name)
                            enabled: !userLib.playerImportBusy
                            onClicked: userLib.importFromPlayer(modelData.path)
                        }
                    }
                    PillButton {
                        objectName: "importPlayerFile"
                        text: foundPlayers.count ? qsTr("Choose another library file…") : qsTr("Choose a library file…")
                        enabled: !userLib.playerImportBusy
                        onClicked: playerFile.open()
                    }
                    PillButton {
                        text: userLib.playerImportBusy ? qsTr("Importing…") : qsTr("foobar2000: play counts from tags")
                        enabled: !userLib.playerImportBusy
                        onClicked: userLib.importTagStatistics()
                    }
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: qsTr("MusicBee: turn on Preferences → Library → “make library and playlists accessible to other applications”, then choose its iTunes Music Library.xml. foobar2000 keeps its statistics to itself, so write them to the files with foo_playcount first; its playlists come over as M3U files.")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
                FileDialog {
                    id: playerFile
                    title: qsTr("Choose another player's library")
                    nameFilters: [qsTr("Player libraries (*.db *.xml)"), qsTr("All files (*)")]
                    onAccepted: userLib.importFromPlayer(selectedFile.toString())
                }
            }
            Flow {  // wraps in a narrow window
                width: parent.width
                objectName: "backupRow"
                spacing: 10
                Text {
                    textFormat: Text.PlainText
                    text: qsTr("Your likes, ratings, playlists, history, stations and shows")
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                PillButton { objectName: "exportBackup"; height: 32; text: qsTr("Back up…"); onClicked: backupSaveDlg.open() }
                PillButton { objectName: "importBackup"; height: 32; text: qsTr("Restore…"); onClicked: backupOpenDlg.open() }
            }
            FileDialog {
                id: backupSaveDlg
                title: qsTr("Back up your data")
                fileMode: FileDialog.SaveFile
                defaultSuffix: "hallucinate-backup"
                nameFilters: [qsTr("Hallucinate backup (*.hallucinate-backup)")]
                onAccepted: Nav.notify(shell.exportBackup(selectedFile.toString()))
            }
            FileDialog {
                id: backupOpenDlg
                title: qsTr("Restore from a backup")
                nameFilters: [qsTr("Hallucinate backup (*.hallucinate-backup)"), qsTr("All files (*)")]
                onAccepted: Nav.notify(shell.importBackup(selectedFile.toString()))
            }
        }
        SettingsSection {
            id: sec_servers
            objectName: "settings_servers"
            title: qsTr("Music servers")
            keywords: qsTr("server servers subsonic navidrome gonic airsonic ampache jellyfin emby stream remote network nas sync offline copy copies download keep")
            query: page.query
            visible: matches && shell.features.servers === true
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Songs on your Jellyfin server, or your Navidrome, Gonic, Airsonic or other Subsonic server, join your library and play like your own files. The sign-in stays in your system keyring (for Jellyfin, only the access token it gives). Songs from a server that can't be reached are skipped.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Repeater {
                model: servers.servers
                Row {
                    id: serverRow
                    required property var modelData
                    objectName: "server_" + modelData.id
                    spacing: 12
                    width: parent ? parent.width : 0
                    Column {
                        width: serverRow.width - syncButton.width - removeButton.width - (signInButton.visible ? signInButton.width + 12 : 0) - 24
                        anchors.verticalCenter: parent.verticalCenter
                        Text {
                            textFormat: Text.PlainText
                            width: parent.width
                            elide: Text.ElideRight
                            text: serverRow.modelData.name + "  ·  " + serverRow.modelData.user
                            color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
                        }
                        Text {
                            textFormat: Text.PlainText
                            width: parent.width
                            elide: Text.ElideRight
                            readonly property var m: serverRow.modelData
                            text: (m.status === "syncing" ? qsTr("Reading its songs…")
                                   : m.status === "checking" ? qsTr("Checking…")
                                   : m.status === "down" ? (m.error ? qsTr("Can't be reached: %1 (tried again every few minutes)").arg(m.error) : qsTr("Can't be reached (tried again every few minutes)"))
                                   : m.status === "error" ? m.error
                                   : Theme.counted(qsTr("%n song(s)", "", m.songs), m.songs)
                                     + (m.error ? "  ·  " + m.error : ""))
                                  + (m.secure ? "" : qsTr("  ·  not a secure link"))
                            color: m.status === "down" || m.status === "error" ? Theme.error : Theme.textDim
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                        }
                    }
                    PillButton {
                        id: signInButton
                        objectName: "signInAgain"
                        visible: serverRow.modelData.needsSignIn === true
                        anchors.verticalCenter: parent.verticalCenter
                        height: 32
                        primary: true
                        text: qsTr("Sign in again…")
                        onClicked: { signInDlg.serverId = serverRow.modelData.id; signInDlg.what = serverRow.modelData.name; signInDlg.open() }
                    }
                    PillButton {
                        id: syncButton
                        anchors.verticalCenter: parent.verticalCenter
                        height: 32
                        text: qsTr("Sync now")
                        enabled: !serverRow.modelData.busy
                        onClicked: servers.sync(serverRow.modelData.id)
                    }
                    PillButton {
                        id: removeButton
                        anchors.verticalCenter: parent.verticalCenter
                        height: 32
                        text: qsTr("Remove")
                        onClicked: { removeServerDlg.serverId = serverRow.modelData.id; removeServerDlg.what = serverRow.modelData.name; removeServerDlg.open() }
                    }
                }
            }
            PillButton {
                objectName: "addServer"
                primary: true
                text: qsTr("Add a server…")
                onClicked: addServerDlg.open()
            }
            // Songs kept on this computer, to play without the server (right-click an album, playlist or song)
            Text {
                textFormat: Text.PlainText
                objectName: "serverCopies"
                width: parent.width
                wrapMode: Text.WordWrap
                text: (serverCopies.count > 0
                       ? Theme.counted(qsTr("%n song(s) kept on this computer (%1): they play without the server, in offline mode too.", "", serverCopies.count), serverCopies.count).arg(Theme.fmtBytes(serverCopies.bytes))
                       : qsTr("To play a server's songs without it (on a train, say), right-click an album, playlist or song and choose Keep on this computer."))
                      + (serverCopies.waiting <= 0 ? "" : "  " + (serverCopies.busy ? qsTr("Downloading %1 more (%2% of the current one).").arg(Theme.num(serverCopies.waiting)).arg(Math.round(serverCopies.progress * 100))
                                                                 : shell.offlineMode ? qsTr("Downloading %1 more, once offline mode is off.").arg(Theme.num(serverCopies.waiting))
                                                                 : qsTr("Downloading %1 more.").arg(Theme.num(serverCopies.waiting))))
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            PillButton {
                objectName: "removeServerCopies"
                visible: serverCopies.count > 0 || serverCopies.waiting > 0
                text: qsTr("Remove all copies…")
                onClicked: removeCopiesDlg.open()
            }
            ConfirmDialog {
                id: removeCopiesDlg
                title: qsTr("Remove the copies on this computer?")
                confirmText: qsTr("Remove copies")
                destructive: true
                body: qsTr("The songs stay in your library and on the server; they stream again instead of playing from this computer.")
                onAccepted: serverCopies.removeAll()
            }
            Dialog {
                id: signInDlg
                objectName: "signInDialog"
                property string serverId: ""
                property string what: ""
                parent: Overlay.overlay
                anchors.centerIn: parent
                modal: true
                width: Math.min(420, (parent ? parent.width : 420) - 40)
                title: qsTr("Sign in to %1 again").arg(what)
                standardButtons: Dialog.Ok | Dialog.Cancel
                onAboutToShow: newPassword.text = ""
                onAccepted: servers.signInAgain(serverId, newPassword.text)
                Column {
                    width: signInDlg.availableWidth
                    spacing: 10
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("The server turned down the saved sign-in. Enter the password again: your playlists, plays and ratings for its songs stay as they are.")
                        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                    }
                    TextField {
                        id: newPassword
                        width: parent.width
                        echoMode: TextInput.Password
                        placeholderText: qsTr("Password")
                        placeholderTextColor: Theme.textDim
                        color: Theme.text
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                        background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: newPassword.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                        onAccepted: signInDlg.accept()
                        Accessible.name: qsTr("Password")
                    }
                }
            }
            ConfirmDialog {
                id: removeServerDlg
                property string serverId: ""
                property string what: ""
                title: qsTr("Remove this server?")
                confirmText: qsTr("Remove server")
                destructive: true
                body: qsTr("Its songs leave your library and its password leaves the keyring. Nothing on the server changes.")
                onAccepted: servers.removeServer(serverId)
            }
            Dialog {
                id: addServerDlg
                objectName: "addServerDialog"
                parent: Overlay.overlay
                anchors.centerIn: parent
                width: Math.min(460, (parent ? parent.width : 460) - 40)
                modal: true
                title: qsTr("Add a music server")
                standardButtons: Dialog.Ok | Dialog.Cancel
                property string kind: "subsonic"
                readonly property bool ready: serverLink.text.trim().length > 0 && serverUser.text.trim().length > 0
                                              && serverPassword.text.length > 0
                function okLater() { var b = standardButton(Dialog.Ok); if (b) b.enabled = ready }
                onReadyChanged: okLater()
                onOpened: { kind = "subsonic"; serverLink.text = ""; serverUser.text = ""; serverPassword.text = ""; serverName.text = ""; okLater(); serverLink.forceActiveFocus() }
                onAccepted: {
                    servers.addServer(serverLink.text.trim(), serverUser.text.trim(), serverPassword.text, serverName.text.trim(), kind)
                    serverPassword.text = ""  // don't keep it in the field
                }
                onRejected: serverPassword.text = ""
                Column {
                    width: addServerDlg.availableWidth
                    spacing: 10
                    Row {
                        spacing: 6
                        Chip {
                            objectName: "serverKindSubsonic"
                            text: qsTr("Subsonic (Navidrome, Gonic…)")
                            selected: addServerDlg.kind === "subsonic"
                            onClicked: addServerDlg.kind = "subsonic"
                        }
                        Chip {
                            objectName: "serverKindJellyfin"
                            text: qsTr("Jellyfin")
                            selected: addServerDlg.kind === "jellyfin"
                            onClicked: addServerDlg.kind = "jellyfin"
                        }
                    }
                    TextField {
                        id: serverLink; objectName: "serverLink"; width: parent.width; selectByMouse: true
                        placeholderText: "Server link (https://music.example.com)"; Accessible.name: qsTr("Server link")
                        onAccepted: if (addServerDlg.ready) addServerDlg.accept()
                    }
                    Text {
                        visible: serverLink.text.trim().length > 0 && !servers.linkIsSecure(serverLink.text)
                        textFormat: Text.PlainText
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("This isn't a secure (https) link and isn't on your home network: anyone on the networks in between could see what you play and reuse your sign-in.")
                        color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                    }
                    TextField {
                        id: serverUser; objectName: "serverUser"; width: parent.width; selectByMouse: true
                        placeholderText: qsTr("User name"); Accessible.name: qsTr("User name")
                        onAccepted: if (addServerDlg.ready) addServerDlg.accept()
                    }
                    TextField {
                        id: serverPassword; objectName: "serverPassword"; width: parent.width
                        echoMode: TextInput.Password; placeholderText: qsTr("Password"); Accessible.name: qsTr("Password")
                        onAccepted: if (addServerDlg.ready) addServerDlg.accept()
                    }
                    TextField {
                        id: serverName; width: parent.width; selectByMouse: true
                        placeholderText: qsTr("Name (optional)"); Accessible.name: qsTr("Server name")
                        onAccepted: if (addServerDlg.ready) addServerDlg.accept()
                    }
                }
            }
        }
        SettingsSection {
            id: sec_casting
            objectName: "settings_casting"
            title: qsTr("Casting")
            keywords: qsTr("cast casting chromecast google nest home speaker tv television dlna upnp renderer receiver kodi sonos play on another device network wifi firewall port original bit-perfect processed equalizer sound")
            query: page.query
            visible: matches && shell.features.casting !== false
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Play your music on a Chromecast, a Google or Nest speaker, or a TV, receiver or speaker that takes DLNA/UPnP. Pick one with the cast button beside the volume; your queue, likes and play counts stay here, and Hallucinate's controls, media keys and phone remote all control the device.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Row {
                visible: casting.active
                spacing: 12
                Icon { name: "cast"; width: 18; height: 18; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                Text {
                    textFormat: Text.PlainText
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Playing on %1").arg(casting.deviceName)
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                }
                PillButton { text: qsTr("Play here instead"); onClicked: casting.stopCasting() }
            }
            OptionCombo {
                objectName: "castSending"
                label: qsTr("What to send")
                values: ["original", "processed"]
                labels: [qsTr("The original files"), qsTr("Hallucinate's sound")]
                current: casting.sending
                onPicked: function (v) { casting.setSending(v) }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: casting.sending === "processed"
                      ? qsTr("Songs are played through your ReplayGain, equalizer, headphone correction and crossfeed first, then sent as lossless WAV (16-bit, up to 48 kHz). They take a moment to get ready, and the next song is got ready while one plays. Music servers' songs and radio are sent as they are.")
                      : qsTr("Songs are sent untouched, bit for bit, and the device plays them itself; your equalizer and crossfeed don't apply. Songs the device can't play as they are (WavPack, APE, ALAC on a Chromecast, very high sample rates) and CUE sheet songs are converted to WAV for it.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Row {
                spacing: 12
                Text { textFormat: Text.PlainText; text: qsTr("Port"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); height: 36; verticalAlignment: Text.AlignVCenter }
                TextField {
                    id: castPort
                    objectName: "castPort"
                    Accessible.name: qsTr("Port")
                    width: 90; height: 36
                    text: String(casting.port)
                    validator: IntValidator { bottom: 1024; top: 65535 }
                    inputMethodHints: Qt.ImhDigitsOnly
                    color: Theme.text
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                    selectByMouse: true
                    onEditingFinished: if (acceptableInput) casting.setPort(parseInt(text)); else text = String(casting.port)
                    background: Rectangle { radius: Theme.round(8); color: Theme.surface; border.color: castPort.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("The device fetches each song from this computer on this port, and only the device you picked can, only while you're casting. If nothing plays, your firewall may be blocking it: allow the port for your home network. For example, on Fedora, Bazzite and other systems with firewalld:")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            TextEdit {
                width: parent.width
                readOnly: true; selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                textFormat: TextEdit.PlainText
                text: "sudo firewall-cmd --permanent --add-port=" + casting.port + "/tcp && sudo firewall-cmd --reload"  // i18n: keep
                color: Theme.text; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSize(12)
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("or with ufw (Ubuntu, Mint):")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            TextEdit {
                width: parent.width
                readOnly: true; selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                textFormat: TextEdit.PlainText
                text: "sudo ufw allow " + casting.port + "/tcp"  // i18n: keep
                color: Theme.text; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
        SettingsSection {
            id: sec_remote
            objectName: "settings_remote"
            title: qsTr("Remote & web")
            keywords: qsTr("remote phone web browser interface control pair pairing device devices network lan wifi headless tablet handoff hand over another computer")
            query: page.query
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Control Hallucinate from your phone, a tablet or a browser: play, pause and skip, the queue, search and your library. Each device pairs once with a code from here, and can be removed any time. A remote can't change your files or settings.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            StyledCheck {
                objectName: "remoteOn"
                text: qsTr("Turn on the web interface and remote")
                checked: webRemote.on
                onToggled: webRemote.setOn(checked)
            }
            StyledCheck {
                objectName: "remoteNetwork"
                enabled: webRemote.on
                text: qsTr("Let other devices on your network connect (your phone on the same Wi-Fi). Only on networks you trust, like your home's")
                checked: webRemote.network
                onToggled: webRemote.setNetwork(checked)
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                visible: webRemote.problem.length > 0
                text: webRemote.problem
                color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Column {
                visible: webRemote.isRunning
                width: parent.width
                spacing: 8
                Text {
                    textFormat: Text.PlainText
                    text: webRemote.network ? qsTr("Open one of these on your phone or another computer:") : qsTr("Open this in a browser on this computer:")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                Repeater {
                    model: webRemote.links
                    TextInput {  // selectable, to copy
                        required property string modelData
                        objectName: "remoteLink"
                        text: modelData
                        readOnly: true
                        selectByMouse: true
                        color: Theme.accent
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold
                    }
                }
                Flow {
                    width: parent.width
                    spacing: 10
                    PillButton {
                        objectName: "pairDevice"
                        primary: true
                        text: webRemote.code.length ? qsTr("New code") : qsTr("Pair a device…")
                        onClicked: webRemote.pairDevice()
                    }
                    PillButton {
                        text: qsTr("Open in browser")
                        onClicked: Qt.openUrlExternally(webRemote.links[webRemote.links.length - 1]
                                                        + (webRemote.code.length ? "#pair=" + webRemote.code : ""))
                    }
                }
                GlassPanel {
                    visible: webRemote.code.length > 0
                    width: Math.min(parent.width, 460)
                    height: codeCol.implicitHeight + 32
                    Column {
                        id: codeCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
                        spacing: 6
                        Text {
                            textFormat: Text.PlainText
                            text: qsTr("Enter this code on the device")
                            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                        }
                        Text {
                            textFormat: Text.PlainText
                            objectName: "pairingCode"
                            text: webRemote.code.replace(/(\d{3})(\d{3})/, "$1 $2")
                            color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(40)) * Theme.displayScale; font.weight: Font.Bold
                            font.letterSpacing: 4
                        }
                        Text {
                            textFormat: Text.PlainText
                            readonly property int minutes: Math.max(0, Math.ceil(webRemote.codeSeconds / 60))
                            text: Theme.counted(qsTr("Works once, for %n more minute(s)", "", minutes), minutes)
                            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                        }
                        PillButton { height: 30; text: qsTr("Cancel"); onClicked: webRemote.cancelCode() }
                    }
                }
            }
            SettingsGroup {
                key: "remoteDevices"
                title: qsTr("Paired devices")
                summary: webRemote.pairedDevices.length ? Theme.counted(qsTr("%n device(s)", "", webRemote.pairedDevices.length), webRemote.pairedDevices.length) : qsTr("None yet")
                query: page.query
                Repeater {
                    model: webRemote.pairedDevices
                    Row {
                        required property var modelData
                        spacing: 12
                        width: parent ? parent.width : 0
                        Column {
                            width: parent.width - forgetButton.width - 12
                            anchors.verticalCenter: parent.verticalCenter
                            // (wrapped to the room beside the button, however narrow: #133)
                            Text { width: parent.width; wrapMode: Text.Wrap; textFormat: Text.PlainText; text: modelData.name; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold }
                            Text {
                                width: parent.width
                                wrapMode: Text.Wrap
                                textFormat: Text.PlainText
                                text: qsTr("Paired %1  ·  last used %2").arg(Theme.date(new Date(modelData.paired * 1000), "short"))
                                      .arg(Qt.locale().toString(new Date(modelData.seen * 1000), Locale.ShortFormat))
                                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                            }
                        }
                        PillButton { id: forgetButton; height: 30; text: qsTr("Remove"); anchors.verticalCenter: parent.verticalCenter; onClicked: webRemote.forgetDevice(modelData.id) }
                    }
                }
                PillButton {
                    visible: webRemote.pairedDevices.length > 1
                    text: qsTr("Remove all devices")
                    onClicked: webRemote.forgetAllDevices()
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: qsTr("Lost a phone, or not sure who has access? Remove the device here: it can't connect again without a new code. Port: %1.").arg(webRemote.portNumber)
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
            }
            // Other computers running Hallucinate this one can hand what's playing over to (the cast menu)
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Other computers running Hallucinate: hand what's playing over to one from the cast button beside the volume (Hand over to another computer). It carries on there, playing songs from its own library where it has them and the rest from this computer. Pair a computer from that menu with the code it shows here.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Repeater {
                model: handoff.computers.filter(c => c.paired)
                Row {
                    required property var modelData
                    spacing: 12
                    Icon { name: "computer"; width: 16; height: 16; color: Theme.textDim; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        textFormat: Text.PlainText
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.name + "  ·  " + modelData.host
                        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                    }
                    PillButton { text: qsTr("Forget"); onClicked: handoff.forget(modelData.id) }
                }
            }
        }
        SettingsSection {
            id: sec_sharing
            objectName: "settings_sharing"
            title: qsTr("Online & privacy")
            keywords: qsTr("offline mode internet network privacy connection lyrics lrclib genres bios biography wikipedia discogs token musicbrainz last.fm tags similar artists discover")
            query: page.query
            StyledCheck {
                objectName: "offlineMode"
                text: qsTr("Offline mode")
                checked: shell.offlineMode
                onToggled: shell.setOfflineMode(checked)
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("With offline mode on, Hallucinate makes no internet connections at all: no lyrics, cover, genre or bio lookups, internet radio, podcast updates, scrobbling, headphone EQ downloads or update checks. Scrobbles wait and are sent when you turn it off. Discord status talks only to the Discord app on this computer, so it has its own switch under Scrobbling & sharing (it shows no cover art while offline).")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            StyledCheck {
                objectName: "lyricsOnline"
                visible: shell.features.lyrics !== false
                text: qsTr("Find lyrics online for songs that have none (asks LRCLIB with the artist, title and album)")
                checked: lyricsCtl.onlineLookup
                onToggled: lyricsCtl.setOnlineLookup(checked)
            }
            StyledCheck {
                objectName: "fetchBios"
                text: qsTr("Look up an artist's bio when their page opens (sends the artist and one of their albums)")
                checked: sources.fetchBios
                onToggled: sources.setFetchBios(checked)
            }
            Flow {
                width: parent.width
                spacing: 12
                Text { textFormat: Text.PlainText; text: qsTr("Bios come from"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "bioSource"
                    width: 220
                    readonly property var names: ["", "Wikipedia", "Last.fm", "Discogs"]  // i18n: keep (the keys)
                    model: [qsTr("Wikipedia, then Last.fm, then Discogs"), qsTr("Wikipedia only"), sources.lastfmAvailable ? qsTr("Last.fm only") : qsTr("Last.fm only (not set up)"),
                            sources.discogsConnected ? qsTr("Discogs only") : qsTr("Discogs only (not set up)")]
                    selection: names.indexOf(sources.bioSource)
                    onActivated: function (i) { sources.setBioSource(names[i]) }
                    Accessible.name: qsTr("Where artist bios come from")
                }
            }
            StyledCheck {
                objectName: "fetchSimilar"
                text: qsTr("Show similar artists from Last.fm on an artist's page (sends the artist's name)")
                      + (sources.lastfmAvailable ? "" : qsTr(". Needs the Last.fm API key, under Scrobbling & sharing"))
                enabled: sources.lastfmAvailable || checked
                checked: sources.fetchSimilar
                onToggled: sources.setFetchSimilar(checked)
            }
            SettingsGroup {
                key: "genreSources"
                title: qsTr("Genre and bio sources")
                summary: qsTr("Discogs, Last.fm tags")
                query: page.query
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: qsTr("Genres are looked up on MusicBrainz, and also on Discogs and Last.fm when they're set up. Only albums without a genre are looked up, and nothing is written until you've checked it. Bios come from Wikipedia (found through MusicBrainz), Last.fm or Discogs; one you write yourself on an artist's page is always shown instead.")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                StyledCheck {
                    objectName: "genresFromLastfm"
                    text: sources.lastfmAvailable ? qsTr("Also use Last.fm's tags for genres (only the tags that are real genres)")
                                                  : qsTr("Also use Last.fm's tags for genres (needs the Last.fm API key below)")
                    enabled: sources.lastfmAvailable
                    checked: sources.genresFromLastfm
                    onToggled: sources.setGenresFromLastfm(checked)
                }
                StyledCheck {
                    objectName: "genresFromDiscogs"
                    text: qsTr("Also use Discogs' genres and styles")
                    enabled: sources.discogsConnected
                    checked: sources.genresFromDiscogs
                    onToggled: sources.setGenresFromDiscogs(checked)
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: sources.discogsConnected
                          ? (sources.discogsUser ? qsTr("Discogs: connected as %1. The token is kept in the system keyring.").arg(sources.discogsUser)
                             : qsTr("Discogs: connected. The token is kept in the system keyring."))
                          : qsTr("Discogs needs a personal access token: make one at discogs.com → Settings → Developers, then paste it here. It's kept in the system keyring.")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                Flow {
                    width: parent.width
                    spacing: 10
                    visible: !sources.discogsConnected
                    TextField {
                        id: discogsToken
                        objectName: "discogsToken"
                        width: Math.min(340, parent.width)
                        echoMode: TextInput.Password
                        placeholderText: qsTr("Discogs personal access token")
                        placeholderTextColor: Theme.textDim
                        color: Theme.text
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                        background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: discogsToken.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                        onAccepted: sources.connectDiscogs(text)
                        Accessible.name: qsTr("Discogs personal access token")
                    }
                    PillButton {
                        objectName: "connectDiscogs"
                        text: sources.discogsBusy ? qsTr("Checking…") : qsTr("Connect Discogs")
                        enabled: !sources.discogsBusy && discogsToken.text.trim().length > 0 && !shell.offlineMode
                        onClicked: { sources.connectDiscogs(discogsToken.text); discogsToken.text = "" }
                    }
                }
                PillButton {
                    objectName: "forgetDiscogs"
                    visible: sources.discogsConnected
                    text: qsTr("Disconnect Discogs")
                    onClicked: sources.forgetDiscogs()
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    visible: sources.discogsStatus.length > 0
                    text: sources.discogsStatus
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
            }
        }
        SettingsSection {
            id: sec_scrobbling
            objectName: "settings_scrobbling"
            title: qsTr("Scrobbling & sharing")
            keywords: qsTr("last.fm lastfm listenbrainz maloja koito multi-scrobbler self-hosted server scrobble scrobbling loves discord rich presence history import account radio stations podcasts episodes queued when half percent threshold point listen end")
            query: page.query
            Text { text: qsTr("Last.fm"); color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold; textFormat: Text.PlainText }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Sends now-playing updates, and scrobbles after half a song or four minutes, whichever comes first. Last.fm asks each person for an API key of their own; it and your sign-in stay in the system keyring.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            SettingsGroup {
                id: lastfmKeyGroup
                key: "lastfmKey"
                title: scrobbler.configured ? qsTr("Last.fm API key (saved)") : qsTr("Last.fm API key")
                summary: scrobbler.configured ? qsTr("Change it") : qsTr("Needed before connecting")
                query: page.query
                Component.onCompleted: if (!scrobbler.configured) open = true
                Flow {  // wraps in a narrow window
                    width: parent.width
                    spacing: 10
                    TextField {
                        id: apiKey
                        width: Math.min(250, parent.width); height: 38
                        placeholderText: scrobbler.configured ? qsTr("Saved (type a new one to replace it)") : qsTr("Last.fm API key")
                        color: Theme.text; placeholderTextColor: Theme.textDim
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                        background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: apiKey.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                    }
                    TextField {
                        id: apiSecret
                        width: Math.min(250, parent.width); height: 38
                        placeholderText: scrobbler.configured ? qsTr("Saved") : qsTr("Last.fm API secret")
                        echoMode: TextInput.Password
                        color: Theme.text; placeholderTextColor: Theme.textDim
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                        background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: apiSecret.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                    }
                    PillButton {
                        text: qsTr("Get API credentials")
                        onClicked: Qt.openUrlExternally("https://www.last.fm/api/account/create")
                    }
                    PillButton {
                        text: qsTr("Save API credentials")
                        primary: true
                        enabled: apiKey.text.length > 0 && apiSecret.text.length > 0 && !scrobbler.busy
                        onClicked: {
                            scrobbler.setApiCredentials(apiKey.text, apiSecret.text)
                            apiSecret.text = ""
                        }
                    }
                }
            }
            Flow {  // wraps in a narrow window
                width: parent.width
                spacing: 10
                PillButton {
                    visible: !scrobbler.connected
                    primary: true
                    text: scrobbler.busy ? qsTr("Connecting…") : qsTr("Connect Last.fm")
                    enabled: scrobbler.configured && !scrobbler.busy  // offline, it says why instead
                    onClicked: scrobbler.connectAccount()
                }
                PillButton {
                    visible: scrobbler.authorizationUrl.length > 0 && !scrobbler.connected
                    text: qsTr("Open authorization")
                    onClicked: scrobbler.openAuthorizationUrl()
                }
                PillButton {
                    visible: scrobbler.authorizationUrl.length > 0 && !scrobbler.connected
                    primary: true
                    text: qsTr("I've authorized")
                    enabled: !scrobbler.busy
                    onClicked: scrobbler.completeAuthorization()
                }
                PillButton {
                    visible: scrobbler.connected
                    text: qsTr("Disconnect Last.fm")
                    enabled: !scrobbler.busy
                    onClicked: scrobbler.disconnectAccount()
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: scrobbler.status + (scrobbler.pendingCount > 0 ? " · " + qsTr("%1 waiting to be sent").arg(Theme.num(scrobbler.pendingCount)) : "")
                      + (scrobbler.rejectedCount > 0 ? " · " + qsTr("%1 turned down by Last.fm").arg(Theme.num(scrobbler.rejectedCount)) : "")
                      + (scrobbler.lastError ? " · " + qsTr("last try: %1").arg(scrobbler.lastError) : "")
                color: scrobbler.connected ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
                wrapMode: Text.WordWrap
            }
            PillButton {
                objectName: "scrobblerRetryNow"
                visible: scrobbler.pendingCount > 0 && scrobbler.connected && !shell.offlineMode
                height: 32
                text: qsTr("Send now")
                onClicked: scrobbler.retryNow()
            }
            StyledCheck {
                objectName: "lastfmNowPlaying"
                visible: scrobbler.connected
                text: qsTr("Show \u201cScrobbling now\u201d on Last.fm while a song plays (the scrobble itself waits for the point below)")
                checked: scrobbler.nowPlaying
                onToggled: scrobbler.setNowPlaying(checked)
            }
            Flow {
                visible: scrobbler.connected
                width: parent.width
                spacing: 10
                Text { textFormat: Text.PlainText; text: qsTr("Scrobble a song after"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "scrobblePoint"
                    readonly property var points: ["rule", "25", "50", "75", "90", "end"]
                    width: 300
                    model: [qsTr("Half way, or 4 minutes (Last.fm's rule)"), qsTr("A quarter of the way"), qsTr("Half way, however long"),
                            qsTr("Three quarters of the way"), qsTr("90% of the way"), qsTr("At the end")]
                    selection: Math.max(0, points.indexOf(scrobbler.listenPoint))
                    onActivated: scrobbler.setListenPoint(points[currentIndex])
                    Accessible.name: qsTr("Scrobble a song after")
                }
            }
            StyledCheck {
                objectName: "syncLoves"
                visible: scrobbler.connected && shell.features.liked !== false
                text: qsTr("Liking a song loves it on Last.fm (and unliking unloves it)")
                checked: scrobbler.syncLoves
                onToggled: scrobbler.setSyncLoves(checked)
            }
            PillButton {
                objectName: "importLoves"
                visible: scrobbler.connected && shell.features.liked !== false
                text: scrobbler.lovesBusy ? qsTr("Fetching your loves…") : qsTr("Like the songs I've loved on Last.fm")
                enabled: !scrobbler.lovesBusy
                onClicked: scrobbler.importLoves()
            }
            OfflineNote { visible: shell.offlineMode && (scrobbler.configured || scrobbler.connected); what: qsTr("Last.fm") }
            Text { text: qsTr("ListenBrainz"); color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold; textFormat: Text.PlainText }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Connect with your ListenBrainz user token to send now-playing updates and listens. The token stays in the system keyring; listens that can't be sent wait and are tried again.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            // a server of your own that speaks the ListenBrainz API, instead of listenbrainz.org
            StyledCheck {
                id: lbOwnServer
                objectName: "listenbrainzOwnServer"
                visible: !listenbrainz.connected
                text: qsTr("Use another server that speaks the ListenBrainz API (Maloja, Koito, Multi-Scrobbler…)")
                checked: listenbrainz.server.length > 0
            }
            Column {
                visible: lbOwnServer.checked && !listenbrainz.connected
                width: parent.width
                leftPadding: 28
                spacing: 6
                TextField {
                    id: lbServer
                    objectName: "listenbrainzServer"
                    width: Math.min(420, parent.width - 28); height: 38
                    text: listenbrainz.server
                    placeholderText: "https://maloja.example.com/apis/listenbrainz"
                    color: Theme.text; placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                    selectByMouse: true
                    background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: lbServer.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width - 28
                    wrapMode: Text.WordWrap
                    // a token over plain http can be read along the way, unless the server is on this computer or at home
                    readonly property bool plain: /^http:\/\//i.test(lbServer.text.trim())
                        && !/^http:\/\/(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[?::1)/i.test(lbServer.text.trim())
                    text: plain ? "This address isn't encrypted (http://): the token and your listens can be read on the way. Use https:// unless the server is on your own network."
                                : qsTr("The server's ListenBrainz API address and a token from it. Maloja and Koito serve it at /apis/listenbrainz.")
                    color: plain ? Theme.error : Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
            }
            Flow {  // wraps in a narrow window
                width: parent.width
                spacing: 10
                TextField {
                    id: lbToken
                    width: Math.min(320, parent.width); height: 38
                    visible: !listenbrainz.connected
                    placeholderText: qsTr("ListenBrainz user token")
                    echoMode: TextInput.Password
                    color: Theme.text; placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                    background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: lbToken.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                }
                PillButton {
                    visible: !listenbrainz.connected
                    primary: true
                    text: listenbrainz.busy ? qsTr("Validating…") : lbOwnServer.checked ? qsTr("Connect") : qsTr("Connect ListenBrainz")
                    enabled: lbToken.text.length > 0 && !listenbrainz.busy && (!lbOwnServer.checked || lbServer.text.trim().length > 0)
                    onClicked: { listenbrainz.connectToken(lbToken.text, lbOwnServer.checked ? lbServer.text : ""); lbToken.text = "" }
                }
                PillButton {
                    visible: !listenbrainz.connected && !lbOwnServer.checked
                    text: qsTr("Get a token")
                    onClicked: Qt.openUrlExternally("https://listenbrainz.org/settings/")
                }
                PillButton {
                    visible: listenbrainz.connected
                    text: qsTr("Disconnect ListenBrainz")
                    enabled: !listenbrainz.busy
                    onClicked: listenbrainz.disconnectAccount()
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: listenbrainz.status + (listenbrainz.pendingCount > 0 ? " · " + qsTr("%1 waiting to be sent").arg(Theme.num(listenbrainz.pendingCount)) : "")
                      + (listenbrainz.rejectedCount > 0 ? " · " + qsTr("%1 turned down by ListenBrainz").arg(Theme.num(listenbrainz.rejectedCount)) : "")
                      + (listenbrainz.lastError ? " · " + qsTr("last try: %1").arg(listenbrainz.lastError) : "")
                color: listenbrainz.connected ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); wrapMode: Text.WordWrap
            }
            OfflineNote { visible: shell.offlineMode; what: qsTr("ListenBrainz") }
            StyledCheck {
                objectName: "listenbrainzNowPlaying"
                visible: listenbrainz.connected
                text: qsTr("Show \u201cPlaying now\u201d on ListenBrainz while a song plays (the listen itself waits for the point below)")
                checked: listenbrainz.nowPlaying
                onToggled: listenbrainz.setNowPlaying(checked)
            }
            Flow {
                visible: listenbrainz.connected
                width: parent.width
                spacing: 10
                Text { textFormat: Text.PlainText; text: qsTr("Count a listen after"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "listenPoint"
                    readonly property var points: ["rule", "25", "50", "75", "90", "end"]
                    width: 300
                    model: [qsTr("Half way, or 4 minutes (Last.fm's rule)"), qsTr("A quarter of the way"), qsTr("Half way, however long"),
                            qsTr("Three quarters of the way"), qsTr("90% of the way"), qsTr("At the end")]
                    selection: Math.max(0, points.indexOf(listenbrainz.listenPoint))
                    onActivated: listenbrainz.setListenPoint(points[currentIndex])
                    Accessible.name: qsTr("Count a listen after")
                }
            }
            PillButton {
                objectName: "listenbrainzRetryNow"
                visible: listenbrainz.pendingCount > 0 && listenbrainz.connected && !shell.offlineMode
                height: 32
                text: qsTr("Send now")
                onClicked: listenbrainz.retryNow()
            }
            StyledCheck {
                objectName: "scrobbleStations"
                visible: shell.features.stations !== false && (scrobbler.connected || listenbrainz.connected)
                text: qsTr("Count songs heard on internet radio on Last.fm and ListenBrainz")
                checked: stations.scrobble
                onToggled: stations.setScrobble(checked)
            }
            StyledCheck {
                objectName: "scrobblePodcasts"
                visible: shell.features.podcasts !== false && (scrobbler.connected || listenbrainz.connected)
                text: qsTr("Count podcast episodes on Last.fm and ListenBrainz (as the show and the episode's title)")
                checked: podcasts.scrobble
                onToggled: podcasts.setScrobble(checked)
            }
            SettingsGroup {
                key: "historyImport"
                title: qsTr("Import listening history")
                summary: qsTr("From ListenBrainz or Last.fm")
                query: page.query
                Flow {  // wraps in a narrow window
                    width: parent.width
                    spacing: 10
                    StyledCombo {
                        id: historySource
                        width: 150
                        model: [qsTr("ListenBrainz"), qsTr("Last.fm")]
                    }
                    TextField {
                        id: historyUser
                        width: Math.min(260, parent.width); height: 38
                        placeholderText: historySource.currentIndex === 0 && listenbrainz.connected ? qsTr("Username (blank = connected account)") : qsTr("Username")
                        color: Theme.text; placeholderTextColor: Theme.textDim
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                        background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: historyUser.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                    }
                    PillButton {
                        primary: true
                        text: listenbrainz.importing ? qsTr("Importing…") : qsTr("Import history")
                        enabled: !shell.offlineMode && !listenbrainz.importing
                                 && (historyUser.text.length > 0 || (historySource.currentIndex === 0 && listenbrainz.connected))
                                 && (historySource.currentIndex === 0 || scrobbler.configured)  // Last.fm needs your API key
                        onClicked: listenbrainz.importHistory(historySource.currentIndex === 0 ? "listenbrainz" : "lastfm", historyUser.text)
                    }
                }
                Text {
                    textFormat: Text.PlainText
                    visible: listenbrainz.importStatus.length > 0
                    width: parent.width
                    text: listenbrainz.importStatus
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); wrapMode: Text.WordWrap
                }
            }
            Text { text: qsTr("Discord"); color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold; textFormat: Text.PlainText }
            StyledCheck { objectName: "discordEnabled"; text: qsTr("Show what I'm listening to on my Discord profile"); checked: discord.enabled; onToggled: discord.setEnabled(checked) }
            Column {
                visible: discord.enabled
                width: parent.width
                spacing: 12
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: qsTr("Create an application at discord.com/developers, paste its Application ID below and upload your icon as an art asset named “hallucinate”. Status: %1").arg(discord.status)
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
                TextField {
                    id: discordAppId
                    width: Math.min(320, parent.width)
                    placeholderText: qsTr("Discord application ID")
                    selectByMouse: true
                    color: Theme.text
                    placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                    background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: parent.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                    onEditingFinished: discord.setAppId(text)
                    Component.onCompleted: text = discord.appId
                    Connections { target: discord; function onChanged() { if (!discordAppId.activeFocus) discordAppId.text = discord.appId } }
                    Accessible.name: qsTr("Discord application ID")
                }
                StyledCheck { text: qsTr("Hide when paused"); checked: discord.hidePaused; onToggled: discord.setPref("hidePaused", checked) }
                StyledCheck { text: qsTr("Hide cover art"); checked: discord.hideCover; onToggled: discord.setPref("hideCover", checked) }
                StyledCheck { text: qsTr("Privacy mode (don't share track details)"); checked: discord.privacy; onToggled: discord.setPref("privacy", checked) }
            }
        }
        SettingsSection {
            id: sec_desktop
            objectName: "settings_desktop"
            title: qsTr("Desktop")
            keywords: qsTr("tray notifications focus close quit minimize exit background mini player title bar window frame decorations frameless maximize buttons left right side start page open on rounded corners round")
            query: page.query
            StyledCheck {
                visible: shell.trayAvailable
                text: qsTr("Show system tray icon")
                checked: shell.trayEnabled
                onToggled: shell.setTrayEnabled(checked)
            }
            StyledCheck {
                objectName: "customTitleBar"
                text: qsTr("Use Hallucinate's own title bar, built into the window")
                checked: shell.customTitleBar
                onToggled: shell.setCustomTitleBar(checked)
            }
            StyledCheck {
                objectName: "roundWindow"
                visible: shell.customTitleBar
                leftPadding: 28
                text: qsTr("Round the window's corners, like the panels inside it")
                checked: shell.ui.roundWindow !== "0"
                onToggled: shell.setUiValue("roundWindow", checked ? "1" : "0")
            }
            StyledCheck {
                objectName: "titleBarMinimize"
                visible: shell.customTitleBar
                leftPadding: 28
                text: qsTr("Show the minimize button")
                checked: shell.titleBarMinimize
                onToggled: shell.setTitleBarMinimize(checked)
            }
            Flow {
                visible: shell.customTitleBar
                width: parent.width
                spacing: 10
                leftPadding: 28
                Text { textFormat: Text.PlainText; text: qsTr("Buttons on the"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "titleBarSide"
                    width: 200
                    model: [qsTr("Right"), qsTr("Left")]
                    selection: shell.titleBarSide === "left" ? 1 : 0
                    onActivated: shell.setTitleBarSide(currentIndex === 1 ? "left" : "right")  // i18n: keep
                    Accessible.name: qsTr("Title bar buttons side")
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: shell.customTitleBar
                      ? qsTr("Drag the top of the window (beside the search) to move it, double-click it to maximize. Turn this off for your system's own title bar.")
                      : qsTr("Your system draws the window's title bar.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Row {
                spacing: 12
                Text { anchors.verticalCenter: parent.verticalCenter; text: qsTr("When I close the window"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "closeAction"
                    width: 250
                    readonly property var actions: ["ask", "quit"].concat(shell.canMinimize ? ["minimize"] : [])
                                                                  .concat(["tray"])
                    readonly property var labels: ({ ask: qsTr("Ask every time"), quit: qsTr("Quit"), minimize: qsTr("Minimize"),
                                                     tray: qsTr("Keep playing in the background") })
                    model: actions.map(a => labels[a])
                    selection: actions.indexOf(shell.closeAction)
                    onActivated: shell.setCloseAction(actions[currentIndex])
                }
            }
            Text {
                textFormat: Text.PlainText
                visible: !shell.canMinimize
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Your window manager has no minimize, so the choices are quitting or keeping it playing in the background (in the tray when your bar shows tray icons; otherwise open Hallucinate again to bring the window back).")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            StyledCheck {
                visible: Qt.platform.os === "linux" || shell.trayAvailable
                text: qsTr("Show desktop notifications when tracks change")
                checked: shell.desktopNotifications
                onToggled: shell.setDesktopNotifications(checked)
            }
            StyledCheck {
                objectName: "notifyAlways"
                visible: shell.desktopNotifications
                leftPadding: 28
                text: qsTr("Even while Hallucinate's window is in front (off: only when you're elsewhere)")
                checked: shell.notifyAlways
                onToggled: shell.setNotifyAlways(checked)
            }
            Flow {
                width: parent.width
                spacing: 10
                Text { textFormat: Text.PlainText; text: qsTr("Open on"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "startPage"
                    readonly property var pages: ["home", "last", "albums", "artists", "genres", "songs", "folders", "liked", "stats", "history"]
                    width: 220
                    model: [qsTr("Home"), qsTr("The page I left it on"), qsTr("Albums"), qsTr("Artists"), qsTr("Genres"), qsTr("Songs"), qsTr("Folders"), qsTr("Liked Songs"), qsTr("Stats"), qsTr("History")]
                    selection: Math.max(0, pages.indexOf(shell.startPage))
                    onActivated: shell.setStartPage(pages[currentIndex])
                    Accessible.name: qsTr("Page Hallucinate opens on")
                }
            }
            Flow {
                visible: shell.appImageLauncher.length > 0
                width: parent.width
                spacing: 10
                Text {
                    textFormat: Text.PlainText
                    width: Math.min(parent.width, 460)
                    wrapMode: Text.WordWrap
                    height: Math.max(38, implicitHeight)
                    verticalAlignment: Text.AlignVCenter
                    text: shell.appImageLauncher === "other" ? qsTr("This AppImage is in your app launcher (added by AppImageLauncher or a similar tool), so docks show its icon.")
                        : shell.appImageLauncher === "ours" ? qsTr("This AppImage is in your app launcher, so docks show its icon.")
                        : qsTr("This AppImage isn't in your app launcher, so docks and taskbars can't show its icon.")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                PillButton {
                    objectName: "addToLauncher"
                    visible: shell.appImageLauncher === "none"
                    text: qsTr("Add to app launcher")
                    onClicked: Nav.notify(shell.addToLauncher())
                }
                PillButton {
                    visible: shell.appImageLauncher === "ours"
                    text: qsTr("Remove from app launcher")
                    onClicked: shell.removeFromLauncher()
                }
            }
            PillButton { text: qsTr("Open mini player"); onClicked: shell.toggleMini() }

        }
        SettingsSection {
            id: sec_about
            objectName: "settings_about"
            title: qsTr("About")
            keywords: qsTr("version debug bug report update check logo")
            query: page.query
            Image {
                width: 260
                height: 210
                source: "../assets/logo.png"
                fillMode: Image.PreserveAspectFit
                sourceSize: Qt.size(600, 600)
                smooth: true
                Accessible.name: qsTr("Hallucinate logo")
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Hallucinate %1 — a modern music library and player").arg(shell.appVersion)
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Flow {
                width: parent.width
                spacing: 10
                PillButton {
                    objectName: "copyDebugInfo"
                    text: qsTr("Copy debug info")
                    onClicked: { shell.copyDebugInfo(); Nav.notify(qsTr("Debug info copied — paste it into your bug report")) }
                }
                PillButton {
                    text: qsTr("Report a bug")
                    onClicked: Qt.openUrlExternally("https://github.com/Phosphene-dev/Hallucinate/issues/new")
                }
            }
            Text {
                textFormat: Text.PlainText
                visible: !shell.updates.supported
                text: qsTr("Updates come through your software centre or package manager.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Flow {  // wraps in a narrow window instead of running off its edge
                visible: shell.updates.supported
                width: parent.width
                spacing: 12
                StyledCheck {
                    objectName: "updateChecks"
                    width: Math.min(implicitWidth, parent.width)
                    text: qsTr("Tell me when a new version is out (checks GitHub once a day)")
                    checked: shell.updates.enabled
                    onToggled: shell.updates.setEnabled(checked)
                }
                PillButton {
                    height: 32
                    text: shell.updates.busy ? qsTr("Checking…") : qsTr("Check now")
                    enabled: !shell.updates.busy && !shell.offlineMode
                    onClicked: shell.updates.checkNow()
                }
                PillButton {
                    objectName: "updateNow"
                    height: 32
                    primary: true
                    visible: shell.updates.canInstall && (shell.updates.available || shell.updates.installing)
                    text: shell.updates.installing ? qsTr("Cancel") : qsTr("Update now")
                    enabled: shell.updates.installing || !shell.offlineMode
                    onClicked: shell.updates.installing ? shell.updates.cancelInstall() : Nav.installUpdate()
                }
            }
            Text {
                textFormat: Text.PlainText
                visible: shell.updates.status.length > 0
                width: parent.width
                wrapMode: Text.WordWrap
                text: shell.updates.status
                color: shell.updates.available ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                MouseArea {
                    anchors.fill: parent
                    enabled: shell.updates.available
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Qt.openUrlExternally(shell.updates.releaseUrl)
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Debug info lists versions, your system, display and audio setup and the recent log. It leaves out file paths, your music and account names.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
    }
    }
}
