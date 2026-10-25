import QtQuick
import QtQuick.Controls.impl
import QtQuick.Templates as T
import ".."

// A menu row: an optional icon (icon.name, one of Icon.qml's), the text, and a submenu chevron. The row under the
// pointer gets a soft accent tint while the text keeps the theme's text colour, so it stays readable in every
// theme. Setting icon.color (e.g. Theme.error for "Move to trash…") colours the icon and the text.
T.MenuItem {
    id: control

    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             implicitContentHeight + topPadding + bottomPadding)

    readonly property bool tinted: control.icon.color.a > 0
    readonly property color ink: !control.enabled ? Qt.rgba(Theme.textDim.r, Theme.textDim.g, Theme.textDim.b, 0.6)
                                 : tinted ? control.icon.color : Theme.text

    leftPadding: 12
    rightPadding: 12
    topPadding: 0
    bottomPadding: 0
    spacing: 10
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSize(13.5)

    contentItem: Item {
        readonly property real trail: control.subMenu || control.checkable ? 14 + control.spacing : 0
        implicitWidth: (icn.visible ? icn.width + control.spacing : 0) + label.implicitWidth + trail
        implicitHeight: 34
        Icon {
            id: icn
            visible: control.icon.name !== ""
            name: control.icon.name
            color: control.tinted ? control.icon.color : Theme.textDim
            width: 16; height: 16
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            id: label
            textFormat: Text.PlainText
            x: icn.visible ? icn.width + control.spacing : 0
            width: parent.width - x - parent.trail
            anchors.verticalCenter: parent.verticalCenter
            text: control.text
            font: control.font
            color: control.ink
            elide: Text.ElideRight
        }
        Text {  // the chosen option of a checkable item (playback speed, sorting)
            textFormat: Text.PlainText
            visible: control.checkable && control.checked
            text: "\u2713"
            color: Theme.accent
            font.pixelSize: Theme.fontSize(14)
            font.bold: true
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
        }
        Icon {
            visible: control.subMenu
            name: "down"
            rotation: -90
            color: Theme.textDim
            width: 12; height: 12
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
        }
    }

    indicator: Item {}
    arrow: Item {}

    background: Rectangle {
        implicitWidth: 220
        implicitHeight: 34
        radius: Theme.round(9)
        color: control.down ? Qt.darker(Theme.hoverTint, 1.15)
             : control.highlighted ? Theme.hoverTint : "transparent"
        Behavior on color { ColorAnimation { duration: 90 } }
    }
}
