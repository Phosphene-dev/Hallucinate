import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import "."

// Library scan progress for the collapsed sidebar, where ScanBar's text has no room (#146): a ring that fills as
// files are read, with the percentage inside, or a turning arc while the total isn't known yet. Hover for the
// same status line the expanded sidebar shows.
Item {
    id: ring
    objectName: "scanRing"
    property bool active: library.scanning
    readonly property bool determinate: library.scanFraction >= 0
    readonly property real size: 30
    implicitHeight: size + 8
    visible: active

    Item {
        id: dial
        width: ring.size; height: ring.size
        anchors.centerIn: parent
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Theme.border; strokeWidth: 3; fillColor: "transparent"
                PathAngleArc { centerX: ring.size / 2; centerY: ring.size / 2; radiusX: ring.size / 2 - 2; radiusY: ring.size / 2 - 2; sweepAngle: 360 }
            }
            ShapePath {
                strokeColor: Theme.accent; strokeWidth: 3; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: ring.size / 2; centerY: ring.size / 2; radiusX: ring.size / 2 - 2; radiusY: ring.size / 2 - 2
                    startAngle: ring.determinate ? -90 : spin.angle
                    sweepAngle: ring.determinate ? 360 * Math.max(0.02, library.scanFraction) : 90
                }
            }
        }
        Text {
            textFormat: Text.PlainText
            anchors.centerIn: parent
            visible: ring.determinate
            text: Math.floor(library.scanFraction * 100)
            color: Theme.accent
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(9)
            font.weight: Font.DemiBold
        }
        QtObject {
            id: spin
            property real angle: -90
        }
        NumberAnimation {
            target: spin; property: "angle"; from: -90; to: 270; duration: 1200
            loops: Animation.Infinite
            running: ring.active && !ring.determinate && !Theme.reduceMotion
        }
    }
    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
    }
    ToolTip.visible: hover.containsMouse
    ToolTip.text: Theme.plain(library.status)
    ToolTip.delay: 300
    Accessible.role: Accessible.ProgressBar
    Accessible.name: library.status
}
