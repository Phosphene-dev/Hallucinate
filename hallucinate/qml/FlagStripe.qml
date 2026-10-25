import QtQuick
import "."

// A theme's own colours (a pride flag's stripes) as one slim bar, in equal bands.
Item {
    id: stripe
    property var colors: []
    implicitWidth: 48
    implicitHeight: 5
    visible: colors.length > 0
    Rectangle {  // rounded ends without a layer: a rounded bar under square bands, inset by the radius
        anchors.fill: parent
        radius: Theme.round(height / 2)
        color: stripe.colors.length ? stripe.colors[0] : "transparent"
    }
    Rectangle {
        anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
        width: parent.height
        radius: Theme.round(height / 2)
        color: stripe.colors.length ? stripe.colors[stripe.colors.length - 1] : "transparent"
    }
    Row {
        x: stripe.height / 2
        width: stripe.width - stripe.height
        height: stripe.height
        Repeater {
            model: stripe.colors
            Rectangle {
                required property var modelData
                width: (stripe.width - stripe.height) / stripe.colors.length
                height: stripe.height
                color: modelData
            }
        }
    }
}
