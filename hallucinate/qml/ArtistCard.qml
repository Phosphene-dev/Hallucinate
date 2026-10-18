import QtQuick
import "."

Item {
    id: card
    objectName: "artistCard"
    property string name
    property string subtitle
    property url artUrl
    property real cardWidth: 150
    width: cardWidth
    height: cardWidth + 56
    Accessible.role: Accessible.Button
    Accessible.name: name + (subtitle.length ? ", " + subtitle : "")
    Accessible.onPressAction: Nav.openArtist(card.name)
    // From the keyboard, like an album card: Tab to it, Enter or Space opens it, the Menu key its menu
    activeFocusOnTab: true
    // A focused control takes Space and Enter itself; without this the window's Space (play/pause) wins
    Keys.onShortcutOverride: function (event) { event.accepted = event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter }
    Keys.onReturnPressed: Nav.openArtist(card.name)
    Keys.onEnterPressed: Nav.openArtist(card.name)
    Keys.onSpacePressed: Nav.openArtist(card.name)
    Keys.onMenuPressed: Nav.artistMenu(card.name)
    Keys.onPressed: function (event) {
        if (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier)) { Nav.artistMenu(card.name); event.accepted = true }
    }
    Rectangle {
        x: -4; y: -4; width: card.cardWidth + 8; height: card.cardWidth + 8
        radius: width / 2; color: "transparent"; border.width: 2; border.color: Theme.accent
        visible: card.activeFocus
    }

    Cover {
        id: art
        width: card.cardWidth; height: card.cardWidth
        radius: width / 2
        source: card.artUrl
        fallback: "♫"
        scale: Theme.reduceMotion ? 1 : (ma.containsMouse ? 1.03 : 1)
        Behavior on scale { NumberAnimation { duration: 140 } }
    }
    Column {
        anchors { top: art.bottom; topMargin: 10; left: parent.left; right: parent.right }
        spacing: 2
        Text {
            textFormat: Text.PlainText
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: card.name
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(14)
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
        Text {
            textFormat: Text.PlainText
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: card.subtitle
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(12)
            elide: Text.ElideRight
        }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressAndHold: Nav.artistMenu(card.name)
        onClicked: function (mouse) { mouse.button === Qt.RightButton ? Nav.artistMenu(card.name) : Nav.openArtist(card.name) }
    }
}
