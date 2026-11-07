import QtQuick
import "."

// A card for something made of several songs (a playlist, a daily mix, a station): up to four covers in a grid
// (one fills it), its name and a line under it, a play button on hover. The same size as an AlbumCard, so they
// line up on Home's shelves. A click opens it (`opened`); the play button plays it (`play`); right-click or the
// menu key asks for its menu (`menu`).
Item {
    id: card
    objectName: "mosaicCard"
    property var arts: []
    property string title
    property string subtitle
    property string fallback: "♪"
    property bool round: false  // (a station: one picture, in a circle)
    property real cardWidth: 170
    signal opened()
    signal play()
    signal menu()
    width: cardWidth
    height: cardWidth + 62
    activeFocusOnTab: true
    Keys.onShortcutOverride: function (event) { event.accepted = event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter }
    Keys.onReturnPressed: card.opened()
    Keys.onSpacePressed: card.opened()
    Keys.onMenuPressed: card.menu()
    Accessible.role: Accessible.Button
    Accessible.name: title + (subtitle.length ? ", " + subtitle : "")
    Accessible.onPressAction: card.opened()
    Rectangle { anchors.fill: parent; anchors.margins: -4; radius: Theme.neon ? Theme.radius : Theme.radius + 4; color: "transparent"; border.width: 2; border.color: Theme.accent; visible: card.activeFocus }

    HoverHandler { id: hh }
    Item {
        id: art
        width: card.cardWidth; height: card.cardWidth
        y: hh.hovered ? -4 : 0
        Behavior on y { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        readonly property real radius: card.round ? width / 2 : (Theme.neon ? Theme.radius : Theme.radius + 4)
        readonly property int count: Math.min(4, (card.arts || []).length)
        Cover {  // one cover, or none (the ♪)
            visible: art.count <= 1
            anchors.fill: parent
            radius: art.radius
            fallback: card.fallback
            source: art.count === 1 ? card.arts[0] : ""
        }
        Grid {  // two to four covers, two by two (two or three repeat to fill it), as small tiles
            visible: art.count > 1
            columns: 2
            spacing: 3
            Repeater {
                model: art.count > 1 ? 4 : 0
                Cover {
                    required property int index
                    width: (art.width - 3) / 2; height: (art.height - 3) / 2
                    radius: Theme.neon ? Theme.radius / 2 : Theme.radius - 2
                    source: card.arts[index % art.count]
                }
            }
        }
    }
    Rectangle {
        id: playBtn
        objectName: "mosaicPlay"
        width: 44; height: 44; radius: Theme.round(22)
        color: Theme.accent
        anchors { right: art.right; bottom: art.bottom; margins: 10 }
        scale: Theme.reduceMotion ? 1 : (hh.hovered ? 1 : 0.85)
        Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutBack } }
        opacity: hh.hovered ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        Icon { anchors.centerIn: parent; width: 20; height: 20; name: "play"; color: Theme.onAccent }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: card.play() }
        Accessible.role: Accessible.Button
        Accessible.name: qsTr("Play %1").arg(card.title)
    }
    MouseArea {  // (under the play button: it takes its own clicks)
        anchors.fill: art
        z: -1
        cursorShape: Qt.PointingHandCursor
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: function (mouse) { if (mouse.button === Qt.RightButton) card.menu(); else card.opened() }
    }
    Column {
        anchors { top: parent.top; topMargin: card.cardWidth + 12; left: parent.left; right: parent.right }
        spacing: 2
        Text {
            textFormat: Text.PlainText
            width: parent.width
            text: card.title
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(14)
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
        Text {
            textFormat: Text.PlainText
            width: parent.width
            text: card.subtitle
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(12)
            elide: Text.ElideRight
        }
    }
}
