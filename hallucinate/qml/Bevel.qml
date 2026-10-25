import QtQuick
import "."

// The raised (or sunken) 3D edge of 90s hardware and desktops: light along the top and left, shadow along the
// bottom and right, two pixels deep. Drawn over its parent's edge, and only in a retro theme.
Item {
    id: bevel
    property bool sunken: false
    anchors.fill: parent
    visible: Theme.retro
    z: 50
    readonly property color hi: Theme.light ? "#ffffff" : Qt.lighter(Theme.border, 1.7)
    readonly property color hi2: Theme.light ? Theme.surfaceHi : Theme.border
    readonly property color lo: Theme.light ? "#3a3936" : "#000000"
    readonly property color lo2: Theme.light ? Theme.border : Qt.darker(Theme.panel, 1.6)
    readonly property color tl: sunken ? lo : hi
    readonly property color tl2: sunken ? lo2 : hi2
    readonly property color br: sunken ? hi : lo
    readonly property color br2: sunken ? hi2 : lo2
    Rectangle { x: 0; y: 0; width: parent.width; height: 1; color: bevel.tl }
    Rectangle { x: 0; y: 0; width: 1; height: parent.height; color: bevel.tl }
    Rectangle { x: 1; y: 1; width: parent.width - 2; height: 1; color: bevel.tl2 }
    Rectangle { x: 1; y: 1; width: 1; height: parent.height - 2; color: bevel.tl2 }
    Rectangle { x: 0; y: parent.height - 1; width: parent.width; height: 1; color: bevel.br }
    Rectangle { x: parent.width - 1; y: 0; width: 1; height: parent.height; color: bevel.br }
    Rectangle { x: 1; y: parent.height - 2; width: parent.width - 2; height: 1; color: bevel.br2 }
    Rectangle { x: parent.width - 2; y: 1; width: 1; height: parent.height - 2; color: bevel.br2 }
}
