import QtQuick
import "."

// A neon theme's edge for a panel, button or field (drawn by Bevel, only in a neon theme): a hairline in the
// accent, brighter brackets on two opposite corners like a HUD's frame, and on a big panel a few greebles: a row
// of ticks and a small block of lights along the top. Sunken (a field, a slider's track): the hairline alone.
Item {
    id: edge
    property bool sunken: false
    anchors.fill: parent
    readonly property bool big: width > 260 && height > 140
    readonly property real arm: Math.max(4, Math.min(14, Math.min(width, height) * 0.22))
    readonly property color line: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, sunken ? 0.35 : (Theme.neonLoud ? 0.42 : 0.28))
    readonly property color bright: Theme.neonLoud ? Theme.accent : Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.75)

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: edge.line
        radius: Theme.round(2)
    }
    // corner brackets: top left and bottom right
    Item {
        visible: !edge.sunken && edge.width > 24 && edge.height > 16
        anchors.fill: parent
        Rectangle { x: 0; y: 0; width: edge.arm; height: 2; color: edge.bright }
        Rectangle { x: 0; y: 0; width: 2; height: edge.arm; color: edge.bright }
        Rectangle { x: edge.width - edge.arm; y: edge.height - 2; width: edge.arm; height: 2; color: edge.bright }
        Rectangle { x: edge.width - 2; y: edge.height - edge.arm; width: 2; height: edge.arm; color: edge.bright }
        // a cut on the top right corner: the bracket's diagonal
        Rectangle {
            x: edge.width - edge.arm * 0.75; y: edge.arm * 0.32
            width: edge.arm; height: 1
            rotation: 45
            antialiasing: true
            color: Qt.rgba(Theme.neonB.r, Theme.neonB.g, Theme.neonB.b, Theme.neonLoud ? 0.8 : 0.5)
        }
    }
    // greebles on a big panel: ticks and a block of lights along the top
    Loader {
        active: edge.big && !edge.sunken && Theme.neonGreebles
        anchors { top: parent.top; right: parent.right; topMargin: 5; rightMargin: edge.arm + 10 }
        sourceComponent: Row {
            spacing: 3
            Repeater {
                model: 9
                Rectangle {
                    required property int index
                    width: 1; height: index % 4 === 0 ? 6 : 3
                    color: Qt.rgba(Theme.neonB.r, Theme.neonB.g, Theme.neonB.b, 0.55)
                }
            }
            Item { width: 6; height: 1 }
            Repeater {
                model: 3
                Rectangle {
                    required property int index
                    width: 4; height: 4
                    color: index === 0 ? Theme.accent : Qt.rgba(Theme.neonB.r, Theme.neonB.g, Theme.neonB.b, index === 1 ? 0.8 : 0.3)
                }
            }
        }
    }
}
