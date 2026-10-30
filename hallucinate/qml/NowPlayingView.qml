import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import "."

// Now Playing, filling the window: the visualizer as a living backdrop in the cover's colours, the cover (or the
// record sliding out of its sleeve), the track and the controls. Controls fade away when the pointer rests.
// Opens by melting in: it fades up while the picture settles from slightly enlarged and blurred-looking.
Item {
    id: view
    objectName: "nowPlayingView"
    property bool open: false
    readonly property bool shown: open || melt.running
    // Fully faded in: the window underneath can't be seen, so it needn't be drawn (main.qml)
    readonly property bool covering: open && !melt.running && opacity === 1
    readonly property bool vinyl: shell.nowPlayingVinyl
    // The Deck (a 90s hi-fi front panel) instead of the cover and visualizer: your choice, or a retro theme's
    property string deckChoice: shell.uiValue("nowPlayingDeck", "")
    readonly property bool deck: deckChoice === "1" || (deckChoice === "" && Theme.retro)
    function setDeck(on) { deckChoice = on ? "1" : "0"; shell.setUiValue("nowPlayingDeck", deckChoice) }
    // A neon theme's own Now Playing: the cockpit or the terminal, or the usual one ("classic"); your choice
    readonly property string neonMode: Theme.neon ? (shell.ui.neonNowPlaying || "cockpit") : ""
    readonly property bool neonView: !deck && (neonMode === "cockpit" || neonMode === "terminal")
    function setNeonMode(m) { shell.setUiValue("neonNowPlaying", m) }
    property bool idle: false
    property bool lyricsMode: shell.uiValue("nowPlayingLyrics", "0") === "1"
    onLyricsModeChanged: { shell.setUiValue("nowPlayingLyrics", lyricsMode ? "1" : "0"); refit() }
    // What fits a small window (#113), the least needed going first: 1 a two-line, smaller title and no genres;
    // 2 no rating or signal path; 3 a one-line title, no album line; 4 no quality badges. Worked out again when
    // the window, the song or the view changes. The cover goes when it would leave the controls too little room.
    property int fold: 0
    function fit() { if (info.implicitHeight > content.height + 0.5 && fold < 4) { fold++; Qt.callLater(fit) } }
    function refit() { fold = 0; Qt.callLater(fit) }
    onWidthChanged: refit()
    onHeightChanged: refit()
    Connections { target: player; function onCurrentChanged() { view.refit() } }
    visible: opacity > 0
    opacity: open ? 1 : 0
    enabled: open
    focus: open
    Behavior on opacity { NumberAnimation { id: melt; duration: Theme.reduceMotion ? 0 : 520; easing.type: Easing.InOutCubic } }
    readonly property var styles: [
        { id: "liquid", t: "Liquid" }, { id: "aurora", t: "Aurora" }, { id: "nebula", t: "Nebula" },
        { id: "halo", t: "Halo" }, { id: "waves", t: "Waves" }, { id: "bars", t: "Bars" }
    ].concat(Theme.neon ? [{ id: "tunnel", t: "Tunnel" }, { id: "wires", t: "Wires" }, { id: "rain", t: "Neon rain" }] : [])  // (a neon theme's own)

    function toggle() { open = !open }
    onOpenChanged: { idle = false; if (open) idleTimer.restart() }
    Keys.onEscapePressed: open = false

    Rectangle { anchors.fill: parent; color: "#06040b" }

    Item {
        id: stage
        anchors.fill: parent
        visible: !view.deck && !view.neonView
        // the melt: the scene settles from a slight zoom as it fades in
        scale: view.open || Theme.reduceMotion ? 1 : 1.06
        Behavior on scale { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }

        Visualizer {
            id: vis
            objectName: "nowPlayingVisualizer"
            anchors.fill: parent
            style: shell.visualizerStyle
            active: view.shown
            quality: 0.45
        }
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.rgba(0, 0, 0, 0.5) }
                GradientStop { position: 0.6; color: Qt.rgba(0, 0, 0, 0.15) }
                GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.35) }
            }
        }

        RowLayout {
            id: content
            objectName: "nowPlayingContent"
            readonly property real edge: Math.max(parent.width < 720 ? 20 : 48, parent.width * 0.08)
            anchors { fill: parent; leftMargin: edge; rightMargin: edge
                      topMargin: 90; bottomMargin: 70 }
            spacing: Math.max(36, parent.width * 0.05)

            // Cover, or the record half out of its sleeve
            Item {
                id: art
                readonly property real side: Math.min(content.height * 0.86, content.width * (view.vinyl ? 0.34 : 0.42))
                Layout.preferredWidth: side * (view.vinyl ? 1.5 : 1)
                Layout.preferredHeight: side
                Layout.alignment: Qt.AlignVCenter
                Behavior on Layout.preferredWidth { NumberAnimation { duration: 420; easing.type: Easing.OutCubic } }
                // in a narrow window the cover makes way, rather than leave the controls too little room (#113)
                visible: content.width - side * (view.vinyl ? 1.5 : 1) - content.spacing >= controls.implicitWidth + 8

                Item {
                    id: record
                    objectName: "vinylRecord"
                    width: art.side * 0.96; height: width
                    anchors.verticalCenter: parent.verticalCenter
                    x: view.vinyl ? art.side * 0.5 : art.side * 0.02
                    opacity: view.vinyl ? 1 : 0
                    Behavior on x { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                    Behavior on opacity { NumberAnimation { duration: 300 } }
                    RotationAnimator on rotation {
                        from: 0; to: 360; duration: 1800 * 2  // 33⅓ rpm is too dizzy on screen; a calm half speed
                        loops: Animation.Infinite
                        running: view.vinyl && view.shown && player.playing && !Theme.reduceMotion
                    }
                    Rectangle {
                        anchors.fill: parent
                        radius: width / 2
                        gradient: Gradient {
                            GradientStop { position: 0; color: "#1b1820" }
                            GradientStop { position: 0.5; color: "#0b0a0e" }
                            GradientStop { position: 1; color: "#18151d" }
                        }
                    }
                    // grooves
                    Repeater {
                        model: 9
                        Rectangle {
                            required property int index
                            anchors.centerIn: parent
                            width: record.width * (0.92 - index * 0.06); height: width
                            radius: width / 2
                            color: "transparent"
                            border.width: 1
                            border.color: Qt.rgba(1, 1, 1, index % 3 === 0 ? 0.08 : 0.04)
                        }
                    }
                    // a sheen that stays put while the record turns underneath it
                    Cover {
                        anchors.centerIn: parent
                        width: record.width * 0.36; height: width
                        radius: width / 2
                        source: player.hasTrack ? player.current.artUrl || "" : ""
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: record.width * 0.03; height: width; radius: width / 2
                        color: "#06040b"
                    }
                }
                Rectangle {
                    anchors.centerIn: record
                    width: record.width; height: width; radius: width / 2
                    visible: record.opacity > 0
                    opacity: 0.5 * record.opacity
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.2; color: "transparent" }
                        GradientStop { position: 0.45; color: Qt.rgba(1, 1, 1, 0.09) }
                        GradientStop { position: 0.6; color: "transparent" }
                    }
                }

                // The sleeve
                Item {
                    id: sleeve
                    width: art.side; height: art.side
                    anchors.verticalCenter: parent.verticalCenter
                    Repeater {  // a soft shadow from stacked outlines (works without effects)
                        model: 6
                        Rectangle {
                            required property int index
                            anchors { fill: parent; margins: -(index + 1) * 3; topMargin: -(index + 1) * 3 + 10 }
                            radius: 22 + (index + 1) * 3
                            color: "transparent"
                            border.width: 3
                            border.color: Qt.rgba(0, 0, 0, 0.12 - index * 0.018)
                        }
                    }
                    Cover {
                        objectName: "nowPlayingCover"
                        anchors.fill: parent
                        radius: view.vinyl ? 6 : 22
                        source: player.hasTrack ? player.current.artUrl || "" : ""
                        fallback: player.hasTrack ? (player.current.title || "?").charAt(0) : ""
                        Accessible.role: Accessible.Graphic
                        Accessible.name: player.hasTrack ? "Cover of " + (player.current.album || player.current.title || "") : "No cover"
                        MouseArea {  // right-click the cover for the song's menu
                            anchors.fill: parent
                            enabled: player.hasTrack
                            acceptedButtons: Qt.RightButton
                            onPressAndHold: Nav.trackMenu(player.current.path, player.current.title, "playing", -1)
                            onClicked: Nav.trackMenu(player.current.path, player.current.title, "playing", -1)
                        }
                    }
                }
            }

            // Track and controls
            ColumnLayout {
                id: info
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                Layout.fillHeight: view.lyricsMode  // the lyrics take what's left of the height
                Layout.maximumHeight: content.height
                spacing: 10
                onImplicitHeightChanged: Qt.callLater(view.fit)
                Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: player.hasTrack ? player.current.title : "Nothing playing"
                    color: "white"
                    font.family: Theme.displayFamily
                    font.pixelSize: (Theme.fontSize(view.lyricsMode || view.fold >= 1 ? Math.min(24, Math.max(20, view.width / 36))
                                                                                       : Math.max(26, Math.min(46, view.width / 30)))) * Theme.displayScale
                    font.weight: Font.Bold
                    wrapMode: Text.Wrap
                    maximumLineCount: view.fold >= 3 ? 1 : view.fold >= 1 ? 2 : 3
                    elide: Text.ElideRight
                }
                QualityBadges {  // E and Hi-Res, as on the song's row
                    objectName: "nowPlayingQuality"
                    visible: view.fold < 4
                    light: true
                    size: 18
                    explicitTag: player.hasTrack ? player.current.explicit || 0 : 0
                    bitDepth: player.hasTrack ? player.current.bit_depth || 0 : 0
                    sampleRate: player.hasTrack ? player.current.sample_rate || 0 : 0
                }
                Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    visible: player.hasTrack
                    text: player.hasTrack ? player.current.artist : ""
                    color: Qt.rgba(1, 1, 1, 0.88)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(view.lyricsMode ? 16 : 20)
                    elide: Text.ElideRight
                    Accessible.role: Accessible.Link
                    Accessible.name: text
                    Accessible.onPressAction: { view.open = false; Nav.openArtist(player.current.album_artist || player.current.artist) }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { view.open = false; Nav.openArtist(player.current.album_artist || player.current.artist) }
                    }
                }
                Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    visible: player.hasTrack && (player.current.album || "").length > 0 && !view.lyricsMode && view.fold < 3
                    text: player.hasTrack ? [player.current.album, player.current.year > 0 ? String(player.current.year) : ""]
                                            .filter(s => s).join("  ·  ") : ""
                    color: Qt.rgba(1, 1, 1, 0.6)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(15)
                    elide: Text.ElideRight
                    Accessible.role: Accessible.Link
                    Accessible.name: text
                    Accessible.onPressAction: { view.open = false; Nav.openAlbum(player.current.album_key) }
                    MouseArea {
                        anchors.fill: parent
                        enabled: player.hasTrack && (player.current.album_key || "").length > 0
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { view.open = false; Nav.openAlbum(player.current.album_key) }
                    }
                }
                GenreLinks {  // the song's genres: each opens its page
                    objectName: "nowPlayingGenres"
                    Layout.fillWidth: true
                    visible: player.hasTrack && !view.lyricsMode && names.length > 0 && view.fold < 1
                    names: {
                        var text = player.hasTrack ? shell.genresText(player.current.genre || "", shell.allGenresSongs) : ""
                        return text ? text.split(", ") : []
                    }
                    color: Qt.rgba(1, 1, 1, 0.6)
                    pixelSize: Theme.fontSize(14)
                    onPicked: view.open = false
                }
                // Lyrics, karaoke style: the sung line large and bright, the others fading with distance
                Item {
                    id: lyricsBox
                    objectName: "nowPlayingLyrics"
                    visible: view.lyricsMode
                    Layout.fillWidth: true
                    Layout.maximumWidth: 640
                    Layout.topMargin: 14
                    Layout.rightMargin: 24  // long lines wrap before the window's edge
                    Layout.fillHeight: true
                    Layout.preferredHeight: 60
                    Layout.minimumHeight: 40
                    Layout.maximumHeight: 380
                    ListView {
                        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
                        id: lyricLines
                        anchors.fill: parent
                        visible: lyricsCtl.status === "found" && lyricsCtl.synced
                        clip: true
                        interactive: false
                        model: lyricsCtl.lines
                        spacing: 10
                        topMargin: 10
                        bottomMargin: 10
                        highlightRangeMode: ListView.StrictlyEnforceRange
                        preferredHighlightBegin: height * 0.38
                        preferredHighlightEnd: height * 0.38 + 40
                        currentIndex: Math.max(0, lyricsCtl.currentLine)
                        highlightMoveDuration: 380
                        delegate: Text {
                            textFormat: Text.PlainText
                            required property var modelData
                            required property int index
                            readonly property int distance: Math.abs(index - lyricsCtl.currentLine)
                            width: lyricLines.width
                            text: modelData.text.length ? modelData.text : "♪"
                            wrapMode: Text.WordWrap
                            color: "white"
                            opacity: distance === 0 ? 1 : Math.max(0.12, 0.62 - 0.14 * distance)
                            font.family: Theme.displayFamily
                            font.pixelSize: (Theme.fontSize(distance === 0 ? 26 : 20)) * Theme.displayScale
                            font.weight: distance === 0 ? Font.Bold : Font.DemiBold
                            Behavior on opacity { NumberAnimation { duration: 260 } }
                            Accessible.role: Accessible.Button
                            Accessible.name: text
                            Accessible.description: "Play from this line"
                            Accessible.onPressAction: player.seek(Math.max(0, modelData.t - lyricsCtl.offset))  // where the line shows, timing nudge and all
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: player.seek(Math.max(0, modelData.t - lyricsCtl.offset)) }
                        }
                    }
                    Flickable {
                        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
                        anchors.fill: parent
                        visible: lyricsCtl.status === "found" && !lyricsCtl.synced
                        clip: true
                        topMargin: 10
                        bottomMargin: 10
                        contentHeight: plainLyrics.implicitHeight
                        boundsBehavior: Flickable.StopAtBounds
                        Text {
                            textFormat: Text.PlainText
                            id: plainLyrics
                            width: parent.width
                            text: lyricsCtl.plain
                            wrapMode: Text.WordWrap
                            color: Qt.rgba(1, 1, 1, 0.85)
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSize(17)
                            lineHeight: 1.3
                        }
                    }
                    Text {
                        textFormat: Text.PlainText
                        anchors.verticalCenter: parent.verticalCenter
                        visible: lyricsCtl.status !== "found"
                        text: lyricsCtl.status === "loading" ? "Looking for lyrics…" : "No lyrics for this song"
                        color: Qt.rgba(1, 1, 1, 0.55)
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(16)
                    }
                }
                LyricsTiming {
                    visible: view.lyricsMode && lyricsCtl.status === "found" && lyricsCtl.synced
                    tint: Qt.rgba(1, 1, 1, 0.7)
                }
                StarRating {
                    objectName: "nowPlayingRating"
                    visible: !(player.current.kind || "").length && view.fold < 2
                    Layout.topMargin: 2
                    path: player.hasTrack ? player.current.path || "" : ""
                    size: 20
                    onColor: "white"
                    offColor: Qt.rgba(1, 1, 1, 0.35)
                }
                SignalPath { light: true; Layout.topMargin: 4; visible: stages.length > 0 && view.fold < 2 }
                Item { Layout.preferredHeight: 12; visible: view.fold < 2 }
                WaveformSeek {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 640
                    Layout.preferredHeight: 44
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 640
                    Text { text: Theme.fmtTime(player.position); color: Qt.rgba(1, 1, 1, 0.65); font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); textFormat: Text.PlainText }
                    Item { Layout.fillWidth: true }
                    Text {
                        readonly property bool live: player.hasTrack && player.current.kind === "station"
                        text: live ? "LIVE" : Theme.fmtTime(player.duration)
                        color: Qt.rgba(1, 1, 1, live ? 0.9 : 0.65)
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: live ? Font.Bold : Font.Normal
                        textFormat: Text.PlainText
                    }
                }
                Row {
                    id: controls
                    spacing: view.width < 600 ? 6 : 14
                    readonly property bool episode: player.hasTrack && player.current.kind === "episode"
                    readonly property bool music: player.hasTrack && !(player.current.kind || "").length
                    IconButton { anchors.verticalCenter: parent.verticalCenter; visible: !parent.episode; icon: "shuffle"; size: 22; active: player.shuffle; onClicked: player.toggleShuffle() }
                    IconButton { anchors.verticalCenter: parent.verticalCenter; visible: parent.episode; icon: "skipback:" + podcasts.options.skipBack; size: 24; tip: "Back " + podcasts.options.skipBack + " seconds"; onClicked: player.seekBy(-1000 * podcasts.options.skipBack) }
                    IconButton { anchors.verticalCenter: parent.verticalCenter; icon: "prev"; size: 24; onClicked: player.previous() }
                    Rectangle {
                        width: 64; height: 64; radius: Theme.round(32)
                        scale: Theme.reduceMotion ? 1 : (bigPlay.pressed ? 0.94 : (bigPlay.containsMouse ? 1.06 : 1))
                        Behavior on scale { NumberAnimation { duration: 120 } }
                        color: "white"
                        Icon {
                            anchors.centerIn: parent
                            anchors.horizontalCenterOffset: player.playing ? 0 : 2
                            width: 24; height: 24
                            name: player.playing ? "pause" : "play"
                            color: "#120d18"
                        }
                        MouseArea { id: bigPlay; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: player.toggle() }
                        Accessible.role: Accessible.Button
                        Accessible.name: player.playing ? "Pause" : "Play"
                    }
                    IconButton { anchors.verticalCenter: parent.verticalCenter; icon: "next"; size: 24; onClicked: player.next() }
                    IconButton { anchors.verticalCenter: parent.verticalCenter; visible: parent.episode; icon: "skipfwd:" + podcasts.options.skipForward; size: 24; tip: "Forward " + podcasts.options.skipForward + " seconds"; onClicked: player.seekBy(1000 * podcasts.options.skipForward) }
                    IconButton {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !parent.episode
                        icon: player.repeat === 2 ? "repeat1" : "repeat"
                        size: 22
                        active: player.repeat !== 0
                        onClicked: player.cycleRepeat()
                    }
                    IconButton {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: parent.music && shell.features.liked !== false
                        icon: "heart"; size: 22
                        active: player.hasTrack && userLib.likesRevision >= 0 && userLib.isLiked(player.current.path)
                        tip: "Like"
                        onClicked: if (player.hasTrack) userLib.toggleLike(player.current.path)
                    }
                    VolumeButton {  // a click opens the slider above it; scroll to change, middle-click to mute
                        objectName: "nowPlayingVolume"
                        anchors.verticalCenter: parent.verticalCenter
                        popupSlider: true
                        iconSize: 22
                    }
                }
            }
        }
    }

    Loader {
        anchors.fill: parent
        active: view.deck && view.shown
        sourceComponent: DeckView { active: view.open }
    }
    Loader {
        anchors.fill: parent
        active: view.neonView && view.shown
        sourceComponent: NeonNowPlaying { active: view.open; mode: view.neonMode; onCloseRequested: view.open = false }
    }

    // Top bar: leave, styles, vinyl, full screen. Fades out with the pointer at rest.
    Item {
        id: chrome
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 76
        opacity: view.idle ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 400 } }
        TitleDrag { anchors.fill: parent }  // Now Playing covers the window: its top row moves it
        IconButton {
            objectName: "closeNowPlaying"
            anchors { left: parent.left; leftMargin: 22; verticalCenter: parent.verticalCenter }
            icon: "down"; size: 22
            tip: "Close (Esc)"
            onClicked: view.open = false
        }
        Row {
            anchors { right: parent.right; rightMargin: 22; verticalCenter: parent.verticalCenter }
            spacing: 8
            // in a neon theme: which Now Playing
            Repeater {
                model: Theme.neon && !view.deck ? [{ id: "cockpit", t: "Cockpit" }, { id: "terminal", t: "Terminal" }, { id: "classic", t: "Classic" }] : []
                Chip {
                    required property var modelData
                    objectName: "neonMode_" + modelData.id
                    text: modelData.t
                    selected: view.neonMode === modelData.id
                    onClicked: view.setNeonMode(modelData.id)
                }
            }
            Item { width: Theme.neon && !view.deck ? 10 : 0; height: 1 }
            // the visualizer's style (the cockpit keeps its own, so the usual Now Playing keeps yours)
            Repeater {
                model: view.deck || view.neonMode === "terminal" ? [] : view.styles
                Chip {
                    required property var modelData
                    readonly property string current: view.neonView ? (shell.ui.neonVisStyle || "tunnel") : shell.visualizerStyle
                    text: modelData.t
                    selected: current === modelData.id
                    onClicked: view.neonView ? shell.setUiValue("neonVisStyle", modelData.id) : shell.setVisualizerStyle(modelData.id)
                }
            }
            Item { width: 6; height: 1 }
            IconButton {
                objectName: "deckToggle"
                anchors.verticalCenter: parent.verticalCenter
                icon: "deck"; active: view.deck
                tip: view.deck ? "Leave the Deck" : "The Deck: a 90s hi-fi"
                onClicked: view.setDeck(!view.deck)
            }
            IconButton {
                objectName: "lyricsToggle"
                visible: shell.features.lyrics !== false && !view.deck && !view.neonView
                anchors.verticalCenter: parent.verticalCenter
                icon: "note"; active: view.lyricsMode
                tip: view.lyricsMode ? "Hide lyrics" : "Show lyrics (L)"
                onClicked: view.lyricsMode = !view.lyricsMode
            }
            IconButton {
                objectName: "vinylToggle"
                visible: !view.deck && !view.neonView
                anchors.verticalCenter: parent.verticalCenter
                icon: "vinyl"; active: view.vinyl
                tip: view.vinyl ? "Show the cover" : "Show the record"
                onClicked: shell.setNowPlayingVinyl(!view.vinyl)
            }
            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                icon: "fullscreen"; active: Window.window && Window.window.visibility === Window.FullScreen
                tip: "Full screen (F11)"
                onClicked: view.toggleFullScreen()
            }
            WindowControls {
                anchors.verticalCenter: parent.verticalCenter
                light: true
            }
        }
    }
    Text {
        textFormat: Text.PlainText
        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 22 }
        visible: !view.deck && view.neonMode !== "terminal" && !player.visualizerEnabled && player.visualizerAvailable && shell.visualizerStyle !== "bars"
        opacity: view.idle ? 0 : 0.6
        Behavior on opacity { NumberAnimation { duration: 400 } }
        text: "Turn on “React to the music” on the Visualizer page to make the backdrop move with the sound"
        color: "white"
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(12)
    }

    function toggleFullScreen() {
        var w = Window.window
        if (!w) return
        w.visibility = w.visibility === Window.FullScreen ? Window.Windowed : Window.FullScreen
    }

    // Hide the controls and pointer after a few still seconds
    Timer { id: idleTimer; interval: 3000; onTriggered: view.idle = view.open }
    HoverHandler {
        cursorShape: view.idle ? Qt.BlankCursor : Qt.ArrowCursor
        onPointChanged: { view.idle = false; idleTimer.restart() }
    }
    // swallow clicks and wheel so nothing underneath reacts
    MouseArea { anchors.fill: parent; z: -2; onWheel: wheel => wheel.accepted = true
                Accessible.role: Accessible.Pane; Accessible.name: "Now Playing" }
}
