import QtQuick
import QtQuick.Effects
import "."

Rectangle {
    id: cover
    property url source
    property string fallback: "♪"
    color: "transparent"
    // Shader masking is unavailable with the software renderer; fall back to square corners.
    readonly property bool useMask: GraphicsInfo.api !== GraphicsInfo.Software
    // Covers are served by the cached "art" image provider in size buckets, decoded off the GUI thread.
    readonly property real wantedPx: Math.max(width, height) * Screen.devicePixelRatio
    readonly property int bucketPx: wantedPx <= 64 ? 64 : wantedPx <= 128 ? 128 : wantedPx <= 256 ? 256 : 512
    readonly property string sourceText: source.toString()
    readonly property string resolved: sourceText.length === 0 ? ""
        : sourceText.indexOf("file:") === 0 ? "image://art/" + bucketPx + "/" + encodeURIComponent(sourceText)
        : sourceText

    Rectangle {
        anchors.fill: parent
        radius: cover.radius
        color: Theme.surface
    }
    Text {
        textFormat: Text.PlainText
        anchors.centerIn: parent
        text: cover.fallback
        color: Theme.surfaceHi
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(Math.max(12, cover.width * 0.4))
        visible: img.status !== Image.Ready
    }
    Image {
        id: img
        anchors.fill: parent
        source: cover.resolved
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        opacity: status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        visible: !cover.useMask
        layer.enabled: cover.useMask
        layer.smooth: true
    }
    Rectangle {
        id: mask
        anchors.fill: parent
        radius: cover.radius
        visible: false
        antialiasing: true
        // A hard-edged, screen-sized mask turns small circles into octagons and stair-steps the corners.
        // Render it at twice the size and let its edge fade over the threshold below.
        layer.enabled: cover.useMask
        layer.smooth: true
        layer.textureSize: Qt.size(Math.ceil(width * 2 * Screen.devicePixelRatio), Math.ceil(height * 2 * Screen.devicePixelRatio))
    }
    MultiEffect {
        anchors.fill: parent
        source: img
        maskEnabled: true
        maskSource: mask
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
        visible: cover.useMask && img.status === Image.Ready
    }
}
