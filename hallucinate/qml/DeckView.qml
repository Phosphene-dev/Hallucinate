import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// The Deck: Now Playing as the front panel of a late-90s hi-fi. A cassette in its window (the cover is the label,
// the reels turn and the tape winds from one to the other as the song plays), a glowing display with seven- and
// fourteen-segment digits, a spectrum analyser and two VU meters fed by the music, and chunky keys.
// The display's colour and a CRT look are yours to choose; motion stops with "Reduce motion".
Item {
    id: deck
    objectName: "deckView"
    property bool active: false

    // --- what it shows ---------------------------------------------------------------------------------------
    readonly property var track: player.hasTrack ? player.current : ({})
    readonly property real progress: player.duration > 0 ? Math.min(1, player.position / player.duration) : 0
    readonly property bool moving: active && player.playing && !Theme.reduceMotion
    readonly property var levels: player.visualizerEnabled ? player.visualizerLevels : []
    property bool remaining: shell.uiValue("deckRemaining", "0") === "1"
    property string lcd: shell.uiValue("deckLcd", "amber")
    property bool crt: shell.uiValue("deckCrt", "0") === "1"
    readonly property var lcdColors: ({
        amber: { on: "#ffb43a", glow: "#ff8a00", ghost: "#2a1a06", bg: "#120b03" },
        green: { on: "#7dff8a", glow: "#2bff5a", ghost: "#0b2410", bg: "#040d06" },
        blue: { on: "#7fe3ff", glow: "#22b8ff", ghost: "#08202b", bg: "#020a0f" },
        red: { on: "#ff6a5c", glow: "#ff2a1a", ghost: "#2b0b08", bg: "#100302" }
    })
    readonly property var ink: lcdColors[lcd] || lcdColors.amber
    readonly property real u: Math.max(0.55, Math.min(width / 1280, height / 760))  // one unit of size

    // fonts for the display: seven-segment digits, fourteen-segment letters and a dot-matrix face
    FontLoader { id: seg7; source: Qt.resolvedUrl("../assets/fonts/DSEG7Classic-Bold.ttf") }
    FontLoader { id: seg14; source: Qt.resolvedUrl("../assets/fonts/DSEG14Classic-Regular.ttf") }
    FontLoader { id: dots; source: Qt.resolvedUrl("../assets/fonts/VT323-Regular.ttf") }
    readonly property string seg7Family: seg7.status === FontLoader.Ready ? seg7.font.family : "Monospace"
    readonly property string seg14Family: seg14.status === FontLoader.Ready ? seg14.font.family : "Monospace"
    readonly property string dotsFamily: dots.status === FontLoader.Ready ? dots.font.family : "Monospace"

    function clock(ms) {
        var s = Math.max(0, Math.floor(ms / 1000))
        var m = Math.floor(s / 60)
        if (m > 99) m = 99
        return (m < 10 ? "0" : "") + m + ":" + (s % 60 < 10 ? "0" : "") + (s % 60)
    }
    // What a fourteen-segment display can show: plain capitals, digits and a little punctuation
    function segText(s) {
        s = String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase()
        return s.replace(/[^A-Z0-9 \-.,'!?/()&+*:]/g, " ").replace(/\s+/g, " ").trim()
    }
    function save(key, value) { shell.setUiValue(key, value) }

    // --- the chassis -------------------------------------------------------------------------------------------
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#34373c" }
            GradientStop { position: 0.08; color: "#26282c" }
            GradientStop { position: 1; color: "#141517" }
        }
    }
    // brushed metal: fine horizontal grain, drawn once
    Canvas {
        anchors.fill: parent
        opacity: 0.35
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var seed = 7
            for (var y = 0; y < height; y += 2) {
                seed = (seed * 9301 + 49297) % 233280
                ctx.fillStyle = seed / 233280 > 0.5 ? "rgba(255,255,255,0.035)" : "rgba(0,0,0,0.05)"
                ctx.fillRect(0, y, width, 1)
            }
        }
    }

    component Screw: Rectangle {
        width: 14 * deck.u; height: width; radius: width / 2
        gradient: Gradient { GradientStop { position: 0; color: "#8d9096" } GradientStop { position: 1; color: "#3c3f44" } }
        border.color: "#1c1d20"
        Rectangle { anchors.centerIn: parent; width: parent.width * 0.7; height: 2; color: "#2a2c30"; rotation: 35 }
    }
    Screw { x: 14 * deck.u; y: 14 * deck.u }
    Screw { anchors.right: parent.right; anchors.rightMargin: 14 * deck.u; y: 14 * deck.u }
    Screw { x: 14 * deck.u; anchors.bottom: parent.bottom; anchors.bottomMargin: 14 * deck.u }
    Screw { anchors { right: parent.right; rightMargin: 14 * deck.u; bottom: parent.bottom; bottomMargin: 14 * deck.u } }

    // a label printed on the panel
    component Legend: Text {
        textFormat: Text.PlainText
        color: "#bdb6a2"
        font.family: deck.dotsFamily
        font.pixelSize: 15 * deck.u
        font.letterSpacing: 1.5
    }

    // a small indicator light with its label under it
    component Led: Column {
        id: led
        property bool lit: false
        property color tint: "#ff3b2f"
        property string label: ""
        spacing: 3 * deck.u
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 9 * deck.u; height: width; radius: width / 2
            color: led.lit ? led.tint : Qt.darker(led.tint, 3.4)
            border.color: "#0c0c0d"
            Rectangle {  // the glow
                anchors.centerIn: parent; width: parent.width * 2.6; height: width; radius: width / 2
                color: led.tint; opacity: led.lit ? 0.22 : 0; z: -1
                Behavior on opacity { NumberAnimation { duration: 120 } }
            }
        }
        Legend { anchors.horizontalCenter: parent.horizontalCenter; text: led.label; font.pixelSize: 12 * deck.u }
    }

    // a hardware key: bevelled, sinks when pressed
    component Key: Rectangle {
        id: key
        property string label: ""
        property string glyph: ""
        property bool latched: false
        signal activated()
        implicitWidth: 74 * deck.u
        implicitHeight: 48 * deck.u
        radius: 3 * deck.u
        readonly property bool down: area.pressed
        gradient: Gradient {
            GradientStop { position: 0; color: key.down ? "#2a2c30" : "#585c63" }
            GradientStop { position: 0.12; color: key.down ? "#303237" : "#45484e" }
            GradientStop { position: 1; color: key.down ? "#3a3d42" : "#2b2d31" }
        }
        border.color: "#0d0e10"
        Rectangle {  // top highlight
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 1 }
            height: 1; color: key.down ? "transparent" : "#7c8088"
        }
        Item {
            anchors.fill: parent
            anchors.topMargin: key.down ? 2 : 0
            Icon {
                visible: key.glyph.length > 0
                anchors.centerIn: parent
                width: 20 * deck.u; height: width
                name: key.glyph
                color: key.latched ? deck.ink.on : "#e6e1d2"
            }
            Legend {
                visible: key.label.length > 0
                anchors.centerIn: parent
                text: key.label
                color: key.latched ? deck.ink.on : "#e6e1d2"
                font.pixelSize: 16 * deck.u
            }
        }
        MouseArea { id: area; anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: key.activated() }
        Accessible.role: Accessible.Button
        Accessible.name: key.label || key.glyph
        Accessible.onPressAction: key.activated()
    }

    // --- layout --------------------------------------------------------------------------------------------------
    ColumnLayout {
        id: panel
        anchors { fill: parent; leftMargin: 44 * deck.u; rightMargin: 44 * deck.u; topMargin: 84 * deck.u; bottomMargin: 40 * deck.u }
        spacing: 22 * deck.u

        // the maker's plate
        RowLayout {
            Layout.fillWidth: true
            Text {
                textFormat: Text.PlainText
                text: qsTr("HALLUCINATE")
                color: "#e8e2d0"
                font.family: Theme.displayFamily
                font.pixelSize: 26 * deck.u
                font.letterSpacing: 6 * deck.u
            }
            Legend { text: qsTr("  HX-98  DIGITAL AUDIO DECK"); Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 3 * deck.u }
            Item { Layout.fillWidth: true }
            Legend { text: qsTr("DISPLAY"); Layout.alignment: Qt.AlignVCenter }
            Repeater {
                model: ["amber", "green", "blue", "red"]
                Rectangle {
                    required property string modelData
                    width: 16 * deck.u; height: width; radius: width / 2
                    color: deck.lcdColors[modelData].on
                    border.width: deck.lcd === modelData ? 2 : 1
                    border.color: deck.lcd === modelData ? "#ffffff" : "#000000"
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: { deck.lcd = parent.modelData; deck.save("deckLcd", parent.modelData) } }
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: qsTr("%1 display").arg(modelData)
                    Accessible.checked: deck.lcd === modelData
                }
            }
            Item { width: 12 * deck.u; height: 1 }
            Key {
                objectName: "deckCrt"
                label: qsTr("CRT"); latched: deck.crt
                implicitWidth: 56 * deck.u; implicitHeight: 30 * deck.u
                onActivated: { deck.crt = !deck.crt; deck.save("deckCrt", deck.crt ? "1" : "0") }
            }
            Item { width: 12 * deck.u; height: 1 }
            Led { lit: true; tint: "#3dff6a"; label: qsTr("POWER") }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 28 * deck.u

            // the cassette window
            Rectangle {
                id: window_
                Layout.preferredWidth: Math.min(panel.width * 0.4, 520 * deck.u)
                Layout.fillHeight: true
                radius: 6 * deck.u
                color: "#0b0b0d"
                border.color: "#050506"
                border.width: 2
                Rectangle {  // the cassette
                    id: cassette
                    anchors.centerIn: parent
                    width: Math.min(parent.width * 0.9, parent.height * 1.45)
                    height: width * 0.63
                    radius: 8 * deck.u
                    color: "#1d1e22"
                    border.color: "#3a3c42"
                    // the label: the cover, with the song written on it
                    Rectangle {
                        id: label
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: parent.width * 0.05 }
                        height: parent.height * 0.42
                        radius: 3
                        color: "#efe8d4"
                        clip: true
                        Cover {
                            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: 4 }
                            width: height
                            source: deck.track.artUrl || ""
                        }
                        Column {
                            anchors { left: parent.left; leftMargin: parent.height + 4; right: parent.right; rightMargin: 8
                                      top: parent.top; topMargin: 6 }
                            spacing: 0
                            Text {
                                textFormat: Text.PlainText
                                width: parent.width
                                text: deck.track.title || qsTr("No tape")
                                elide: Text.ElideRight
                                color: "#1e2a6e"
                                font.family: deck.dotsFamily
                                font.pixelSize: 22 * deck.u
                            }
                            Text {
                                textFormat: Text.PlainText
                                width: parent.width
                                text: deck.track.artist || ""
                                elide: Text.ElideRight
                                color: "#3b3b3b"
                                font.family: deck.dotsFamily
                                font.pixelSize: 17 * deck.u
                            }
                            Text {
                                textFormat: Text.PlainText
                                width: parent.width
                                text: deck.track.album ? qsTr("SIDE A · %1").arg(deck.track.album) : ""
                                elide: Text.ElideRight
                                color: "#6b6555"
                                font.family: deck.dotsFamily
                                font.pixelSize: 14 * deck.u
                            }
                        }
                    }
                    Rectangle {  // the tape window the reels show through
                        anchors { horizontalCenter: parent.horizontalCenter; top: label.bottom; topMargin: cassette.height * 0.05 }
                        width: parent.width * 0.74; height: parent.height * 0.36; radius: height * 0.18
                        color: "#0c0c0e"
                        border.color: "#4a4c52"
                        Rectangle {  // the tape running between the reels
                            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: parent.width * 0.16 }
                            height: 3; color: "#3a2618"
                        }
                    }
                    // the two reels: tape moves from the left one to the right one as the song plays
                    Repeater {
                        model: 2
                        Item {
                            id: reel
                            required property int index
                            readonly property real tape: reel.index === 0 ? 1 - deck.progress : deck.progress
                            width: cassette.height * 0.32; height: width
                            x: cassette.width * (reel.index === 0 ? 0.3 : 0.7) - width / 2
                            y: cassette.height * 0.69 - height / 2
                            Rectangle {  // the wound tape
                                anchors.centerIn: parent
                                width: parent.width * (0.42 + 0.58 * reel.tape); height: width; radius: width / 2
                                color: "#3a2618"
                                border.color: "#22160e"
                                Behavior on width { NumberAnimation { duration: 600 } }
                            }
                            Item {
                                id: hub
                                anchors.centerIn: parent
                                width: parent.width * 0.4; height: width
                                Rectangle { anchors.fill: parent; radius: width / 2; color: "#e9e4d6"; border.color: "#7e7a6e" }
                                Repeater {
                                    model: 6
                                    Rectangle {
                                        required property int index
                                        width: hub.width * 0.12; height: hub.width * 0.3; radius: 2
                                        color: "#2b2c30"
                                        x: hub.width / 2 - width / 2
                                        y: hub.width / 2 - height / 2
                                        transform: [ Translate { y: -hub.width * 0.28 }, Rotation { origin.x: width / 2; origin.y: height / 2 + hub.width * 0.28; angle: index * 60 } ]
                                    }
                                }
                                RotationAnimator on rotation {
                                    from: 0; to: -360; loops: Animation.Infinite
                                    duration: 1800 + reel.tape * 2400  // a full reel turns slower
                                    running: deck.moving
                                }
                            }
                        }
                    }
                    Text {  // the bottom edge of the shell
                        textFormat: Text.PlainText
                        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 4 }
                        text: qsTr("C-90  ·  TYPE II  ·  HIGH BIAS")
                        color: "#8a8b91"
                        font.family: deck.dotsFamily
                        font.pixelSize: 12 * deck.u
                    }
                }
                // smoked glass in front
                Rectangle {
                    anchors.fill: parent; anchors.margins: 2; radius: parent.radius
                    gradient: Gradient {
                        GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0.10) }
                        GradientStop { position: 0.35; color: Qt.rgba(1, 1, 1, 0.02) }
                        GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.25) }
                    }
                }
            }

            // the display, the analyser and the meters
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 18 * deck.u

                Rectangle {
                    id: lcdPanel
                    objectName: "deckDisplay"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 220 * deck.u
                    radius: 6 * deck.u
                    color: deck.ink.bg
                    border.color: "#000000"
                    border.width: 3
                    clip: true

                    // one display text, with its unlit segments faintly behind it, and a glow
                    component Lit: Item {
                        id: lit
                        property string text: ""
                        property string ghost: ""
                        property string family: deck.seg7Family
                        property real size: 40
                        property int align: Text.AlignLeft
                        implicitWidth: shown.implicitWidth
                        implicitHeight: shown.implicitHeight
                        Text {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            horizontalAlignment: lit.align
                            text: lit.ghost
                            color: deck.ink.ghost
                            font.family: lit.family; font.pixelSize: lit.size
                        }
                        Text {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            anchors.margins: -1
                            horizontalAlignment: lit.align
                            text: lit.text
                            color: deck.ink.glow; opacity: 0.35
                            font.family: lit.family; font.pixelSize: lit.size * 1.02
                        }
                        Text {
                            id: shown
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            horizontalAlignment: lit.align
                            text: lit.text
                            color: deck.ink.on
                            font.family: lit.family; font.pixelSize: lit.size
                        }
                    }
                    component Flag: Text {
                        property bool on: false
                        textFormat: Text.PlainText
                        color: on ? deck.ink.on : deck.ink.ghost
                        font.family: deck.dotsFamily
                        font.pixelSize: 20 * deck.u
                    }

                    ColumnLayout {
                        anchors { fill: parent; margins: 16 * deck.u }
                        spacing: 8 * deck.u

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 18 * deck.u
                            Column {
                                spacing: 2
                                Flag { on: true; text: qsTr("TRACK") }
                                Lit {
                                    text: player.hasTrack ? String(Math.min(99, player.currentIndex + 1)).padStart(2, "0") : "--"
                                    ghost: "88"; size: 40 * deck.u
                                }
                            }
                            Item { Layout.fillWidth: true }
                            Column {
                                spacing: 2
                                Flag { on: true; text: deck.remaining ? qsTr("REMAIN") : qsTr("TIME"); anchors.right: parent.right }
                                Lit {
                                    objectName: "deckTime"
                                    text: (deck.remaining ? "-" : "") + deck.clock(deck.remaining ? player.duration - player.position : player.position)
                                    ghost: (deck.remaining ? "8" : "") + "88:88"; size: 64 * deck.u
                                    align: Text.AlignRight
                                    function flip() { deck.remaining = !deck.remaining; deck.save("deckRemaining", deck.remaining ? "1" : "0") }
                                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: parent.flip() }
                                    Accessible.role: Accessible.Button
                                    Accessible.name: (deck.remaining ? qsTr("Time left %1, click to switch") : qsTr("Time played %1, click to switch")).arg(text)
                                    Accessible.onPressAction: flip()
                                }
                            }
                        }

                        // the scrolling title, on fourteen segments
                        Item {
                            id: marquee
                            Layout.fillWidth: true
                            Layout.preferredHeight: 40 * deck.u
                            clip: true
                            readonly property string message: player.hasTrack
                                ? deck.segText([deck.track.artist, deck.track.title, deck.track.album].filter(function (s) { return s }).join(" - "))
                                : qsTr("INSERT TAPE")
                            readonly property bool scrolls: fits.advanceWidth > width && !Theme.reduceMotion
                            TextMetrics { id: fits; font: line.font; text: marquee.message }
                            Text {  // every segment, unlit
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                text: "~".repeat(64)
                                color: deck.ink.ghost
                                font.family: deck.seg14Family; font.pixelSize: 28 * deck.u
                            }
                            Text {
                                id: line
                                textFormat: Text.PlainText
                                y: 0
                                text: marquee.scrolls ? marquee.message + "   ***   " + marquee.message : marquee.message
                                color: deck.ink.on
                                font.family: deck.seg14Family; font.pixelSize: 28 * deck.u
                                NumberAnimation on x {
                                    id: scroll
                                    running: marquee.scrolls && deck.active
                                    loops: Animation.Infinite
                                    from: 0
                                    to: -loop.advanceWidth  // one message and its gap: then it's back where it began
                                    duration: Math.max(4000, line.implicitWidth * 9)
                                }
                                onTextChanged: x = 0
                            }
                            TextMetrics { id: loop; font: line.font; text: marquee.message + "   ***   " }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 14 * deck.u
                            Flag { on: player.playing; text: qsTr("PLAY") }
                            Flag { on: player.hasTrack && !player.playing; text: qsTr("PAUSE") }
                            Flag { on: player.shuffle; text: qsTr("SHUF") }
                            Flag { on: player.repeat === 1; text: qsTr("RPT") }
                            Flag { on: player.repeat === 2; text: qsTr("RPT1") }
                            Flag { on: player.radio; text: qsTr("RADIO") }
                            Flag { on: player.muted; text: qsTr("MUTE") }
                            Item { Layout.fillWidth: true }
                            Flag {
                                on: true
                                text: {
                                    var bits = []
                                    if (deck.track.codec) bits.push(String(deck.track.codec).toUpperCase())
                                    if (deck.track.sample_rate) bits.push((deck.track.sample_rate / 1000).toFixed(1) + "K")
                                    if (deck.track.bitrate) bits.push(Math.round(deck.track.bitrate / 1000) + "KBPS")  // i18n: keep (a unit on the display)
                                    return bits.join("  ")
                                }
                            }
                        }

                        // the spectrum analyser: LED columns, green to amber to red, with falling peaks
                        Item {
                            id: analyser
                            objectName: "deckAnalyser"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 60 * deck.u
                            readonly property int bars: 24
                            readonly property int rows: 14
                            property var peaks: []
                            readonly property real gap: 3 * deck.u
                            Repeater {
                                model: analyser.bars
                                Item {
                                    id: bar
                                    required property int index
                                    readonly property real level: deck.levels.length > bar.index ? Math.min(1, deck.levels[bar.index]) : 0
                                    readonly property real peak: analyser.peaks.length > bar.index ? analyser.peaks[bar.index] : 0
                                    x: bar.index * (analyser.width / analyser.bars)
                                    width: analyser.width / analyser.bars - analyser.gap
                                    height: analyser.height
                                    Repeater {
                                        model: analyser.rows
                                        Rectangle {
                                            required property int index
                                            readonly property real at: (index + 1) / analyser.rows
                                            width: bar.width
                                            height: (analyser.height - analyser.gap * analyser.rows) / analyser.rows
                                            y: analyser.height - (index + 1) * (height + analyser.gap)
                                            color: at > 0.86 ? "#ff3b2f" : at > 0.64 ? "#ffc23a" : deck.ink.on
                                            opacity: bar.level >= at - 0.5 / analyser.rows ? 1
                                                     : Math.abs(bar.peak - at) < 0.5 / analyser.rows ? 0.85 : 0.08
                                        }
                                    }
                                }
                            }
                            Timer {  // the peaks hold, then fall
                                interval: 60
                                running: deck.active && player.visualizerEnabled
                                repeat: true
                                onTriggered: {
                                    var p = analyser.peaks.slice()
                                    for (var i = 0; i < analyser.bars; i++) {
                                        var l = deck.levels.length > i ? deck.levels[i] : 0
                                        p[i] = Math.max(l, (p[i] || 0) - 0.025)
                                    }
                                    analyser.peaks = p
                                }
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors.centerIn: parent
                                visible: !player.visualizerEnabled
                                text: player.visualizerAvailable ? qsTr("ANALYSER OFF  ·  CLICK TO SWITCH ON") : qsTr("NO ANALYSER ON THIS SYSTEM")
                                color: deck.ink.on
                                font.family: deck.dotsFamily
                                font.pixelSize: 20 * deck.u
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: player.visualizerAvailable
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: player.setVisualizerEnabled(true)
                                }
                                Accessible.role: Accessible.Button
                                Accessible.name: qsTr("Switch on the spectrum analyser")
                                Accessible.onPressAction: player.setVisualizerEnabled(true)
                            }
                        }
                    }
                    // scanlines over the glass
                    Canvas {
                        anchors.fill: parent
                        opacity: 0.22
                        onHeightChanged: requestPaint()
                        onWidthChanged: requestPaint()
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            ctx.fillStyle = "#000000"
                            for (var y = 0; y < height; y += 3) ctx.fillRect(0, y, width, 1)
                        }
                    }
                    Rectangle {  // a reflection on the glass
                        anchors.fill: parent
                        radius: parent.radius
                        gradient: Gradient {
                            GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0.07) }
                            GradientStop { position: 0.3; color: Qt.rgba(1, 1, 1, 0) }
                        }
                    }
                }

                // the tape position: a slider in a groove
                Item {
                    id: seekBar
                    objectName: "deckSeek"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 26 * deck.u
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width; height: 6 * deck.u; radius: height / 2
                        color: "#0b0b0c"; border.color: "#3d4045"
                    }
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width * (drag.pressed ? drag.at : deck.progress); height: 4 * deck.u; radius: height / 2
                        color: deck.ink.on; opacity: 0.8
                    }
                    Rectangle {
                        x: (parent.width - width) * (drag.pressed ? drag.at : deck.progress)
                        anchors.verticalCenter: parent.verticalCenter
                        width: 16 * deck.u; height: 24 * deck.u; radius: 2
                        gradient: Gradient { GradientStop { position: 0; color: "#c9ccd2" } GradientStop { position: 1; color: "#6c7077" } }
                        border.color: "#1a1b1e"
                        Rectangle { anchors.centerIn: parent; width: parent.width * 0.6; height: 1; color: "#2a2b2f" }
                    }
                    MouseArea {
                        id: drag
                        property real at: 0
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onPressed: mouse => at = Math.max(0, Math.min(1, mouse.x / width))
                        onPositionChanged: mouse => at = Math.max(0, Math.min(1, mouse.x / width))
                        onReleased: if (player.duration > 0) player.seek(Math.round(at * player.duration))
                    }
                    Accessible.role: Accessible.Slider
                    Accessible.name: qsTr("Position in the song")
                }
            }
        }

        // the controls: VU meters, the keys and the volume knob
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 128 * deck.u
            spacing: 22 * deck.u

            // two needle meters: the low and the high half of the spectrum
            Repeater {
                model: [{ t: qsTr("LOW"), from: 0, to: 8 }, { t: qsTr("HIGH"), from: 8, to: 24 }]
                Rectangle {
                    id: vu
                    required property var modelData
                    Layout.preferredWidth: 170 * deck.u
                    Layout.fillHeight: true
                    radius: 4 * deck.u
                    color: "#efe3bd"
                    border.color: "#0d0d0e"; border.width: 3
                    clip: true
                    readonly property real level: {
                        var l = deck.levels, s = 0, n = 0
                        for (var i = vu.modelData.from; i < vu.modelData.to && i < l.length; i++) { s += l[i]; n++ }
                        return n ? Math.min(1, (s / n) * 1.6) : 0
                    }
                    Canvas {  // the scale
                        anchors.fill: parent
                        onWidthChanged: requestPaint()
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            var cx = width / 2, cy = height * 1.05, r = height * 0.82
                            for (var i = 0; i <= 10; i++) {
                                var a = (-50 + i * 10) * Math.PI / 180
                                ctx.strokeStyle = i >= 8 ? "#c8261a" : "#2a2a2a"
                                ctx.lineWidth = i % 2 === 0 ? 2 : 1
                                ctx.beginPath()
                                ctx.moveTo(cx + Math.sin(a) * r, cy - Math.cos(a) * r)
                                ctx.lineTo(cx + Math.sin(a) * (r - (i % 2 === 0 ? 12 : 7)), cy - Math.cos(a) * (r - (i % 2 === 0 ? 12 : 7)))
                                ctx.stroke()
                            }
                            ctx.strokeStyle = "#c8261a"; ctx.lineWidth = 4
                            ctx.beginPath(); ctx.arc(cx, cy, r + 2, (-90 + 30) * Math.PI / 180, (-90 + 50) * Math.PI / 180); ctx.stroke()
                        }
                    }
                    Text {
                        textFormat: Text.PlainText
                        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 8 * deck.u }
                        text: "VU  " + vu.modelData.t  // i18n: keep
                        color: "#2a2a2a"
                        font.family: deck.dotsFamily; font.pixelSize: 16 * deck.u
                    }
                    Rectangle {  // the needle
                        width: 2; height: vu.height * 0.9
                        color: "#151515"
                        antialiasing: true
                        x: vu.width / 2 - 1
                        y: vu.height * 1.05 - height
                        transformOrigin: Item.Bottom
                        rotation: -50 + vu.level * 100
                        Behavior on rotation { SmoothedAnimation { velocity: 220 } }
                    }
                    Rectangle {  // glass
                        anchors.fill: parent; radius: parent.radius
                        gradient: Gradient { GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0.25) } GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0) } }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // the transport keys, with lights over the modes
            Column {
                spacing: 10 * deck.u
                Row {
                    spacing: 8 * deck.u
                    anchors.horizontalCenter: parent.horizontalCenter
                    Led { lit: player.shuffle; tint: "#ffb000"; label: qsTr("SHUFFLE"); width: 74 * deck.u }
                    Led { lit: player.repeat > 0; tint: "#ffb000"; label: player.repeat === 2 ? qsTr("REPEAT 1") : qsTr("REPEAT"); width: 74 * deck.u }
                    Led { lit: player.radio; tint: "#ffb000"; label: qsTr("RADIO"); width: 74 * deck.u }
                    Led { lit: player.playing; tint: "#3dff6a"; label: qsTr("PLAY"); width: 74 * deck.u }
                }
                Row {
                    spacing: 8 * deck.u
                    Key { objectName: "deckShuffle"; glyph: "shuffle"; latched: player.shuffle; onActivated: player.toggleShuffle() }
                    Key { objectName: "deckRepeat"; glyph: player.repeat === 2 ? "repeat1" : "repeat"; latched: player.repeat > 0; onActivated: player.cycleRepeat() }
                    Key { objectName: "deckPrev"; glyph: "prev"; onActivated: player.previous() }
                    Key { label: "◀◀"; onActivated: player.seekBy(-10000) }
                    Key { objectName: "deckPlay"; glyph: player.playing ? "pause" : "play"; latched: player.playing; onActivated: player.toggle() }
                    Key { label: "▶▶"; onActivated: player.seekBy(10000) }
                    Key { objectName: "deckNext"; glyph: "next"; onActivated: player.next() }
                    Key { label: "■"; onActivated: player.stop() }
                }
            }

            Item { Layout.fillWidth: true }

            // the volume knob: drag up or down, or scroll
            Column {
                spacing: 6 * deck.u
                Item {
                    id: knobBox
                    objectName: "deckVolume"
                    width: 96 * deck.u; height: width
                    Repeater {  // the lights around it
                        model: 15
                        Rectangle {
                            required property int index
                            readonly property real at: index / 14
                            readonly property real a: (-135 + index * (270 / 14)) * Math.PI / 180
                            width: 6 * deck.u; height: width; radius: width / 2
                            x: knobBox.width / 2 + Math.sin(a) * knobBox.width * 0.47 - width / 2
                            y: knobBox.height / 2 - Math.cos(a) * knobBox.height * 0.47 - height / 2
                            color: player.volume >= at - 0.001 && !player.muted ? deck.ink.on : "#2c2a26"
                        }
                    }
                    Rectangle {
                        id: knob
                        anchors.centerIn: parent
                        width: parent.width * 0.74; height: width; radius: width / 2
                        gradient: Gradient { GradientStop { position: 0; color: "#7a7e85" } GradientStop { position: 1; color: "#26282b" } }
                        border.color: "#0b0b0c"; border.width: 2
                        rotation: -135 + player.volume * 270
                        Rectangle {  // the pointer
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: parent.height * 0.08
                            width: 4 * deck.u; height: parent.height * 0.24; radius: 2
                            color: "#efe9d8"
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.SizeVerCursor
                        property real startY: 0
                        property real startVol: 0
                        onPressed: mouse => { startY = mouse.y; startVol = player.volume }
                        onPositionChanged: mouse => player.setVolume(Math.max(0, Math.min(1, startVol + (startY - mouse.y) / 200)))
                        onWheel: wheel => player.nudgeVolume(wheel.angleDelta.y / 120)
                        onDoubleClicked: player.toggleMute()
                    }
                    Accessible.role: Accessible.Slider
                    Accessible.name: qsTr("Volume %1%").arg(Math.round(player.volume * 100))
                }
                Legend { anchors.horizontalCenter: parent.horizontalCenter; text: player.muted ? qsTr("MUTED") : qsTr("VOLUME") }
            }
        }
    }

    // the CRT look over everything: scanlines, a dark edge and a faint flicker
    Item {
        anchors.fill: parent
        visible: deck.crt
        Canvas {
            anchors.fill: parent
            opacity: 0.18
            onHeightChanged: requestPaint()
            onWidthChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                ctx.fillStyle = "#000000"
                for (var y = 0; y < height; y += 3) ctx.fillRect(0, y, width, 1)
                var g = ctx.createRadialGradient(width / 2, height / 2, Math.min(width, height) * 0.35,
                                                 width / 2, height / 2, Math.max(width, height) * 0.75)
                g.addColorStop(0, "rgba(0,0,0,0)")
                g.addColorStop(1, "rgba(0,0,0,0.9)")
                ctx.fillStyle = g
                ctx.fillRect(0, 0, width, height)
            }
        }
        Rectangle {
            anchors.fill: parent
            color: "white"
            opacity: 0
            SequentialAnimation on opacity {
                running: deck.crt && deck.active && !Theme.reduceMotion
                loops: Animation.Infinite
                NumberAnimation { to: 0.015; duration: 90 }
                NumberAnimation { to: 0; duration: 140 }
                PauseAnimation { duration: 1700 }
            }
        }
    }
}
