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
        width: ListView.view ? ListView.view.width : combo.width
        height: 34
        highlighted: combo.highlightedIndex === index
        leftPadding: 12; rightPadding: 12
        contentItem: Text {
            textFormat: Text.PlainText
            text: combo.textRole ? entry.model[combo.textRole] : entry.model.modelData
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(13.5)
            font.weight: combo.currentIndex === entry.index ? Font.DemiBold : Font.Normal
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 9
            color: entry.down ? Qt.darker(Theme.hoverTint, 1.15) : entry.highlighted ? Theme.hoverTint : "transparent"
        }
    }
    // The list: the same glass as menus
    popup: Popup {
        y: combo.height + 4
        width: combo.width
        implicitHeight: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, 360)
        padding: 6
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: combo.popup.visible ? combo.delegateModel : null
            currentIndex: combo.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle {
            radius: 14
            color: Theme.popup
            border.width: 1
            border.color: Theme.stroke
            SoftShadow { radius: parent.radius; spread: 16; offsetY: 5; strength: 0.26 }
        }
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 110 } }
    }
    background: Rectangle {
        implicitHeight: 38
        radius: Theme.radius
        color: Theme.surface
        border.color: combo.activeFocus ? Theme.accent : Theme.border
    }
}
