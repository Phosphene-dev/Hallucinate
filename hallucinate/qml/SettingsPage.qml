import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "."

Item {
    id: page
    objectName: "settings"
    property string query: ""
    readonly property var sectionIds: ["appearance", "features", "podcasts", "playback", "sound", "library", "servers", "remote", "sharing", "scrobbling", "desktop", "about"]
    readonly property var sectionTitles: ["Appearance", "Features", "Podcasts", "Playback", "Sound", "Library", "Music servers", "Remote & web", "Online & privacy", "Scrobbling & sharing", "Desktop", "About"]

    function sectionItem(i) { return [sec_appearance, sec_features, sec_podcasts, sec_playback, sec_sound, sec_library, sec_servers, sec_remote, sec_sharing, sec_scrobbling, sec_desktop, sec_about][i] }
    function jumpToSidebar() {
        jumpTo(1)
        sidebarGroup.open = true
        var y = sidebarOrderBox.mapToItem(flick.contentItem, 0, 0).y - 20
        flick.contentY = Math.max(0, Math.min(y, flick.contentHeight - flick.height))
    }
    // the section at the top of the view, lit in the jump list
    readonly property int currentSection: {
        var y = flick.contentY + 40, at = 0
        for (var i = 0; i < sectionIds.length; i++) {
            var s = sectionItem(i)
            if (s && s.visible && s.y <= y) at = i
        }
        return at
    }
    function jumpTo(i) {
        page.query = ""
        search.text = ""
        flick.contentY = Math.max(0, Math.min(sectionItem(i).y, flick.contentHeight - flick.height))
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
            Text { id: pageTitle; text: "Settings"; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale; font.weight: Font.Bold; textFormat: Text.PlainText }
            TextField {
                id: search
                objectName: "settingsSearch"
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(340, parent.width - pageTitle.width - 16)
                height: 36
                placeholderText: "Search settings"
                color: Theme.text
                placeholderTextColor: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(14)
                leftPadding: 14
                selectByMouse: true
                background: Rectangle { radius: Theme.round(height / 2); color: Theme.surface; border.color: search.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                onTextChanged: { page.query = text; flick.contentY = 0 }
                Keys.onEscapePressed: text = ""
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
                    visible: (modelData !== "Podcasts" || shell.features.podcasts !== false)
                             && (modelData !== "Music servers" || shell.features.servers === true)
                    text: modelData
                    selected: index === page.currentSection
                    onClicked: page.jumpTo(index)
                }
            }
        }
        Text {
            textFormat: Text.PlainText
            visible: page.query.length > 0
            text: noMatches ? "No settings match “" + page.query + "”" : "Showing settings that match “" + page.query + "”"
            // (a section hidden because its feature is off doesn't count, even if it matches)
            readonly property bool noMatches: !(sec_appearance.visible || sec_features.visible || sec_podcasts.visible || sec_playback.visible || sec_sound.visible || sec_library.visible || sec_servers.visible || sec_remote.visible || sec_sharing.visible || sec_scrobbling.visible || sec_desktop.visible || sec_about.visible)
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
            title: "Appearance"
            keywords: "theme colours colors font text size bigger smaller accent album art ambient motion drift paused power battery visualizer background unfocused reduce animation dark light system pride ribbon custom badges bitrate format scroll speed mouse wheel explicit hi-res hires bit depth 24-bit sample rate"
            query: page.query
            Row {
                spacing: 12
                visible: !themeManager.followSystem  // following the system, the Light and Dark choices below apply
                Text {
                    textFormat: Text.PlainText
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Theme"
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
                Text { textFormat: Text.PlainText; text: "Accent colour"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14) }
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
                                Accessible.name: modelData === "#f5be9d" ? "Accent Shrimp Boat"  // PPG's paint colour
                                                 : modelData.length ? "Accent " + modelData : "The theme's own accent"
                                Accessible.checked: chosen
                                Accessible.onPressAction: themeManager.setAccentOverride(modelData)
                            }
                        }
                    }
                    TextField {
                        id: accentHex
                        objectName: "accentHex"
                        width: 120; height: 30
                        placeholderText: "#hex"
                        text: themeManager.accentOverride
                        selectByMouse: true
                        Accessible.name: "Accent colour as a hex code"
                        // typing breaks the binding above: follow the accent again once it changes elsewhere
                        Connections { target: themeManager; function onThemeChanged() { if (!accentHex.activeFocus) accentHex.text = themeManager.accentOverride } }
                        onAccepted: themeManager.setAccentOverride(text)
                    }
                }
                StyledCheck {
                    objectName: "albumArtAccent"
                    text: "Tint the accent with each album's cover"
                    checked: themeManager.albumArtAccent
                    onToggled: themeManager.setAlbumArtAccent(checked)
                }
                StyledCheck {
                    objectName: "followSystemTheme"
                    text: "Follow the system's light or dark mode"
                    checked: themeManager.followSystem
                    onToggled: themeManager.setFollowSystem(checked)
                }
                Flow {
                    visible: themeManager.followSystem
                    width: parent.width
                    spacing: 10
                    Text { textFormat: Text.PlainText; text: "Light"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        width: 200
                        model: themeManager.availableThemes
                        selection: themeManager.availableThemes.indexOf(themeManager.lightTheme)
                        onActivated: themeManager.setSystemThemes(currentText, themeManager.darkTheme)
                        Accessible.name: "Theme in light mode"
                    }
                    Text { textFormat: Text.PlainText; text: "Dark"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        width: 200
                        model: themeManager.availableThemes
                        selection: themeManager.availableThemes.indexOf(themeManager.darkTheme)
                        onActivated: themeManager.setSystemThemes(themeManager.lightTheme, currentText)
                        Accessible.name: "Theme in dark mode"
                    }
                }
                PillButton { objectName: "makeTheme"; text: "Make my own theme…"; onClicked: themeEditor.open() }
            }
            ThemeEditor { id: themeEditor }
            StyledCheck {
                objectName: "ambientMotion"
                text: "Animated background (slowly drifting colours from the current cover)"
                checked: shell.ambientMotion
                onToggled: shell.setAmbientMotion(checked)
            }
            StyledCheck {
                objectName: "ambientOnlyPlaying"
                visible: shell.ambientMotion
                leftPadding: 28
                text: "Only while music plays (it rests while paused, using no power)"
                checked: shell.ambientOnlyPlaying
                onToggled: shell.setAmbientOnlyPlaying(checked)
            }
            Flow {
                visible: shell.features.visualizer !== false
                width: parent.width
                spacing: 10
                Text { textFormat: Text.PlainText; text: "Visualizer while the window is in the background"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "visualizerBackground"
                    readonly property var modes: ["full", "slower", "paused"]
                    width: 220
                    model: ["Full speed", "Slower (saves power)", "Paused"]
                    selection: Math.max(0, modes.indexOf(shell.visualizerBackground))
                    onActivated: shell.setVisualizerBackground(modes[currentIndex])
                    Accessible.name: "Visualizer while the window is in the background"
                }
            }
            StyledCheck {
                objectName: "reduceMotion"
                text: "Reduce motion (no page transitions, zooms, spinning record or growing buttons)"
                checked: shell.reduceMotion
                onToggled: shell.setReduceMotion(checked)
            }
            SettingsGroup {
                key: "appearanceMore"
                title: "More appearance options"
                summary: "Text size, track badges, theme files"
                query: page.query
                Flow {
                    width: parent.width
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: "Text size"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "textSize"
                        width: 200
                        readonly property var sizes: [0.9, 1.0, 1.1, 1.25, 1.4]
                        model: ["Smaller", "As the theme has it", "Larger", "Larger still", "Largest"]
                        selection: sizes.indexOf(themeManager.textScale)
                        onActivated: function (i) { themeManager.setTextScale(sizes[i]) }
                        Accessible.name: "Text size"
                    }
                }
                Row {
                    spacing: 12
                    Text { textFormat: Text.PlainText; text: "Scroll speed"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); height: 38; verticalAlignment: Text.AlignVCenter }
                    StyledCombo {
                        objectName: "scrollSpeed"
                        width: 200
                        readonly property var speeds: [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
                        model: ["Slowest", "Slow", "Normal", "Fast", "Faster", "Fastest"]
                        selection: speeds.indexOf(shell.scrollSpeed) >= 0 ? speeds.indexOf(shell.scrollSpeed) : 2
                        onActivated: function (i) { shell.setScrollSpeed(speeds[i]) }
                        Accessible.name: "Scroll speed (mouse wheel)"
                    }
                }
                StyledCheck {
                    text: "Show audio format and average bitrate on tracks"
                    checked: player.showTrackInfo
                    onToggled: player.setShowTrackInfo(checked)
                    Accessible.name: "Show track audio format and average bitrate"
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    text: "Shows compact format and approximate average bitrate badges in song rows and the now-playing bar."
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                    wrapMode: Text.WordWrap
                }
                StyledCheck {
                    objectName: "explicitBadges"
                    text: "Mark explicit songs with an E"
                    checked: Rows.explicitBadges
                    onToggled: shell.setSongBadge("explicitBadges", checked)
                }
                StyledCheck {
                    objectName: "cleanBadges"
                    text: "Mark clean (edited) versions with a C"
                    checked: Rows.cleanBadges
                    onToggled: shell.setSongBadge("cleanBadges", checked)
                }
                StyledCheck {
                    objectName: "hiResBadges"
                    text: "Show a Hi-Res badge on 24-bit and higher songs"
                    checked: Rows.hiResBadges
                    onToggled: shell.setSongBadge("hiResBadges", checked)
                }
                Row {
                    visible: Rows.hiResBadges
                    leftPadding: 28
                    spacing: 12
                    Text { anchors.verticalCenter: parent.verticalCenter; text: "Hi-Res badge"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                    StyledCombo {
                        objectName: "hiResBadgeStyle"
                        width: 230
                        model: ["\"Hi-Res\"", "A gold M (Master)"]
                        selection: Rows.masterBadge ? 1 : 0
                        onActivated: function (i) { shell.setSongBadge("masterBadge", i === 1) }
                        Accessible.name: "Hi-Res badge style"
                    }
                }
                StyledCheck {
                    objectName: "bitDepthBadges"
                    text: "Show every song's bit depth and sample rate"
                    checked: Rows.bitDepth
                    onToggled: shell.setSongBadge("bitDepth", checked)
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    text: "Explicit comes from the files' tags (iTunes advisory or an EXPLICIT tag); bit depth from lossless files (FLAC, ALAC, WAV, AIFF, WavPack, APE, DSD). Songs added before this version get both at the next scan."
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                    wrapMode: Text.WordWrap
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                    text: "Custom themes: " + themeManager.userThemeDirectory + "/*.json"
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(12)
                }
                PillButton {
                    text: "Reload themes"
                    onClicked: themeManager.reloadThemes()
                }
            }

        }
        SettingsSection {
            id: sec_features
            objectName: "settings_features"
            title: "Features"
            keywords: "hide show turn off sidebar pages order rearrange move arrange home cards internet radio stations podcasts lyrics stats recap history visualizer health folders liked"
            query: page.query
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: "Turn off what you don't use. It disappears everywhere (the sidebar, Ctrl+K, menus and shortcuts) and nothing is lost: switch it back on and it's all still there."
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
                heading: "Listening"
                items: [["stations", "Internet radio"], ["podcasts", "Podcasts"], ["servers", "Music servers"],
                        ["lyrics", "Lyrics"], ["visualizer", "Visualizer"]]
            }
            FeatureGroup {
                heading: "Pages"
                items: [["liked", "Liked Songs"], ["folders", "Folders"], ["stats", "Stats"], ["history", "History"],
                        ["recap", "Recap"], ["health", "Library health"]]
            }
            FeatureGroup {
                heading: "Home"
                items: [["homeRandom", "Random album"], ["homeListening", "Listening card"],
                        ["homeFacts", "Library facts"], ["homeShelves", "Album shelves"]]
            }
            SettingsGroup {
                id: sidebarGroup
                key: "sidebarOrder"
                title: "Sidebar order"
                summary: "Move pages up or down"
                query: page.query
                Column {
                    id: sidebarOrderBox
                    objectName: "sidebarOrder"
                    width: parent.width
                    spacing: 6
                    readonly property var names: ({ home: "Home", albums: "Albums", artists: "Artists", songs: "Songs",
                        folders: "Folders", liked: "Liked Songs", stats: "Stats", history: "History", recap: "Recap",
                        visualizer: "Visualizer", stations: "Internet radio", podcasts: "Podcasts" })
                    readonly property var shown: shell.sidebarOrder.filter(function (p) { return shell.features[p] !== false })
                    Row {
                        width: parent.width
                        spacing: 12
                        Text {
                            textFormat: Text.PlainText
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Sidebar order"
                            color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
                        }
                        PillButton { objectName: "resetSidebarOrder"; height: 30; text: "Reset"; onClicked: shell.resetSidebarOrder() }
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "Move pages up or down here, drag them in the sidebar, or right-click one there. With a page focused, Alt+Up and Alt+Down move it too."
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
                                    tip: "Move " + sidebarOrderBox.names[modelData] + " up"
                                    onClicked: shell.moveSidebarPage(modelData, -1)
                                }
                                IconButton {
                                    icon: "down"; size: 16
                                    enabled: index < sidebarOrderBox.shown.length - 1
                                    opacity: enabled ? 1 : 0.35
                                    tip: "Move " + sidebarOrderBox.names[modelData] + " down"
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
            title: "Podcasts"
            keywords: "podcast episodes skip back forward seconds feeds check refresh download keep remove storage played speed next"
            query: page.query
            visible: matches && shell.features.podcasts !== false
            readonly property var o: podcasts.options
            function secs(list) { return list.map(function (n) { return n + " seconds" }) }
            OptionCombo {
                label: "Skip back"
                values: [5, 10, 15, 30, 45, 60]; labels: sec_podcasts.secs(values)
                current: sec_podcasts.o.skipBack
                onPicked: function (v) { podcasts.setOption("skipBack", v) }
            }
            OptionCombo {
                label: "Skip forward"
                values: [10, 15, 30, 45, 60, 90]; labels: sec_podcasts.secs(values)
                current: sec_podcasts.o.skipForward
                onPicked: function (v) { podcasts.setOption("skipForward", v) }
            }
            OptionCombo {
                label: "After an episode"
                values: ["next", "stop"]
                labels: ["Play the show's next one", "Stop"]
                current: sec_podcasts.o.afterEpisode
                onPicked: function (v) { podcasts.setOption("afterEpisode", v) }
            }
            StyledCheck {
                objectName: "notifyNewEpisodes"
                text: "Tell me when a show I follow has a new episode (a desktop notification)"
                checked: sec_podcasts.o.notifyNew === 1
                onToggled: podcasts.setOption("notifyNew", checked ? 1 : 0)
            }
            SettingsGroup {
                key: "podcastsMore"
                title: "When to check, and when an episode counts as played"
                query: page.query
                OptionCombo {
                    label: "Check for new episodes"
                    values: [1, 2, 4, 8, 12, 24, 0]
                    labels: ["Every hour", "Every 2 hours", "Every 4 hours", "Every 8 hours", "Twice a day", "Once a day", "Only when I ask"]
                    current: sec_podcasts.o.refreshHours
                    onPicked: function (v) { podcasts.setOption("refreshHours", v) }
                }
                OptionCombo {
                    label: "Played when this close to the end"
                    values: [10, 30, 45, 60, 120, 300]
                    labels: ["10 seconds", "30 seconds", "45 seconds", "1 minute", "2 minutes", "5 minutes"]
                    current: sec_podcasts.o.playedWindow
                    onPicked: function (v) { podcasts.setOption("playedWindow", v) }
                }
            }
            Text { textFormat: Text.PlainText; text: "Downloads"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
            OptionCombo {
                label: "A show you follow downloads"
                values: [0, 1, 2, 3, 5]
                labels: ["Nothing by itself", "Its newest episode", "Its newest 2", "Its newest 3", "Its newest 5"]
                current: sec_podcasts.o.newShowDownloads
                onPicked: function (v) { podcasts.setOption("newShowDownloads", v) }
            }
            OptionCombo {
                label: "Keep downloads"
                values: ["played", "latest", "forever"]
                labels: ["Until they're played", "Only the newest of each show", "Until I remove them"]
                current: sec_podcasts.o.keep
                onPicked: function (v) { podcasts.setOption("keep", v) }
            }
            OptionCombo {
                visible: sec_podcasts.o.keep === "latest"
                label: "Newest to keep per show"
                values: [1, 2, 3, 5, 10]; labels: ["1", "2", "3", "5", "10"]
                current: sec_podcasts.o.keepCount
                onPicked: function (v) { podcasts.setOption("keepCount", v) }
            }
            Row {
                spacing: 12
                Text {
                    textFormat: Text.PlainText
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Downloads take " + Theme.fmtBytes(podcasts.downloadsSize)
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                }
                PillButton { text: "Remove all downloads"; enabled: podcasts.downloadsSize > 0; onClicked: removeDownloadsDlg.open() }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Each show can have its own speed, skip its intro or outro, list oldest first and download its newest episodes: open the show and choose Show settings. Episodes in a folder you added are your own files and are never removed."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            ConfirmDialog {
                id: removeDownloadsDlg
                title: "Remove every downloaded episode?"
                body: "The files go; the episodes stay, and play from the web until downloaded again."
                confirmText: "Remove downloads"
                destructive: true
                onAccepted: podcasts.removeAllDownloads()
            }
        }

        SettingsSection {
            id: sec_playback
            objectName: "settings_playback"
            title: "Playback"
            keywords: "output device audio replaygain loudness preamp measure crossfade gapless album fade pause resume start startup open volume step wheel maximum limit loud speed sleep timer"
            query: page.query
            Flow {  // wraps in a narrow window
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: "Output device"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
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
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: "ReplayGain"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "rgMode"
                    model: ["Off", "Track", "Album"]
                    selection: ["off", "track", "album"].indexOf(player.replayGainMode)
                    onActivated: player.setReplayGainMode(["off", "track", "album"][currentIndex])
                }
            }
            SettingsGroup {
                key: "replayGain"
                title: "ReplayGain details"
                summary: "Preamp, measuring songs without tags"
                query: page.query
                Flow {
                    width: parent.width
                    spacing: 12
                    Text { height: 38; verticalAlignment: Text.AlignVCenter; text: "Preamp " + player.replayGainPreamp.toFixed(1) + " dB"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                    StyledSlider {
                        width: 140
                        from: -15; to: 15; stepSize: 0.5
                        value: player.replayGainPreamp
                        onMoved: player.setReplayGainPreamp(value)
                    }
                }
                StyledCheck {
                    objectName: "autoReplayGain"
                    text: "Measure new music by itself after each scan"
                    checked: replayGain.auto
                    onToggled: replayGain.setAuto(checked)
                }
                Flow {  // wraps in a narrow window
                    width: parent.width
                    spacing: 12
                    PillButton {
                        objectName: "analyseReplayGain"
                        text: replayGain.busy ? "Stop measuring" : "Measure songs without ReplayGain"
                        onClicked: replayGain.busy ? replayGain.cancel() : replayGain.analyseMissing()
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: Math.min(implicitWidth, parent.width)
                        wrapMode: Text.WordWrap
                        text: replayGain.busy ? "Measured " + replayGain.done + " of " + replayGain.total + " songs…"
                            : "Measures loudness (EBU R128) for songs whose files have no ReplayGain tags. Files aren't changed."
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(12)
                    }
                }
            }
            Flow {
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: "Crossfade " + (player.crossfade > 0 ? player.crossfade + " s" : "off"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
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
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: "Volume step"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "volumeStep"
                    readonly property var steps: [0.01, 0.02, 0.05, 0.1]
                    width: 120
                    model: ["1%", "2%", "5%", "10%"]
                    selection: Math.max(0, steps.findIndex(s => Math.abs(s - player.volumeStep) < 0.001))
                    onActivated: player.setVolumeStep(steps[currentIndex])
                    Accessible.name: "Volume step for the mouse wheel and arrow keys"
                }
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: "Maximum volume " + Math.round(player.maxVolume * 100) + "%"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledSlider {
                    objectName: "maxVolume"
                    width: 160
                    from: 0.1; to: 1; stepSize: 0.05
                    value: player.maxVolume
                    onMoved: player.setMaxVolume(value)
                    Accessible.name: "Maximum volume"
                }
            }
            StyledCheck {
                objectName: "resumeOnStart"
                text: "Start playing when Hallucinate opens (carry on where it was)"
                checked: player.resumeOnStart
                onToggled: player.setResumeOnStart(checked)
            }
            StyledCheck {
                objectName: "crossfadeAlbums"
                visible: player.crossfade > 0
                text: "Crossfade between songs of the same album too (off: an album plays gaplessly, as it runs)"
                checked: player.crossfadeAlbums
                onToggled: player.setCrossfadeAlbums(checked)
            }
            Flow {
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: "Fade on pause and play"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "pauseFade"
                    readonly property var lengths: [0, 150, 400, 1000]
                    width: 200
                    model: ["Off", "Quick", "Gentle", "Slow"]
                    selection: Math.max(0, lengths.indexOf(player.pauseFade))
                    onActivated: player.setPauseFade(lengths[currentIndex])
                    Accessible.name: "Fade on pause and play"
                }
            }
            Text { width: parent.width; wrapMode: Text.WordWrap; text: "Gapless playback is always on; with crossfade off, consecutive tracks play back to back. Playback speed and the sleep timer are in the ⋯ menu of the player bar."; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); textFormat: Text.PlainText }
        }
        SettingsSection {
            id: sec_sound
            objectName: "settings_sound"
            title: "Sound"
            keywords: "equalizer eq bass treble headphones autoeq crossfeed"
            query: page.query
            EqualizerPanel { width: parent.width }
            Flow {
                width: parent.width
                spacing: 12
                Text { height: 38; verticalAlignment: Text.AlignVCenter; text: "Headphone crossfeed"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "crossfeed"
                    enabled: player.eqAvailable
                    model: ["Off", "Light", "Medium", "Strong"]
                    selection: player.crossfeedPresets.indexOf(player.crossfeed)
                    onActivated: player.setCrossfeed(player.crossfeedPresets[currentIndex])
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Lets each ear hear a little of the other channel, as from speakers. Old stereo recordings with "
                    + "instruments hard left or right get much easier on the ears over headphones."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }

        }
        SettingsSection {
            id: sec_library
            objectName: "settings_library"
            title: "Library"
            keywords: "genres genre music folders scan rescan start startup watch watching health tags files ratings stars cover art cover.jpg embed import strawberry clementine rhythmbox musicbee itunes foobar playlists hidden removed restore albums backup export your data move computer"
            query: page.query
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Folders are scanned in the background" + (library.scanAtStart ? " at every start" : "")
                      + (library.watching ? " and watched for changes." : ". Rescan picks up what's new.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            StyledCheck {
                objectName: "scanAtStart"
                text: "Look for new and changed files when Hallucinate starts"
                checked: library.scanAtStart
                onToggled: library.setScanAtStart(checked)
            }
            StyledCheck {
                objectName: "watchFolders"
                text: "Watch the folders and pick up changes as they happen"
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
                        tip: "Remove this folder from the library"
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
                    text: "Add folder"
                    onClicked: { library.addFolder(pathField.text); pathField.text = "" }
                }
                PillButton { text: "Choose folder…"; onClicked: picker.open() }
                PillButton { text: "Rescan now"; onClicked: library.rescan() }
                PillButton { objectName: "openHealth"; visible: shell.features.health !== false; text: "Library health"; onClicked: Nav.openHealth() }
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
                text: "Folder not found or unreadable: " + library.missingFolders.join(", ")
                color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Text {
                textFormat: Text.PlainText
                visible: library.unreadableFiles > 0 && !library.scanning
                text: library.unreadableFiles + " files could not be read and were skipped."
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
                    text: library.hiddenCount + (library.hiddenCount === 1 ? " file" : " files")
                          + " removed from the library (still on disk)"
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                PillButton {
                    objectName: "restoreHidden"
                    height: 32
                    text: "Bring them back"
                    onClicked: { library.restoreHidden(); Nav.notify("Rescanning to bring them back…") }
                }
            }
            SettingsGroup {
                key: "libraryFiles"
                title: "Files and tags"
                summary: "Ratings and covers in files, how many genres show"
                query: page.query
                StyledCheck {
                    objectName: "ratingsInFiles"
                    text: "Save star ratings in the songs' own tags too, so other players see them"
                    checked: userLib.ratingsInFiles
                    onToggled: userLib.setRatingsInFiles(checked)
                }
                StyledCheck {
                    objectName: "coversToFolder"
                    text: "Save covers you add as cover.jpg in the album's folder"
                    checked: metaEditor.coversToFolder
                    onToggled: metaEditor.setCoversToFolder(checked)
                }
                StyledCheck {
                    objectName: "embedCovers"
                    text: "Also embed covers you add in the songs themselves"
                    checked: metaEditor.embedCovers
                    onToggled: metaEditor.setEmbedCovers(checked)
                }
                StyledCheck {
                    objectName: "allGenresAlbums"
                    text: "Show every genre on album and artist pages (not just the main one)"
                    checked: shell.allGenresAlbums
                    onToggled: shell.setAllGenresAlbums(checked)
                }
                StyledCheck {
                    objectName: "allGenresSongs"
                    text: "Show every genre of the playing song (not just the main one)"
                    checked: shell.allGenresSongs
                    onToggled: shell.setAllGenresSongs(checked)
                }
            }
            SettingsGroup {
                key: "otherPlayer"
                title: "From another player"
                summary: "Strawberry, Clementine, Rhythmbox, MusicBee, iTunes, foobar2000"
                query: page.query
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "Bring over play counts, skips, ratings and playlists from Strawberry, Clementine, Rhythmbox, MusicBee "
                        + "or iTunes. Songs are matched to your library; importing again never counts anything twice, and "
                        + "ratings you set here are kept."
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
                            text: "Import from " + modelData.name
                            enabled: !userLib.playerImportBusy
                            onClicked: userLib.importFromPlayer(modelData.path)
                        }
                    }
                    PillButton {
                        objectName: "importPlayerFile"
                        text: foundPlayers.count ? "Choose another library file…" : "Choose a library file…"
                        enabled: !userLib.playerImportBusy
                        onClicked: playerFile.open()
                    }
                    PillButton {
                        text: userLib.playerImportBusy ? "Importing…" : "foobar2000: play counts from tags"
                        enabled: !userLib.playerImportBusy
                        onClicked: userLib.importTagStatistics()
                    }
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "MusicBee: turn on Preferences → Library → “make library and playlists accessible to other "
                        + "applications”, then choose its iTunes Music Library.xml. foobar2000 keeps its statistics to "
                        + "itself, so write them to the files with foo_playcount first; its playlists come over as M3U files."
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
                FileDialog {
                    id: playerFile
                    title: "Choose another player's library"
                    nameFilters: ["Player libraries (*.db *.xml)", "All files (*)"]
                    onAccepted: userLib.importFromPlayer(selectedFile.toString())
                }
            }
            Flow {  // wraps in a narrow window
                width: parent.width
                objectName: "backupRow"
                spacing: 10
                Text {
                    textFormat: Text.PlainText
                    text: "Your likes, ratings, playlists, history, stations and shows"
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                PillButton { objectName: "exportBackup"; height: 32; text: "Back up…"; onClicked: backupSaveDlg.open() }
                PillButton { objectName: "importBackup"; height: 32; text: "Restore…"; onClicked: backupOpenDlg.open() }
            }
            FileDialog {
                id: backupSaveDlg
                title: "Back up your data"
                fileMode: FileDialog.SaveFile
                defaultSuffix: "hallucinate-backup"
                nameFilters: ["Hallucinate backup (*.hallucinate-backup)"]
                onAccepted: Nav.notify(shell.exportBackup(selectedFile.toString()))
            }
            FileDialog {
                id: backupOpenDlg
                title: "Restore from a backup"
                nameFilters: ["Hallucinate backup (*.hallucinate-backup)", "All files (*)"]
                onAccepted: Nav.notify(shell.importBackup(selectedFile.toString()))
            }
        }
        SettingsSection {
            id: sec_servers
            objectName: "settings_servers"
            title: "Music servers"
            keywords: "server servers subsonic navidrome gonic airsonic ampache jellyfin emby stream remote network nas sync offline copy copies download keep"
            query: page.query
            visible: matches && shell.features.servers === true
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Songs on your Jellyfin server, or your Navidrome, Gonic, Airsonic or other Subsonic server, join your library and play like your own files. The sign-in stays in your system keyring (for Jellyfin, only the access token it gives). Songs from a server that can't be reached are skipped."
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
                            text: (m.status === "syncing" ? "Reading its songs…"
                                   : m.status === "checking" ? "Checking…"
                                   : m.status === "down" ? "Can't be reached" + (m.error ? ": " + m.error : "") + " (tried again every few minutes)"
                                   : m.status === "error" ? m.error
                                   : m.songs.toLocaleString(Qt.locale(), "f", 0) + (m.songs === 1 ? " song" : " songs")
                                     + (m.error ? "  ·  " + m.error : ""))
                                  + (m.secure ? "" : "  ·  not a secure link")
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
                        text: "Sign in again…"
                        onClicked: { signInDlg.serverId = serverRow.modelData.id; signInDlg.what = serverRow.modelData.name; signInDlg.open() }
                    }
                    PillButton {
                        id: syncButton
                        anchors.verticalCenter: parent.verticalCenter
                        height: 32
                        text: "Sync now"
                        enabled: !serverRow.modelData.busy
                        onClicked: servers.sync(serverRow.modelData.id)
                    }
                    PillButton {
                        id: removeButton
                        anchors.verticalCenter: parent.verticalCenter
                        height: 32
                        text: "Remove"
                        onClicked: { removeServerDlg.serverId = serverRow.modelData.id; removeServerDlg.what = serverRow.modelData.name; removeServerDlg.open() }
                    }
                }
            }
            PillButton {
                objectName: "addServer"
                primary: true
                text: "Add a server…"
                onClicked: addServerDlg.open()
            }
            // Songs kept on this computer, to play without the server (right-click an album, playlist or song)
            Text {
                textFormat: Text.PlainText
                objectName: "serverCopies"
                width: parent.width
                wrapMode: Text.WordWrap
                text: (serverCopies.count > 0
                       ? serverCopies.count.toLocaleString(Qt.locale(), "f", 0) + (serverCopies.count === 1 ? " song" : " songs")
                         + " kept on this computer (" + Theme.fmtBytes(serverCopies.bytes) + "): they play without the server, in offline mode too."
                       : "To play a server's songs without it (on a train, say), right-click an album, playlist or song and choose Keep on this computer.")
                      + (serverCopies.waiting > 0 ? "  Downloading " + serverCopies.waiting + " more"
                         + (serverCopies.busy ? " (" + Math.round(serverCopies.progress * 100) + "% of the current one)" : shell.offlineMode ? ", once offline mode is off" : "") + "." : "")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            PillButton {
                objectName: "removeServerCopies"
                visible: serverCopies.count > 0 || serverCopies.waiting > 0
                text: "Remove all copies…"
                onClicked: removeCopiesDlg.open()
            }
            ConfirmDialog {
                id: removeCopiesDlg
                title: "Remove the copies on this computer?"
                confirmText: "Remove copies"
                destructive: true
                body: "The songs stay in your library and on the server; they stream again instead of playing from this computer."
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
                title: "Sign in to " + what + " again"
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
                        text: "The server turned down the saved sign-in. Enter the password again: your playlists, plays and ratings for its songs stay as they are."
                        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                    }
                    TextField {
                        id: newPassword
                        width: parent.width
                        echoMode: TextInput.Password
                        placeholderText: "Password"
                        placeholderTextColor: Theme.textDim
                        color: Theme.text
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                        background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: newPassword.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                        onAccepted: signInDlg.accept()
                        Accessible.name: "Password"
                    }
                }
            }
            ConfirmDialog {
                id: removeServerDlg
                property string serverId: ""
                property string what: ""
                title: "Remove this server?"
                confirmText: "Remove server"
                destructive: true
                body: "Its songs leave your library and its password leaves the keyring. Nothing on the server changes."
                onAccepted: servers.removeServer(serverId)
            }
            Dialog {
                id: addServerDlg
                objectName: "addServerDialog"
                parent: Overlay.overlay
                anchors.centerIn: parent
                width: Math.min(460, (parent ? parent.width : 460) - 40)
                modal: true
                title: "Add a music server"
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
                            text: "Subsonic (Navidrome, Gonic…)"
                            selected: addServerDlg.kind === "subsonic"
                            onClicked: addServerDlg.kind = "subsonic"
                        }
                        Chip {
                            objectName: "serverKindJellyfin"
                            text: "Jellyfin"
                            selected: addServerDlg.kind === "jellyfin"
                            onClicked: addServerDlg.kind = "jellyfin"
                        }
                    }
                    TextField {
                        id: serverLink; objectName: "serverLink"; width: parent.width; selectByMouse: true
                        placeholderText: "Server link (https://music.example.com)"; Accessible.name: "Server link"
                        onAccepted: if (addServerDlg.ready) addServerDlg.accept()
                    }
                    Text {
                        visible: serverLink.text.trim().length > 0 && !servers.linkIsSecure(serverLink.text)
                        textFormat: Text.PlainText
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "This isn't a secure (https) link and isn't on your home network: anyone on the networks in between could see what you play and reuse your sign-in."
                        color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                    }
                    TextField {
                        id: serverUser; objectName: "serverUser"; width: parent.width; selectByMouse: true
                        placeholderText: "User name"; Accessible.name: "User name"
                        onAccepted: if (addServerDlg.ready) addServerDlg.accept()
                    }
                    TextField {
                        id: serverPassword; objectName: "serverPassword"; width: parent.width
                        echoMode: TextInput.Password; placeholderText: "Password"; Accessible.name: "Password"
                        onAccepted: if (addServerDlg.ready) addServerDlg.accept()
                    }
                    TextField {
                        id: serverName; width: parent.width; selectByMouse: true
                        placeholderText: "Name (optional)"; Accessible.name: "Server name"
                        onAccepted: if (addServerDlg.ready) addServerDlg.accept()
                    }
                }
            }
        }
        SettingsSection {
            id: sec_remote
            objectName: "settings_remote"
            title: "Remote & web"
            keywords: "remote phone web browser interface control pair pairing device devices network lan wifi headless tablet"
            query: page.query
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Control Hallucinate from your phone, a tablet or a browser: play, pause and skip, the queue, search and your library. Each device pairs once with a code from here, and can be removed any time. A remote can't change your files or settings."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            StyledCheck {
                objectName: "remoteOn"
                text: "Turn on the web interface and remote"
                checked: webRemote.on
                onToggled: webRemote.setOn(checked)
            }
            StyledCheck {
                objectName: "remoteNetwork"
                enabled: webRemote.on
                text: "Let other devices on your network connect (your phone on the same Wi-Fi). Only on networks you trust, like your home's"
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
                    text: webRemote.network ? "Open one of these on your phone or another computer:" : "Open this in a browser on this computer:"
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
                        text: webRemote.code.length ? "New code" : "Pair a device…"
                        onClicked: webRemote.pairDevice()
                    }
                    PillButton {
                        text: "Open in browser"
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
                            text: "Enter this code on the device"
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
                            text: "Works once, for " + Math.max(0, Math.ceil(webRemote.codeSeconds / 60)) + " more minute" + (webRemote.codeSeconds > 60 ? "s" : "")
                            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                        }
                        PillButton { height: 30; text: "Cancel"; onClicked: webRemote.cancelCode() }
                    }
                }
            }
            SettingsGroup {
                key: "remoteDevices"
                title: "Paired devices"
                summary: webRemote.pairedDevices.length ? webRemote.pairedDevices.length + (webRemote.pairedDevices.length === 1 ? " device" : " devices") : "None yet"
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
                            Text { textFormat: Text.PlainText; text: modelData.name; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold }
                            Text {
                                textFormat: Text.PlainText
                                text: "Paired " + new Date(modelData.paired * 1000).toLocaleDateString() + "  ·  last used " + new Date(modelData.seen * 1000).toLocaleString()
                                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                            }
                        }
                        PillButton { id: forgetButton; height: 30; text: "Remove"; anchors.verticalCenter: parent.verticalCenter; onClicked: webRemote.forgetDevice(modelData.id) }
                    }
                }
                PillButton {
                    visible: webRemote.pairedDevices.length > 1
                    text: "Remove all devices"
                    onClicked: webRemote.forgetAllDevices()
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "Lost a phone, or not sure who has access? Remove the device here: it can't connect again without a new code. Port: " + webRemote.portNumber + "."
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
            }
        }
        SettingsSection {
            id: sec_sharing
            objectName: "settings_sharing"
            title: "Online & privacy"
            keywords: "offline mode internet network privacy connection lyrics lrclib genres bios biography wikipedia discogs token musicbrainz last.fm tags similar artists discover"
            query: page.query
            StyledCheck {
                objectName: "offlineMode"
                text: "Offline mode"
                checked: shell.offlineMode
                onToggled: shell.setOfflineMode(checked)
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "With offline mode on, Hallucinate makes no internet connections at all: no lyrics, cover, genre or bio lookups, internet radio, podcast updates, scrobbling, headphone EQ downloads or update checks. Scrobbles wait and are sent when you turn it off. Discord status talks only to the Discord app on this computer, so it has its own switch under Scrobbling & sharing (it shows no cover art while offline)."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            StyledCheck {
                objectName: "lyricsOnline"
                visible: shell.features.lyrics !== false
                text: "Find lyrics online for songs that have none (asks LRCLIB with the artist, title and album)"
                checked: lyricsCtl.onlineLookup
                onToggled: lyricsCtl.setOnlineLookup(checked)
            }
            StyledCheck {
                objectName: "fetchBios"
                text: "Look up an artist's bio when their page opens (sends the artist and one of their albums)"
                checked: sources.fetchBios
                onToggled: sources.setFetchBios(checked)
            }
            Flow {
                width: parent.width
                spacing: 12
                Text { textFormat: Text.PlainText; text: "Bios come from"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "bioSource"
                    width: 220
                    readonly property var names: ["", "Wikipedia", "Last.fm", "Discogs"]
                    model: ["Wikipedia, then Last.fm, then Discogs", "Wikipedia only", "Last.fm only" + (sources.lastfmAvailable ? "" : " (not set up)"),
                            "Discogs only" + (sources.discogsConnected ? "" : " (not set up)")]
                    selection: names.indexOf(sources.bioSource)
                    onActivated: function (i) { sources.setBioSource(names[i]) }
                    Accessible.name: "Where artist bios come from"
                }
            }
            StyledCheck {
                objectName: "fetchSimilar"
                text: "Show similar artists from Last.fm on an artist's page (sends the artist's name)"
                      + (sources.lastfmAvailable ? "" : ". Needs the Last.fm API key, under Scrobbling & sharing")
                enabled: sources.lastfmAvailable || checked
                checked: sources.fetchSimilar
                onToggled: sources.setFetchSimilar(checked)
            }
            SettingsGroup {
                key: "genreSources"
                title: "Genre and bio sources"
                summary: "Discogs, Last.fm tags"
                query: page.query
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "Genres are looked up on MusicBrainz, and also on Discogs and Last.fm when they're set up. Only albums without a genre are looked up, and nothing is written until you've checked it. Bios come from Wikipedia (found through MusicBrainz), Last.fm or Discogs; one you write yourself on an artist's page is always shown instead."
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                StyledCheck {
                    objectName: "genresFromLastfm"
                    text: sources.lastfmAvailable ? "Also use Last.fm's tags for genres (only the tags that are real genres)"
                                                  : "Also use Last.fm's tags for genres (needs the Last.fm API key below)"
                    enabled: sources.lastfmAvailable
                    checked: sources.genresFromLastfm
                    onToggled: sources.setGenresFromLastfm(checked)
                }
                StyledCheck {
                    objectName: "genresFromDiscogs"
                    text: "Also use Discogs' genres and styles"
                    enabled: sources.discogsConnected
                    checked: sources.genresFromDiscogs
                    onToggled: sources.setGenresFromDiscogs(checked)
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: sources.discogsConnected
                          ? "Discogs: connected" + (sources.discogsUser ? " as " + sources.discogsUser : "") + ". The token is kept in the system keyring."
                          : "Discogs needs a personal access token: make one at discogs.com → Settings → Developers, then paste it here. It's kept in the system keyring."
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
                        placeholderText: "Discogs personal access token"
                        placeholderTextColor: Theme.textDim
                        color: Theme.text
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                        background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: discogsToken.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                        onAccepted: sources.connectDiscogs(text)
                        Accessible.name: "Discogs personal access token"
                    }
                    PillButton {
                        objectName: "connectDiscogs"
                        text: sources.discogsBusy ? "Checking…" : "Connect Discogs"
                        enabled: !sources.discogsBusy && discogsToken.text.trim().length > 0 && !shell.offlineMode
                        onClicked: { sources.connectDiscogs(discogsToken.text); discogsToken.text = "" }
                    }
                }
                PillButton {
                    objectName: "forgetDiscogs"
                    visible: sources.discogsConnected
                    text: "Disconnect Discogs"
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
            title: "Scrobbling & sharing"
            keywords: "last.fm lastfm listenbrainz scrobble scrobbling loves discord rich presence history import account radio stations podcasts episodes queued when half percent threshold point listen end"
            query: page.query
            Text { text: "Last.fm"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold; textFormat: Text.PlainText }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Sends now-playing updates, and scrobbles after half a song or four minutes, whichever comes first. Last.fm asks each person for an API key of their own; it and your sign-in stay in the system keyring."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            SettingsGroup {
                id: lastfmKeyGroup
                key: "lastfmKey"
                title: scrobbler.configured ? "Last.fm API key (saved)" : "Last.fm API key"
                summary: scrobbler.configured ? "Change it" : "Needed before connecting"
                query: page.query
                Component.onCompleted: if (!scrobbler.configured) open = true
                Flow {  // wraps in a narrow window
                    width: parent.width
                    spacing: 10
                    TextField {
                        id: apiKey
                        width: Math.min(250, parent.width); height: 38
                        placeholderText: scrobbler.configured ? "Saved (type a new one to replace it)" : "Last.fm API key"
                        color: Theme.text; placeholderTextColor: Theme.textDim
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                        background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: apiKey.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                    }
                    TextField {
                        id: apiSecret
                        width: Math.min(250, parent.width); height: 38
                        placeholderText: scrobbler.configured ? "Saved" : "Last.fm API secret"
                        echoMode: TextInput.Password
                        color: Theme.text; placeholderTextColor: Theme.textDim
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                        background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: apiSecret.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                    }
                    PillButton {
                        text: "Get API credentials"
                        onClicked: Qt.openUrlExternally("https://www.last.fm/api/account/create")
                    }
                    PillButton {
                        text: "Save API credentials"
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
                    text: scrobbler.busy ? "Connecting…" : "Connect Last.fm"
                    enabled: scrobbler.configured && !scrobbler.busy  // offline, it says why instead
                    onClicked: scrobbler.connectAccount()
                }
                PillButton {
                    visible: scrobbler.authorizationUrl.length > 0 && !scrobbler.connected
                    text: "Open authorization"
                    onClicked: scrobbler.openAuthorizationUrl()
                }
                PillButton {
                    visible: scrobbler.authorizationUrl.length > 0 && !scrobbler.connected
                    primary: true
                    text: "I've authorized"
                    enabled: !scrobbler.busy
                    onClicked: scrobbler.completeAuthorization()
                }
                PillButton {
                    visible: scrobbler.connected
                    text: "Disconnect Last.fm"
                    enabled: !scrobbler.busy
                    onClicked: scrobbler.disconnectAccount()
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: scrobbler.status + (scrobbler.pendingCount > 0 ? " · " + scrobbler.pendingCount + " waiting to be sent" : "")
                      + (scrobbler.rejectedCount > 0 ? " · " + scrobbler.rejectedCount + " turned down by Last.fm" : "")
                      + (scrobbler.lastError ? " · last try: " + scrobbler.lastError : "")
                color: scrobbler.connected ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
                wrapMode: Text.WordWrap
            }
            PillButton {
                objectName: "scrobblerRetryNow"
                visible: scrobbler.pendingCount > 0 && scrobbler.connected && !shell.offlineMode
                height: 32
                text: "Send now"
                onClicked: scrobbler.retryNow()
            }
            Flow {
                visible: scrobbler.connected
                width: parent.width
                spacing: 10
                Text { textFormat: Text.PlainText; text: "Scrobble a song after"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "scrobblePoint"
                    readonly property var points: ["rule", "25", "50", "75", "90", "end"]
                    width: 300
                    model: ["Half way, or 4 minutes (Last.fm's rule)", "A quarter of the way", "Half way, however long",
                            "Three quarters of the way", "90% of the way", "At the end"]
                    selection: Math.max(0, points.indexOf(scrobbler.listenPoint))
                    onActivated: scrobbler.setListenPoint(points[currentIndex])
                    Accessible.name: "Scrobble a song after"
                }
            }
            StyledCheck {
                objectName: "syncLoves"
                visible: scrobbler.connected && shell.features.liked !== false
                text: "Liking a song loves it on Last.fm (and unliking unloves it)"
                checked: scrobbler.syncLoves
                onToggled: scrobbler.setSyncLoves(checked)
            }
            PillButton {
                objectName: "importLoves"
                visible: scrobbler.connected && shell.features.liked !== false
                text: scrobbler.lovesBusy ? "Fetching your loves…" : "Like the songs I've loved on Last.fm"
                enabled: !scrobbler.lovesBusy
                onClicked: scrobbler.importLoves()
            }
            OfflineNote { visible: shell.offlineMode && (scrobbler.configured || scrobbler.connected); what: "Last.fm" }
            Text { text: "ListenBrainz"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold; textFormat: Text.PlainText }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Connect with your ListenBrainz user token to send now-playing updates and listens. The token stays in the system keyring; listens that can't be sent wait and are tried again."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Flow {  // wraps in a narrow window
                width: parent.width
                spacing: 10
                TextField {
                    id: lbToken
                    width: Math.min(320, parent.width); height: 38
                    visible: !listenbrainz.connected
                    placeholderText: "ListenBrainz user token"
                    echoMode: TextInput.Password
                    color: Theme.text; placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                    background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: lbToken.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                }
                PillButton {
                    visible: !listenbrainz.connected
                    primary: true
                    text: listenbrainz.busy ? "Validating…" : "Connect ListenBrainz"
                    enabled: lbToken.text.length > 0 && !listenbrainz.busy
                    onClicked: { listenbrainz.connectToken(lbToken.text, ""); lbToken.text = "" }
                }
                PillButton {
                    visible: !listenbrainz.connected
                    text: "Get a token"
                    onClicked: Qt.openUrlExternally("https://listenbrainz.org/settings/")
                }
                PillButton {
                    visible: listenbrainz.connected
                    text: "Disconnect ListenBrainz"
                    enabled: !listenbrainz.busy
                    onClicked: listenbrainz.disconnectAccount()
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: listenbrainz.status + (listenbrainz.pendingCount > 0 ? " · " + listenbrainz.pendingCount + " waiting to be sent" : "")
                      + (listenbrainz.rejectedCount > 0 ? " · " + listenbrainz.rejectedCount + " turned down by ListenBrainz" : "")
                      + (listenbrainz.lastError ? " · last try: " + listenbrainz.lastError : "")
                color: listenbrainz.connected ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); wrapMode: Text.WordWrap
            }
            OfflineNote { visible: shell.offlineMode; what: "ListenBrainz" }
            Flow {
                visible: listenbrainz.connected
                width: parent.width
                spacing: 10
                Text { textFormat: Text.PlainText; text: "Count a listen after"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "listenPoint"
                    readonly property var points: ["rule", "25", "50", "75", "90", "end"]
                    width: 300
                    model: ["Half way, or 4 minutes (Last.fm's rule)", "A quarter of the way", "Half way, however long",
                            "Three quarters of the way", "90% of the way", "At the end"]
                    selection: Math.max(0, points.indexOf(listenbrainz.listenPoint))
                    onActivated: listenbrainz.setListenPoint(points[currentIndex])
                    Accessible.name: "Count a listen after"
                }
            }
            PillButton {
                objectName: "listenbrainzRetryNow"
                visible: listenbrainz.pendingCount > 0 && listenbrainz.connected && !shell.offlineMode
                height: 32
                text: "Send now"
                onClicked: listenbrainz.retryNow()
            }
            StyledCheck {
                objectName: "scrobbleStations"
                visible: shell.features.stations !== false && (scrobbler.connected || listenbrainz.connected)
                text: "Count songs heard on internet radio on Last.fm and ListenBrainz"
                checked: stations.scrobble
                onToggled: stations.setScrobble(checked)
            }
            StyledCheck {
                objectName: "scrobblePodcasts"
                visible: shell.features.podcasts !== false && (scrobbler.connected || listenbrainz.connected)
                text: "Count podcast episodes on Last.fm and ListenBrainz (as the show and the episode's title)"
                checked: podcasts.scrobble
                onToggled: podcasts.setScrobble(checked)
            }
            SettingsGroup {
                key: "historyImport"
                title: "Import listening history"
                summary: "From ListenBrainz or Last.fm"
                query: page.query
                Flow {  // wraps in a narrow window
                    width: parent.width
                    spacing: 10
                    StyledCombo {
                        id: historySource
                        width: 150
                        model: ["ListenBrainz", "Last.fm"]
                    }
                    TextField {
                        id: historyUser
                        width: Math.min(260, parent.width); height: 38
                        placeholderText: historySource.currentIndex === 0 && listenbrainz.connected ? "Username (blank = connected account)" : "Username"
                        color: Theme.text; placeholderTextColor: Theme.textDim
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                        background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: historyUser.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                    }
                    PillButton {
                        primary: true
                        text: listenbrainz.importing ? "Importing…" : "Import history"
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
            Text { text: "Discord"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold; textFormat: Text.PlainText }
            StyledCheck { objectName: "discordEnabled"; text: "Show what I'm listening to on my Discord profile"; checked: discord.enabled; onToggled: discord.setEnabled(checked) }
            Column {
                visible: discord.enabled
                width: parent.width
                spacing: 12
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "Create an application at discord.com/developers, paste its Application ID below and upload your icon as an art asset named “hallucinate”. Status: " + discord.status
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
                TextField {
                    id: discordAppId
                    width: Math.min(320, parent.width)
                    placeholderText: "Discord application ID"
                    selectByMouse: true
                    color: Theme.text
                    placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                    background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: parent.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                    onEditingFinished: discord.setAppId(text)
                    Component.onCompleted: text = discord.appId
                    Connections { target: discord; function onChanged() { if (!discordAppId.activeFocus) discordAppId.text = discord.appId } }
                    Accessible.name: "Discord application ID"
                }
                StyledCheck { text: "Hide when paused"; checked: discord.hidePaused; onToggled: discord.setPref("hidePaused", checked) }
                StyledCheck { text: "Hide cover art"; checked: discord.hideCover; onToggled: discord.setPref("hideCover", checked) }
                StyledCheck { text: "Privacy mode (don't share track details)"; checked: discord.privacy; onToggled: discord.setPref("privacy", checked) }
            }
        }
        SettingsSection {
            id: sec_desktop
            objectName: "settings_desktop"
            title: "Desktop"
            keywords: "tray notifications focus close quit minimize exit background mini player title bar window frame decorations frameless maximize buttons left right side start page open on"
            query: page.query
            StyledCheck {
                visible: shell.trayAvailable
                text: "Show system tray icon"
                checked: shell.trayEnabled
                onToggled: shell.setTrayEnabled(checked)
            }
            StyledCheck {
                objectName: "customTitleBar"
                text: "Use Hallucinate's own title bar, built into the window"
                checked: shell.customTitleBar
                onToggled: shell.setCustomTitleBar(checked)
            }
            StyledCheck {
                objectName: "titleBarMinimize"
                visible: shell.customTitleBar
                leftPadding: 28
                text: "Show the minimize button"
                checked: shell.titleBarMinimize
                onToggled: shell.setTitleBarMinimize(checked)
            }
            Flow {
                visible: shell.customTitleBar
                width: parent.width
                spacing: 10
                leftPadding: 28
                Text { textFormat: Text.PlainText; text: "Buttons on the"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "titleBarSide"
                    width: 200
                    model: ["Right", "Left"]
                    selection: shell.titleBarSide === "left" ? 1 : 0
                    onActivated: shell.setTitleBarSide(currentIndex === 1 ? "left" : "right")
                    Accessible.name: "Title bar buttons side"
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: shell.customTitleBar
                      ? "Drag the top of the window (beside the search) to move it, double-click it to maximize. Turn this off for your system's own title bar."
                      : "Your system draws the window's title bar."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Row {
                spacing: 12
                Text { anchors.verticalCenter: parent.verticalCenter; text: "When I close the window"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                StyledCombo {
                    objectName: "closeAction"
                    width: 250
                    readonly property var actions: ["ask", "quit"].concat(shell.canMinimize ? ["minimize"] : [])
                                                                  .concat(["tray"])
                    readonly property var labels: ({ ask: "Ask every time", quit: "Quit", minimize: "Minimize",
                                                     tray: "Keep playing in the background" })
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
                text: "Your window manager has no minimize, so the choices are quitting or keeping it playing in the background (in the tray when your bar shows tray icons; otherwise open Hallucinate again to bring the window back)."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            StyledCheck {
                visible: Qt.platform.os === "linux" || shell.trayAvailable
                text: "Show desktop notifications when tracks change"
                checked: shell.desktopNotifications
                onToggled: shell.setDesktopNotifications(checked)
            }
            StyledCheck {
                objectName: "notifyAlways"
                visible: shell.desktopNotifications
                leftPadding: 28
                text: "Even while Hallucinate's window is in front (off: only when you're elsewhere)"
                checked: shell.notifyAlways
                onToggled: shell.setNotifyAlways(checked)
            }
            Flow {
                width: parent.width
                spacing: 10
                Text { textFormat: Text.PlainText; text: "Open on"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); height: 38; verticalAlignment: Text.AlignVCenter }
                StyledCombo {
                    objectName: "startPage"
                    readonly property var pages: ["home", "last", "albums", "artists", "songs", "folders", "liked", "stats", "history"]
                    width: 220
                    model: ["Home", "The page I left it on", "Albums", "Artists", "Songs", "Folders", "Liked Songs", "Stats", "History"]
                    selection: Math.max(0, pages.indexOf(shell.startPage))
                    onActivated: shell.setStartPage(pages[currentIndex])
                    Accessible.name: "Page Hallucinate opens on"
                }
            }
            PillButton { text: "Open mini player"; onClicked: shell.toggleMini() }

        }
        SettingsSection {
            id: sec_about
            objectName: "settings_about"
            title: "About"
            keywords: "version debug bug report update check logo"
            query: page.query
            Image {
                width: 260
                height: 210
                source: "../assets/logo.png"
                fillMode: Image.PreserveAspectFit
                sourceSize: Qt.size(600, 600)
                smooth: true
                Accessible.name: "Hallucinate logo"
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Hallucinate " + shell.appVersion + " — a modern music library and player"
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Flow {
                width: parent.width
                spacing: 10
                PillButton {
                    objectName: "copyDebugInfo"
                    text: "Copy debug info"
                    onClicked: { shell.copyDebugInfo(); Nav.notify("Debug info copied — paste it into your bug report") }
                }
                PillButton {
                    text: "Report a bug"
                    onClicked: Qt.openUrlExternally("https://github.com/Phosphene-dev/Hallucinate/issues/new")
                }
            }
            Text {
                textFormat: Text.PlainText
                visible: !shell.updates.supported
                text: "Updates come through your software centre or package manager."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Flow {  // wraps in a narrow window instead of running off its edge
                visible: shell.updates.supported
                width: parent.width
                spacing: 12
                StyledCheck {
                    objectName: "updateChecks"
                    width: Math.min(implicitWidth, parent.width)
                    text: "Tell me when a new version is out (checks GitHub once a day)"
                    checked: shell.updates.enabled
                    onToggled: shell.updates.setEnabled(checked)
                }
                PillButton {
                    height: 32
                    text: shell.updates.busy ? "Checking…" : "Check now"
                    enabled: !shell.updates.busy && !shell.offlineMode
                    onClicked: shell.updates.checkNow()
                }
                PillButton {
                    objectName: "updateNow"
                    height: 32
                    primary: true
                    visible: shell.updates.canInstall && (shell.updates.available || shell.updates.installing)
                    text: shell.updates.installing ? "Cancel" : "Update now"
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
                text: "Debug info lists versions, your system, display and audio setup and the recent log. It leaves out "
                    + "file paths, your music and account names."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
    }
    }
}
