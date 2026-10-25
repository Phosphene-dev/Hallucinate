import QtQuick
import QtQuick.Controls
import "."

CheckBox {
    id: box
    // In a column (a settings section), as wide as its text but never wider than the column: long ones wrap.
    readonly property bool _inColumn: parent !== null && String(parent).indexOf("QQuickColumn") === 0
    width: _inColumn && parent.width > 0 ? Math.min(implicitWidth, parent.width) : implicitWidth
    contentItem: Text {
        textFormat: Text.PlainText
        text: box.text
        leftPadding: 30
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(14)
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap  // only when the box is given less room than its text wants
    }
    indicator: Rectangle {
        implicitWidth: 20
        implicitHeight: 20
        radius: Theme.radius / 2
        x: box.leftPadding
        y: parent.height / 2 - height / 2
        // a retro theme's box is a white well with a dark tick, as old desktops drew them
        color: Theme.retro ? Theme.surfaceHi : box.checked ? Theme.accent : Theme.surface
        border.color: Theme.retro ? Theme.border : box.checked ? Theme.accent : Theme.border
        Bevel { sunken: true }
        Text {
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: box.checked ? "✓" : ""
            color: Theme.retro ? Theme.text : Theme.onAccent
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(13)
        }
    }
}
