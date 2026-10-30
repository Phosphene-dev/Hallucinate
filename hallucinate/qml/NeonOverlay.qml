import QtQuick
import "."

// A neon theme's screen over the whole window (loaded by main.qml only in a neon theme): faint scanlines and a
// vignette, a glitch of torn slices for a moment when the song changes, and the brackets of a HUD at the window's
// corners. It takes no clicks or keys, and it's still (drawing nothing new) except during a glitch.
Item {
    id: hud
    objectName: "neonOverlay"
    readonly property bool gpu: GraphicsInfo.api !== GraphicsInfo.Software && GraphicsInfo.api !== GraphicsInfo.Unknown
    property real glitch: 0
    property real clock: 0

    Connections {
        target: player
        function onCurrentChanged() { if (Theme.neonGlitch && player.hasTrack) tear.restart() }
    }
    SequentialAnimation {
        id: tear
        NumberAnimation { target: hud; property: "glitch"; from: 1; to: 0.35; duration: 140 }
        NumberAnimation { target: hud; property: "glitch"; to: 0.8; duration: 60 }
        NumberAnimation { target: hud; property: "glitch"; to: 0; duration: 320; easing.type: Easing.InQuad }
    }
    FrameAnimation { running: tear.running; onTriggered: hud.clock += frameTime }

    ShaderEffect {
        anchors.fill: parent
        visible: hud.gpu && (Theme.neonScanlines || hud.glitch > 0)
        fragmentShader: "shaders/neonscan.frag.qsb"
        property real time: hud.clock
        property real scan: Theme.neonScanlines ? (Theme.neonLoud ? 1 : 0.6) : 0
        property real glitch: hud.glitch
        property real vignette: Theme.neonScanlines ? (Theme.neonLoud ? 0.7 : 0.4) : 0
        property size res: Qt.size(width, height)
        property color ca: Theme.accent
        property color cb: Theme.neonB
    }

    // the HUD's corner brackets
    Item {
        anchors { fill: parent; margins: 6 }
        visible: Theme.neonGreebles
        readonly property real arm: 22
        readonly property color ink: Qt.rgba(Theme.neonB.r, Theme.neonB.g, Theme.neonB.b, Theme.neonLoud ? 0.7 : 0.4)
        Repeater {
            model: 4
            Item {
                required property int index
                readonly property bool atRight: index % 2 === 1
                readonly property bool atBottom: index > 1
                x: atRight ? parent.width - width : 0
                y: atBottom ? parent.height - height : 0
                width: parent.arm; height: parent.arm
                Rectangle { width: parent.width; height: 1; y: parent.atBottom ? parent.height - 1 : 0; color: parent.parent.ink }
                Rectangle { width: 1; height: parent.height; x: parent.atRight ? parent.width - 1 : 0; color: parent.parent.ink }
            }
        }
    }
}
