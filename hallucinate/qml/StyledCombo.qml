import QtQuick
import QtQuick.Controls
import "."

ComboBox {
    id: combo
    width: 200
    // The choice as the app has it (an index). A ComboBox stops following its currentIndex binding once you pick
    // from it, so a choice changed elsewhere (Ctrl+K, a dialog, the system) would no longer show: with
    // `selection` bound instead, the shown choice always follows the app. -2: not used.
    property int selection: -2
    onSelectionChanged: if (selection > -2) currentIndex = Math.max(0, selection)
    Component.onCompleted: if (selection > -2) currentIndex = Math.max(0, selection)
    onActivated: if (selection > -2) Qt.callLater(function () { if (combo.selection > -2) combo.currentIndex = Math.max(0, combo.selection) })
    contentItem: Text {
        textFormat: Text.PlainText
        leftPadding: 12
        rightPadding: 2  // the arrow's space is already reserved by the control's own padding
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
            radius: Theme.round(9)
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
            radius: Theme.round(14)
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
