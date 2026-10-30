import QtQuick

// Slim progress bar for library scans: determinate when the expected file count is known.
Item {
    id: bar
    property bool active: library.scanning
    property bool compact: false
    implicitHeight: compact ? 18 : 30
    implicitWidth: 240
    visible: active

    Text {
        textFormat: Text.PlainText
        id: label
        anchors { left: parent.left; right: parent.right; top: parent.top }
        elide: Text.ElideRight
        text: library.status
        color: Theme.accent
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(compact ? 11 : 12)
    }
    Rectangle {
        id: track
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 3
        radius: 2
        color: Theme.border
        clip: true
        Rectangle {
            id: fill
            height: parent.height
            radius: 2
            color: Theme.accent
            readonly property bool determinate: library.scanFraction >= 0
            width: determinate ? track.width * library.scanFraction : track.width * 0.3
            // (a sweep while the total isn't known; #131: one that had stopped partway left the next scan's real
            // progress drawn from where it stopped, so a known total always starts from the left)
            property real sweep: 0
            x: determinate ? 0 : sweep
            Behavior on width { enabled: fill.determinate; NumberAnimation { duration: 150 } }
            SequentialAnimation {
                running: bar.active && !fill.determinate
                loops: Animation.Infinite
                onRunningChanged: if (!running) fill.sweep = 0
                NumberAnimation { target: fill; property: "sweep"; from: 0; to: track.width * 0.7; duration: 900; easing.type: Easing.InOutQuad }
                NumberAnimation { target: fill; property: "sweep"; from: track.width * 0.7; to: 0; duration: 900; easing.type: Easing.InOutQuad }
            }
        }
    }
}
