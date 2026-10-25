import QtQuick
import "."

// A soft drop shadow drawn as rings outside its parent's rounded shape, so it works without GPU effects and
// never darkens a translucent panel from underneath. Put it first in the panel, sized to fill it.
Item {
    id: shadow
    property real radius: 0
    property real spread: 22
    property real offsetY: 8
    property real strength: 0.32
    readonly property int steps: 10
    anchors.fill: parent
    z: -1
    visible: !Theme.retro  // hard-edged in a retro theme: the bevel does the work
    Repeater {
        model: shadow.steps
        Rectangle {
            required property int index
            readonly property real step: shadow.spread / shadow.steps
            readonly property real out: (index + 1) * step
            x: -out; y: -out + shadow.offsetY
            width: shadow.width + 2 * out; height: shadow.height + 2 * out
            radius: shadow.radius + out
            color: "transparent"
            border.width: step + 0.5
            // strongest next to the panel, fading out
            border.color: Qt.rgba(0, 0, 0, shadow.strength * (Theme.light ? 0.45 : 1)
                                           * Math.pow(1 - index / shadow.steps, 2) / 2.2)
        }
    }
}
