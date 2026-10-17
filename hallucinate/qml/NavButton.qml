import QtQuick
import "."

Item {
    id: item
    property string text
    property bool selected: false
    signal clicked()
    height: 40
    activeFocusOnTab: true
    // A focused control takes Space and Enter itself; without this the window's Space (play/pause) wins
    Keys.onShortcutOverride: function (event) { event.accepted = event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter }
    Keys.onSpacePressed: item.clicked()
    Keys.onReturnPressed: item.clicked()
    Keys.onEnterPressed: item.clicked()
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: item.clicked()
    Rectangle { anchors.fill: parent; anchors.margins: -2; radius: Theme.radiusSmall; color: "transparent"; border.width: 2; border.color: Theme.accent; visible: item.activeFocus }
    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSmall
        color: item.selected ? Theme.surfaceHi : (ma.containsMouse ? Theme.surface : "transparent")
    }
    Rectangle {
        visible: item.selected
        width: 3; height: 18; radius: 2
        color: Theme.accent
        anchors { left: parent.left; verticalCenter: parent.verticalCenter }
    }
    Text {
        textFormat: Text.PlainText
        anchors { left: parent.left; leftMargin: 18; verticalCenter: parent.verticalCenter }
        text: item.text
        color: item.selected || ma.containsMouse ? Theme.text : Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(14)
        font.weight: item.selected ? Font.DemiBold : Font.Normal
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: item.clicked()
    }
}
