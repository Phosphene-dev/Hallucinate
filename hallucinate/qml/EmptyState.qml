import QtQuick
import QtQuick.Controls
import "."

// What a page shows when it has nothing to list: an icon in a soft glow, a short title, a hint at what to do,
// and optionally a button that does it. `busy` swaps the icon for a spinner while something is being worked out.
Column {
    id: es
    property string icon: "note"
    property string title: ""
    property string hint: ""
    property string actionText: ""
    property bool busy: false
    signal action()

    width: Math.min(440, parent ? parent.width - 48 : 440)
    spacing: 10

    Item {
        anchors.horizontalCenter: parent.horizontalCenter
        width: 76; height: 76
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.light ? 0.08 : 0.10)
        }
        Rectangle {
            anchors.centerIn: parent
            width: 54; height: 54; radius: 27
            color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.light ? 0.14 : 0.18)
            border.width: 1
            border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.30)
        }
        Icon {
            anchors.centerIn: parent
            visible: !es.busy
            width: 24; height: 24
            name: es.icon
            color: Theme.accent
        }
        BusyIndicator {
            anchors.centerIn: parent
            visible: es.busy
            running: es.busy
            width: 30; height: 30
        }
    }
    Item { width: 1; height: 2 }
    Text {
        textFormat: Text.PlainText
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        visible: text.length > 0
        text: es.title
        color: Theme.text
        font.family: Theme.displayFamily
        font.weight: Font.DemiBold
        font.pixelSize: Theme.fontSize(16)
    }
    Text {
        textFormat: Text.PlainText
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        visible: text.length > 0
        text: es.hint
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(13)
        lineHeight: 1.15
    }
    Item { width: 1; height: 4; visible: es.actionText.length > 0 }
    PillButton {
        anchors.horizontalCenter: parent.horizontalCenter
        visible: es.actionText.length > 0
        text: es.actionText
        primary: true
        onClicked: es.action()
    }
}
