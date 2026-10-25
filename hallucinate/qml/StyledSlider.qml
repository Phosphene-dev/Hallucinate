import QtQuick
import QtQuick.Controls
import "."

Slider {
    id: s
    implicitHeight: Theme.retro ? 20 : 18
    padding: 0
    Accessible.name: "Slider"
    background: Rectangle {
        x: s.leftPadding
        y: s.topPadding + s.availableHeight / 2 - height / 2
        width: s.availableWidth
        height: Theme.retro ? 6 : 4
        radius: Theme.retro ? 0 : 2
        color: Theme.retro ? Theme.surfaceHi : Theme.surfaceHi
        Rectangle {
            width: s.visualPosition * parent.width
            height: parent.height
            radius: Theme.retro ? 0 : 2
            color: s.hovered || s.pressed || Theme.retro ? Theme.accent : Theme.text
        }
        Bevel { sunken: true }  // a retro theme's groove
    }
    handle: Rectangle {
        x: s.leftPadding + s.visualPosition * (s.availableWidth - width)
        y: s.topPadding + s.availableHeight / 2 - height / 2
        // a retro theme's thumb: a raised block that's always there
        width: Theme.retro ? 10 : 12; height: Theme.retro ? 18 : 12; radius: Theme.retro ? 0 : width / 2
        color: Theme.retro ? Theme.panel : Theme.text
        visible: s.hovered || s.pressed || Theme.retro
        Bevel {}
    }
}
