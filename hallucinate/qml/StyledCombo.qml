import QtQuick
import QtQuick.Controls
import "."

ComboBox {
    id: combo
    width: 200
    contentItem: Text {
        textFormat: Text.PlainText
        leftPadding: 12
        rightPadding: 28
        text: combo.displayText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(14)
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    // List items drawn as plain text too: device and custom theme names come from outside the app
    delegate: ItemDelegate {
        id: entry
        required property var model
        required property int index
        width: combo.width
        highlighted: combo.highlightedIndex === index
        contentItem: Text {
            textFormat: Text.PlainText
            text: combo.textRole ? entry.model[combo.textRole] : entry.model.modelData
            color: entry.highlighted ? entry.palette.highlightedText : entry.palette.text
            font: combo.font
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
    }
    background: Rectangle {
        implicitHeight: 38
        radius: Theme.radius
        color: Theme.surface
        border.color: combo.activeFocus ? Theme.accent : Theme.border
    }
}
