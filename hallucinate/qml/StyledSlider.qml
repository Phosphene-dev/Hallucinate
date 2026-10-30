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
        Loader {  // a neon theme's: the filled part glows
            active: Theme.neon
            sourceComponent: Rectangle {
                y: -2
                width: s.visualPosition * s.availableWidth
                height: 8
                radius: 4
                color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.neonLoud ? 0.35 : 0.2)
            }
        }
    }
    handle: Rectangle {
        x: s.leftPadding + s.visualPosition * (s.availableWidth - width)
        y: s.topPadding + s.availableHeight / 2 - height / 2
        // a retro theme's thumb: a raised block that's always there
        width: Theme.retro ? 10 : 12; height: Theme.retro ? 18 : 12; radius: Theme.retro ? 0 : width / 2
        color: Theme.retro ? Theme.panel : Theme.neon ? "transparent" : Theme.text
        visible: s.hovered || s.pressed || Theme.retro || Theme.neon
        Bevel {}
        Loader {  // a neon theme's thumb: a small diamond in its second colour
            active: Theme.neon
            anchors.centerIn: parent
            sourceComponent: Rectangle {
                width: 9; height: 9
                rotation: 45
                color: s.hovered || s.pressed ? "#ffffff" : Theme.neonB
                border.width: 1; border.color: Theme.accent
            }
        }
    }
}
