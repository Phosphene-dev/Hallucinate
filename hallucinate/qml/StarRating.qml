import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import "."

// One to five stars for a song. Hover previews, click rates, clicking the current rating clears it.
Row {
    id: stars
    objectName: "starRating"
    property string path: ""
    property real size: 16
    property color onColor: Theme.accent
    property color offColor: Qt.rgba(Theme.text.r, Theme.text.g, Theme.text.b, 0.28)
    readonly property int value: path.length && userLib.likesRevision >= 0 ? userLib.rating(path) : 0
    property int hovered: 0
    spacing: Math.round(size * 0.12)
    enabled: path.length > 0
    Accessible.role: Accessible.Slider
    Accessible.name: "Rating: " + (value ? value + " of 5 stars" : "not rated")

    Repeater {
        model: 5
        Item {
            id: star
            required property int index
            readonly property bool lit: (stars.hovered || stars.value) > index
            width: stars.size; height: stars.size
            Shape {
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                scale: Theme.reduceMotion ? 1 : (starMouse.containsMouse ? 1.15 : 1)
                Behavior on scale { NumberAnimation { duration: 90 } }
                ShapePath {
                    strokeWidth: star.lit ? 0 : Math.max(1, stars.size / 12)
                    strokeColor: stars.offColor
                    fillColor: star.lit ? (stars.hovered ? Qt.lighter(stars.onColor, 1.15) : stars.onColor) : "transparent"
                    joinStyle: ShapePath.RoundJoin
                    // five-pointed star in a unit box
                    startX: stars.size * 0.5; startY: stars.size * 0.06
                    PathLine { x: stars.size * 0.63; y: stars.size * 0.36 }
                    PathLine { x: stars.size * 0.95; y: stars.size * 0.38 }
                    PathLine { x: stars.size * 0.71; y: stars.size * 0.59 }
                    PathLine { x: stars.size * 0.79; y: stars.size * 0.92 }
                    PathLine { x: stars.size * 0.5; y: stars.size * 0.74 }
                    PathLine { x: stars.size * 0.21; y: stars.size * 0.92 }
                    PathLine { x: stars.size * 0.29; y: stars.size * 0.59 }
                    PathLine { x: stars.size * 0.05; y: stars.size * 0.38 }
                    PathLine { x: stars.size * 0.37; y: stars.size * 0.36 }
                    PathLine { x: stars.size * 0.5; y: stars.size * 0.06 }
                }
            }
            MouseArea {
                id: starMouse
                anchors.fill: parent
                anchors.margins: -2
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onContainsMouseChanged: stars.hovered = containsMouse ? star.index + 1 : (stars.hovered === star.index + 1 ? 0 : stars.hovered)
                onClicked: userLib.setRating(stars.path, star.index + 1)
            }
            ToolTip.visible: starMouse.containsMouse
            ToolTip.text: (star.index + 1) === stars.value ? "Clear rating" : (star.index + 1) + (star.index ? " stars" : " star")
            ToolTip.delay: 600
        }
    }
}
