import QtQuick
import "."

Item {
    id: card
    property string name
    property string subtitle
    property url artUrl
    property real cardWidth: 150
    width: cardWidth
    height: cardWidth + 56
    Accessible.role: Accessible.Button
    Accessible.name: name + (subtitle.length ? ", " + subtitle : "")
    Accessible.onPressAction: Nav.openArtist(card.name)

    Cover {
        id: art
        width: card.cardWidth; height: card.cardWidth
        radius: width / 2
        source: card.artUrl
        fallback: "♫"
        scale: ma.containsMouse ? 1.03 : 1
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
