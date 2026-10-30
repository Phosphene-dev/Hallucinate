import QtQuick
import QtQuick.Shapes
import "."

// A neon theme's Now Playing, loaded only in one (NowPlayingView): your pick of two views.
//   cockpit  the song as seen from a pilot's seat: a holographic cover in a turning targeting ring, gauges for the
//            bass, mids and highs, a sync bar for how far in you are, readouts of the signal, and a warp tunnel
//            (or your own visualizer) behind it all. A title card announces each new song.
//   terminal the same, typed out by a machine on a wired network: a status block, a bar of # for the song, the
//            spectrum in block characters, what's next in the queue and the line of lyrics being sung.
// Motion stops with Reduce motion; the title card, the glitch and the colours are yours to choose (Settings →
// Appearance).
Item {
    id: neo
    objectName: "neonNowPlaying"
    property bool active: false
    property string mode: "cockpit"   // or "terminal"

    // --- what it shows ---------------------------------------------------------------------------------------
    readonly property var track: player.hasTrack ? player.current : ({})
    readonly property real progress: player.duration > 0 ? Math.min(1, player.position / player.duration) : 0
    readonly property bool moving: active && !Theme.reduceMotion
    readonly property var levels: player.visualizerEnabled ? (player.visualizerLevels || []) : []
    readonly property real u: Math.max(0.6, Math.min(width / 1280, height / 760))
    readonly property color ca: Theme.accent
    readonly property color cb: Theme.neonB
    readonly property string mono: Theme.monoFamily
    readonly property bool coverTint: shell.ui.neonTint === "cover"
    function avg(from, to) {
        var s = 0, n = 0
        for (var i = from; i < to && i < levels.length; i++) { s += levels[i]; n++ }
        return n ? s / n : 0
    }
    readonly property real bass: avg(0, 4)
    readonly property real mids: avg(4, 14)
    readonly property real highs: avg(14, 24)
    function clock(ms) {
        var s = Math.max(0, Math.floor(ms / 1000)), m = Math.floor(s / 60)
        return (m < 10 ? "0" : "") + m + ":" + (s % 60 < 10 ? "0" : "") + (s % 60)
    }
    function upper(s) { return String(s || "").toUpperCase() }
    // what the signal is, as a readout: FLAC · 24/96 · 2304 KBPS
    readonly property string signal: {
        var t = track, parts = []
        if (t.codec || t.fmt) parts.push(upper(t.codec || t.fmt))
        if (t.bit && t.sample) parts.push(t.bit + "/" + Math.round(t.sample / 1000 * 10) / 10)
        else if (t.sample) parts.push(Math.round(t.sample / 100) / 10 + " KHZ")
        if (t.bitrate) parts.push(Math.round(t.bitrate / 1000) + " KBPS")
        return parts.length ? parts.join(" · ") : (player.hasTrack ? "SIGNAL OK" : "NO SIGNAL")
    }
    readonly property string kindLabel: track.kind === "station" ? "LIVE FEED" : track.kind === "episode" ? "TRANSMISSION" : "TRACK"
    // the next few songs in the queue's order
    readonly property var upNext: {
        var out = [], n = player.upcomingCount, at = player.currentIndex  // (both re-read this when they change)
        for (var k = 1; k <= 5 && n >= 0; k++) {
            var it = player.queueModel.get(at + k)
            if (it && it.title) out.push(it)
        }
        return out
    }

    // --- the title card: a new song announced on black, for a moment ------------------------------------------
    readonly property bool cards: shell.ui.neonTitleCard !== "0"
    Connections {
        target: player
        function onCurrentChanged() { if (neo.active && neo.cards && player.hasTrack && neo.mode === "cockpit") card.show() }
    }

    Loader {
        anchors.fill: parent
        sourceComponent: neo.mode === "terminal" ? terminal : cockpit
    }

    // === cockpit ================================================================================================
    Component {
        id: cockpit
        Item {
            id: pit
            Rectangle { anchors.fill: parent; color: "#030208" }
            Visualizer {
                anchors.fill: parent
                style: shell.ui.neonVisStyle || "tunnel"
                active: neo.active
                quality: 0.4
                tint: neo.coverTint ? [] : [neo.ca, neo.cb, Qt.tint(neo.ca, Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, 0.5))]
            }
            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Qt.rgba(0, 0, 0, 0.72) }
                    GradientStop { position: 0.55; color: Qt.rgba(0, 0, 0, 0.25) }
                    GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.6) }
                }
            }

            // the holographic cover in its ring
            Item {
                id: holo
                readonly property real side: Math.min(pit.height * 0.5, pit.width * 0.3)
                width: side * 1.32; height: width
                x: Math.max(24 * neo.u, pit.width * 0.08 - side * 0.16)
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: -20 * neo.u
                visible: pit.width > 760
                // the targeting ring: ticks around, two arcs turning opposite ways
                Shape {
                    anchors.fill: parent
                    antialiasing: true
                    layer.enabled: true; layer.samples: 4
                    rotation: ringSpin.angle
                    ShapePath {
                        strokeColor: Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, 0.8); strokeWidth: 2; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap
                        PathAngleArc { centerX: holo.width / 2; centerY: holo.height / 2; radiusX: holo.width / 2 - 3; radiusY: radiusX; startAngle: -30; sweepAngle: 110 }
                    }
                    ShapePath {
                        strokeColor: Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, 0.8); strokeWidth: 2; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap
                        PathAngleArc { centerX: holo.width / 2; centerY: holo.height / 2; radiusX: holo.width / 2 - 3; radiusY: radiusX; startAngle: 150; sweepAngle: 110 }
                    }
                }
                Shape {
                    anchors.fill: parent
                    antialiasing: true
                    layer.enabled: true; layer.samples: 4
                    rotation: -ringSpin.angle * 1.6
                    ShapePath {
                        strokeColor: neo.ca; strokeWidth: 3; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap
                        PathAngleArc { centerX: holo.width / 2; centerY: holo.height / 2; radiusX: holo.width / 2 - 12; radiusY: radiusX; startAngle: 60; sweepAngle: 40 + 80 * neo.bass }
                    }
                    ShapePath {
                        strokeColor: Qt.rgba(neo.ca.r, neo.ca.g, neo.ca.b, 0.5); strokeWidth: 1; fillColor: "transparent"
                        PathAngleArc { centerX: holo.width / 2; centerY: holo.height / 2; radiusX: holo.width / 2 - 18; radiusY: radiusX; startAngle: 0; sweepAngle: 360 }
                    }
                }
                Repeater {  // ticks
                    model: 36
                    Rectangle {
                        required property int index
                        x: holo.width / 2 - width / 2; y: 0
                        width: index % 9 === 0 ? 3 : 1; height: index % 9 === 0 ? 10 : 5
                        color: Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, index % 9 === 0 ? 0.9 : 0.45)
                        transform: Rotation { origin.x: 0.5 * (index % 9 === 0 ? 3 : 1); origin.y: holo.height / 2; angle: index * 10 }
                    }
                }
                QtObject {
                    id: ringSpin
                    property real angle: 0
                    property NumberAnimation run: NumberAnimation {
                        target: ringSpin; property: "angle"; from: 0; to: 360; duration: 24000
                        loops: Animation.Infinite; running: neo.moving && player.playing
                    }
                }
                // the cover, as a hologram: tinted, lined, a light sweeping down it
                Item {
                    id: projection
                    width: holo.side; height: width
                    anchors.centerIn: parent
                    opacity: flicker.value
                    Cover {
                        anchors.fill: parent
                        radius: 0
                        source: player.hasTrack ? player.current.artUrl || "" : ""
                    }
                    Rectangle { anchors.fill: parent; color: Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, Theme.neonLoud ? 0.22 : 0.14) }
                    Column {
                        anchors.fill: parent
                        clip: true
                        Repeater {
                            model: Math.ceil(projection.height / 3)
                            Rectangle { width: projection.width; height: 3; color: index % 2 ? "transparent" : Qt.rgba(0, 0, 0, 0.22); required property int index }
                        }
                    }
                    Rectangle {
                        width: parent.width; height: Math.max(2, parent.height * 0.04)
                        y: sweep.value * (parent.height - height)
                        gradient: Gradient {
                            GradientStop { position: 0; color: "transparent" }
                            GradientStop { position: 1; color: Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, 0.5) }
                        }
                        visible: neo.moving
                    }
                    Bevel {}
                }
                QtObject {
                    id: sweep
                    property real value: 0
                    property NumberAnimation run: NumberAnimation {
                        target: sweep; property: "value"; from: 0; to: 1; duration: 3200
                        loops: Animation.Infinite; running: neo.moving
                    }
                }
                QtObject {  // a hologram's flicker, now and then
                    id: flicker
                    property real value: 1
                    property SequentialAnimation run: SequentialAnimation {
                        loops: Animation.Infinite; running: neo.moving && Theme.neonGlitch
                        PauseAnimation { duration: 4200 }
                        NumberAnimation { target: flicker; property: "value"; to: 0.55; duration: 40 }
                        NumberAnimation { target: flicker; property: "value"; to: 1; duration: 60 }
                        NumberAnimation { target: flicker; property: "value"; to: 0.7; duration: 30 }
                        NumberAnimation { target: flicker; property: "value"; to: 1; duration: 90 }
                    }
                }
                Text {  // a label under it, like a target's
                    anchors { top: parent.bottom; horizontalCenter: parent.horizontalCenter; topMargin: 6 * neo.u }
                    textFormat: Text.PlainText
                    text: "◢ " + neo.kindLabel + (neo.track.year ? " · " + neo.track.year : "") + " ◣"
                    color: Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, 0.85)
                    font.family: neo.mono; font.pixelSize: 13 * neo.u; font.letterSpacing: 2
                }
            }

            // the readouts, title and controls
            Column {
                id: panel
                anchors { left: holo.visible ? holo.right : parent.left; leftMargin: holo.visible ? 48 * neo.u : 32 * neo.u
                          right: parent.right; rightMargin: 40 * neo.u; verticalCenter: parent.verticalCenter }
                spacing: 14 * neo.u

                // a warning strip: paused, or a live feed
                Row {
                    spacing: 10
                    visible: player.hasTrack
                    Rectangle {
                        width: 120 * neo.u; height: 18 * neo.u
                        color: !player.playing ? Theme.error : neo.ca
                        clip: true
                        Row {
                            x: -stripes.value * 16
                            Repeater {
                                model: 14
                                Rectangle { width: 8; height: 30 * neo.u; y: -6 * neo.u; rotation: 30; color: "#000000"; opacity: 0.85
                                            x: index * 16; required property int index }
                            }
                        }
                        QtObject {
                            id: stripes
                            property real value: 0
                            property NumberAnimation run: NumberAnimation { target: stripes; property: "value"; from: 0; to: 1; duration: 600; loops: Animation.Infinite; running: neo.moving && !player.playing }
                        }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        textFormat: Text.PlainText
                        text: !player.playing ? "SIGNAL HOLD" : neo.kindLabel === "TRACK" ? "SYNC NOMINAL" : neo.kindLabel
                        color: !player.playing ? Theme.error : neo.ca
                        font.family: neo.mono; font.pixelSize: 14 * neo.u; font.letterSpacing: 3
                        opacity: !player.playing && neo.moving ? blink.value : 1
                    }
                }
                QtObject {
                    id: blink
                    property real value: 1
                    property SequentialAnimation run: SequentialAnimation {
                        loops: Animation.Infinite; running: neo.moving && !player.playing
                        NumberAnimation { target: blink; property: "value"; to: 0.25; duration: 500 }
                        NumberAnimation { target: blink; property: "value"; to: 1; duration: 500 }
                    }
                }

                // the title, with a split of magenta and cyan behind it in a loud theme
                Item {
                    width: panel.width
                    height: title.implicitHeight
                    Text {
                        x: -2; y: 1
                        width: parent.width; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.Wrap
                        visible: Theme.neonLoud
                        textFormat: Text.PlainText; text: title.text; font: title.font
                        color: Qt.rgba(neo.ca.r, neo.ca.g, neo.ca.b, 0.7)
                    }
                    Text {
                        x: 2; y: -1
                        width: parent.width; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.Wrap
                        visible: Theme.neonLoud
                        textFormat: Text.PlainText; text: title.text; font: title.font
                        color: Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, 0.7)
                    }
                    Text {
                        id: title
                        objectName: "neonTitle"
                        width: parent.width; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                        text: player.hasTrack ? neo.track.title || "" : "Nothing playing"
                        color: "#ffffff"
                        font.family: Theme.displayFamily; font.pixelSize: Math.max(24, 54 * neo.u); font.weight: Font.DemiBold
                    }
                }
                Text {
                    width: panel.width; elide: Text.ElideRight
                    textFormat: Text.PlainText
                    text: [neo.track.artist, neo.track.album].filter(function (s) { return !!s }).join("  //  ")
                    color: neo.cb
                    font.family: Theme.displayFamily; font.pixelSize: Math.max(14, 22 * neo.u)
                }

                // gauges: bass, mids, highs
                Row {
                    spacing: 22 * neo.u
                    Repeater {
                        model: 3  // (a number, not a list of values: the delegates stay as the levels change)
                        Item {
                            required property int index
                            readonly property var modelData: ({ n: ["LOW", "MID", "HIGH"][index], v: index === 0 ? neo.bass : index === 1 ? neo.mids : neo.highs })
                            width: 86 * neo.u; height: 64 * neo.u
                            Shape {
                                anchors.fill: parent
                                antialiasing: true
                                layer.enabled: true; layer.samples: 4
                                ShapePath {
                                    strokeColor: Qt.rgba(1, 1, 1, 0.14); strokeWidth: 6 * neo.u; fillColor: "transparent"; capStyle: ShapePath.FlatCap
                                    PathAngleArc { centerX: 43 * neo.u; centerY: 50 * neo.u; radiusX: 36 * neo.u; radiusY: radiusX; startAngle: 180; sweepAngle: 180 }
                                }
                                ShapePath {
                                    strokeColor: modelData.v > 0.8 ? Theme.error : neo.ca; strokeWidth: 6 * neo.u; fillColor: "transparent"; capStyle: ShapePath.FlatCap
                                    PathAngleArc { centerX: 43 * neo.u; centerY: 50 * neo.u; radiusX: 36 * neo.u; radiusY: radiusX; startAngle: 180; sweepAngle: Math.max(1, 180 * Math.min(1, modelData.v)) }
                                }
                            }
                            Text {
                                anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom }
                                textFormat: Text.PlainText
                                text: modelData.n + " " + Math.round(modelData.v * 100)
                                color: Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, 0.9)
                                font.family: neo.mono; font.pixelSize: 12 * neo.u
                            }
                        }
                    }
                    // the readouts
                    Column {
                        spacing: 3
                        anchors.verticalCenter: parent.verticalCenter
                        Repeater {
                            model: 4
                            Text {
                                required property int index
                                textFormat: Text.PlainText
                                text: index === 0 ? "SIGNAL  " + neo.signal
                                    : index === 1 ? "TIME    " + neo.clock(player.position) + " / " + neo.clock(player.duration)
                                    : index === 2 ? "QUEUE   " + player.upcomingCount + " TO COME"
                                    : "OUTPUT  " + (player.muted ? "MUTED" : Math.round(player.volume * 100) + "%")
                                color: Theme.text; opacity: 0.85
                                font.family: neo.mono; font.pixelSize: 13 * neo.u
                            }
                        }
                    }
                }

                // the sync bar: how far into the song, in cells; click or drag to seek
                Item {
                    width: panel.width; height: 30 * neo.u
                    Row {
                        id: cells
                        readonly property int count: Math.max(10, Math.floor(parent.width / (12 * neo.u)))
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3 * neo.u
                        Repeater {
                            model: cells.count
                            Rectangle {
                                required property int index
                                readonly property bool lit: index < Math.round(neo.progress * cells.count)
                                width: 9 * neo.u; height: 16 * neo.u
                                color: lit ? (index === Math.round(neo.progress * cells.count) - 1 ? "#ffffff" : neo.ca) : Qt.rgba(1, 1, 1, 0.08)
                            }
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        enabled: player.duration > 0
                        cursorShape: Qt.PointingHandCursor
                        function at(m) { player.seek(Math.max(0, Math.min(1, m.x / width)) * player.duration) }
                        onPressed: function (m) { at(m) }
                        onPositionChanged: function (m) { if (pressed) at(m) }
                    }
                    Accessible.role: Accessible.Slider
                    Accessible.name: "Position"
                }
                Text {
                    textFormat: Text.PlainText
                    text: "SYNC RATIO " + (neo.progress * 100).toFixed(1) + "%"
                    color: Qt.rgba(neo.ca.r, neo.ca.g, neo.ca.b, 0.9)
                    font.family: neo.mono; font.pixelSize: 12 * neo.u; font.letterSpacing: 2
                }

                Row {
                    spacing: 6
                    IconButton { icon: "shuffle"; size: 22; active: player.shuffle; onClicked: player.toggleShuffle() }
                    IconButton { icon: "prev"; size: 26; onClicked: player.previous() }
                    Rectangle {
                        width: 58; height: 58
                        color: neo.ca
                        anchors.verticalCenter: parent.verticalCenter
                        Icon { anchors.centerIn: parent; width: 26; height: 26; name: player.playing ? "pause" : "play"; color: Theme.onAccent }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: player.toggle() }
                        Accessible.role: Accessible.Button
                        Accessible.name: player.playing ? "Pause" : "Play"
                        Accessible.onPressAction: player.toggle()
                        Bevel {}
                    }
                    IconButton { icon: "next"; size: 26; onClicked: player.next() }
                    IconButton { icon: player.repeat === 2 ? "repeat1" : "repeat"; size: 22; active: player.repeat !== 0; onClicked: player.cycleRepeat() }
                    VolumeButton { anchors.verticalCenter: parent.verticalCenter; popupSlider: true; iconSize: 22 }
                }
            }

            // HUD readouts in the corners
            Text {
                anchors { left: parent.left; bottom: parent.bottom; leftMargin: 24; bottomMargin: 18 }
                visible: Theme.neonGreebles
                textFormat: Text.PlainText
                text: "AFTERIMAGE · LAYER " + ((player.currentIndex + 1) % 100 < 10 ? "0" : "") + ((player.currentIndex + 1) % 100) + " · " + (player.playing ? "LINK ACTIVE" : "LINK IDLE")
                color: Qt.rgba(neo.cb.r, neo.cb.g, neo.cb.b, 0.6)
                font.family: neo.mono; font.pixelSize: 11; font.letterSpacing: 2
            }
        }
    }

    // === terminal ===============================================================================================
    Component {
        id: terminal
        Rectangle {
            id: term
            color: Qt.rgba(Theme.bg.r * 0.6, Theme.bg.g * 0.6, Theme.bg.b * 0.6, 1)
            readonly property real fs: Math.max(12, 17 * neo.u)
            readonly property color ink: Theme.neonLoud ? neo.cb : Theme.text
            readonly property color dim: Qt.rgba(ink.r, ink.g, ink.b, 0.55)
            readonly property int barWidth: Math.max(10, Math.min(60, Math.floor((width - 220) / (fs * 0.6)) - 22))
            function bar(p, n) {
                var lit = Math.round(p * n)
                return "[" + "#".repeat(lit) + "-".repeat(Math.max(0, n - lit)) + "]"
            }
            function pad(s, n) { s = String(s); return s.length >= n ? s : s + " ".repeat(n - s.length) }
            // the spectrum in block characters, eight rows high
            readonly property string spectrum: {
                var rows = [], blocks = " ▁▂▃▄▅▆▇█", lv = neo.levels
                if (!lv.length) return "  (turn on “React to the music” on the Visualizer page to see the spectrum)"
                for (var r = 3; r >= 0; r--) {
                    var line = "  "
                    for (var i = 0; i < 24; i++) {
                        var h = Math.max(0, Math.min(1, lv[i] || 0)) * 4 - r
                        line += (h >= 1 ? "█" : h <= 0 ? " " : blocks[Math.round(h * 8)]) + " "
                    }
                    rows.push(line)
                }
                return rows.join("\n")
            }

            Flickable {
                anchors { fill: parent; margins: 32 * neo.u; topMargin: 84 }
                contentHeight: lines.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                Column {
                    id: lines
                    width: parent.width
                    spacing: 2
                    component Line: Text {
                        width: lines.width
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        color: term.ink
                        font.family: neo.mono; font.pixelSize: term.fs
                    }
                    Line { text: "AFTERIMAGE TERMINAL  ::  wired link " + (player.playing ? "up" : "idle"); color: term.dim }
                    Line { text: " " }
                    Line { text: "> now_playing --verbose"; color: neo.ca }
                    Line { objectName: "terminalTitle"; text: "  title    : " + (player.hasTrack ? neo.track.title || "?" : "(nothing)") }
                    Line { text: "  artist   : " + (neo.track.artist || "-") }
                    Line { text: "  album    : " + (neo.track.album || "-") + (neo.track.year ? " (" + neo.track.year + ")" : "") }
                    Line { text: "  signal   : " + neo.signal.toLowerCase() }
                    Line { text: "  state    : " + (player.playing ? "playing" : "paused") + (player.shuffle ? " · shuffle" : "") + (player.repeat === 2 ? " · repeat one" : player.repeat ? " · repeat" : "") }
                    Line { text: "  " + term.bar(neo.progress, term.barWidth) + " " + neo.clock(player.position) + " / " + neo.clock(player.duration) + "  " + Math.round(neo.progress * 100) + "%" }
                    Line { text: " " }
                    Line { text: "> spectrum"; color: neo.ca }
                    Line { text: term.spectrum; wrapMode: Text.NoWrap; lineHeight: 0.9 }
                    Line { text: " " }
                    Line { text: "> queue --next " + neo.upNext.length; color: neo.ca; visible: neo.upNext.length > 0 }
                    Repeater {
                        model: neo.upNext
                        Line {
                            required property var modelData
                            required property int index
                            text: "  " + (index + 1 < 10 ? "0" : "") + (index + 1) + "  " + term.pad(modelData.title, 34) + "  " + (modelData.artist || "")
                            wrapMode: Text.NoWrap; elide: Text.ElideRight
                            color: index === 0 ? term.ink : term.dim
                        }
                    }
                    Line { text: " "; visible: neo.upNext.length > 0 }
                    Line { text: "> lyrics --line"; color: neo.ca; visible: lyricsCtl.status === "found" && lyricsCtl.synced }
                    Line {
                        visible: lyricsCtl.status === "found" && lyricsCtl.synced
                        text: "  " + ((lyricsCtl.lines[lyricsCtl.currentLine] || {}).text || "...")
                    }
                    Line { text: " "; visible: lyricsCtl.status === "found" && lyricsCtl.synced }
                    // the controls, as commands you can click
                    Flow {
                        width: lines.width
                        spacing: term.fs
                        Repeater {
                            model: [
                                { t: "[ prev ]", a: function () { player.previous() } },
                                { t: player.playing ? "[ pause ]" : "[ play ]", a: function () { player.toggle() } },
                                { t: "[ next ]", a: function () { player.next() } },
                                { t: player.shuffle ? "[ shuffle:on ]" : "[ shuffle:off ]", a: function () { player.toggleShuffle() } },
                                { t: player.repeat === 2 ? "[ repeat:one ]" : player.repeat ? "[ repeat:all ]" : "[ repeat:off ]", a: function () { player.cycleRepeat() } }
                            ]
                            Text {
                                required property var modelData
                                textFormat: Text.PlainText
                                text: modelData.t
                                color: cmd.containsMouse ? Theme.onAccent : neo.ca
                                font.family: neo.mono; font.pixelSize: term.fs
                                Rectangle { anchors.fill: parent; z: -1; color: neo.ca; visible: cmd.containsMouse }
                                MouseArea { id: cmd; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: modelData.a() }
                                Accessible.role: Accessible.Button
                                Accessible.name: modelData.t.replace(/[\[\]]/g, "").trim()
                                Accessible.onPressAction: modelData.a()
                            }
                        }
                    }
                    Row {
                        Line { width: implicitWidth; text: "> " }
                        Rectangle {  // the cursor
                            width: term.fs * 0.55; height: term.fs
                            color: term.ink
                            opacity: cursorBlink.on ? 1 : 0
                            Timer { id: cursorBlink; property bool on: true; interval: 530; repeat: true; running: neo.moving; onTriggered: on = !on }
                        }
                    }
                }
            }
        }
    }

    // === the title card =========================================================================================
    Rectangle {
        id: card
        objectName: "neonTitleCard"
        anchors.fill: parent
        color: "#000000"
        opacity: 0
        visible: opacity > 0
        function show() {
            cardTitle.text = neo.track.title || ""
            cardWho.text = neo.upper(neo.track.artist || "")
            cardNo.text = neo.kindLabel + " " + ((player.currentIndex + 1) < 10 ? "0" : "") + (player.currentIndex + 1)
            if (Theme.reduceMotion) return
            cardRun.restart()
        }
        SequentialAnimation {
            id: cardRun
            NumberAnimation { target: card; property: "opacity"; to: 1; duration: 90 }
            PauseAnimation { duration: 1500 }
            NumberAnimation { target: card; property: "opacity"; to: 0; duration: 380; easing.type: Easing.InQuad }
        }
        Column {
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: parent.width * 0.1 }
            spacing: 12 * neo.u
            Text {
                id: cardNo
                textFormat: Text.PlainText
                color: "#ffffff"
                font.family: "Serif"; font.pixelSize: 22 * neo.u; font.weight: Font.Bold; font.letterSpacing: 6
            }
            Text {
                id: cardTitle
                width: parent.width
                textFormat: Text.PlainText
                wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                color: "#ffffff"
                font.family: "Serif"; font.pixelSize: Math.max(34, 92 * neo.u); font.weight: Font.Black
                transform: Scale { xScale: 0.82 }
            }
            Rectangle { width: parent.width * 0.4; height: 3 * neo.u; color: neo.ca }
            Text {
                id: cardWho
                textFormat: Text.PlainText
                color: "#ffffff"; opacity: 0.85
                font.family: "Serif"; font.pixelSize: 26 * neo.u; font.weight: Font.Bold; font.letterSpacing: 4
            }
        }
        MouseArea { anchors.fill: parent; enabled: card.visible; onClicked: { cardRun.stop(); card.opacity = 0 } }
    }
}
