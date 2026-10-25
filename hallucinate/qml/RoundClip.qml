import QtQuick
import QtQuick.Effects
import "."

// Clips what's inside it to a rounded rectangle. `clip: true` only cuts along the bounding box, so anything
// that reaches the edge (a visualizer, a page's glow of cover colours) ends in sharp corners that don't match
// the rounded panels around it. With the software renderer (no shaders) it falls back to a square clip.
Item {
    id: root
    property real radius: Theme.round(22)
    default property alias content: inner.data
    readonly property bool useMask: GraphicsInfo.api !== GraphicsInfo.Software && radius > 0
    clip: !useMask

    Item {
        id: inner
        anchors.fill: parent
        layer.enabled: root.useMask
        layer.smooth: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: mask
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1.0
        }
    }
    Rectangle {
        id: mask
        anchors.fill: parent
        radius: root.radius
        visible: false
        antialiasing: true
        layer.enabled: root.useMask
        layer.smooth: true
        // twice the size, its edge fading over the threshold: smooth corners, not stair steps (as in Cover)
        layer.textureSize: Qt.size(Math.ceil(width * 2 * Screen.devicePixelRatio), Math.ceil(height * 2 * Screen.devicePixelRatio))
    }
}
