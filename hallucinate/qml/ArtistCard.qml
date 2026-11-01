import QtQuick
import "."

Item {
    id: card
    objectName: "artistCard"
    property string name
    property string subtitle
    property url artUrl
    property real cardWidth: 150
    property bool composer: false  // a composer's card: opens their page and menu instead
    // The list it's in and its place there: Shift+click and dragging select across it (Ctrl+click works anywhere)
    property var selectionSource: null
    property int rowIndex: -1
    Pick {
        id: pick
        target: card
        kind: card.composer ? "composer" : "artist"
        entry: card.name.length ? { name: card.name } : null
        source: card.selectionSource
        index: card.rowIndex
    }
    readonly property bool selected: pick.selected
    function openIt() { if (composer) Nav.openComposer(name); else Nav.openArtist(name) }
    function menuIt() { if (!composer) Nav.artistMenu(name); else if (composerMenu.item) composerMenu.item.showComposer(name) }
    width: cardWidth
    height: cardWidth + 56
    Accessible.role: Accessible.Button
    Accessible.name: name + (subtitle.length ? ", " + subtitle : "")
    Accessible.onPressAction: card.openIt()
    // From the keyboard, like an album card: Tab to it, Enter or Space opens it, the Menu key its menu
    activeFocusOnTab: true
    // A focused control takes Space and Enter itself; without this the window's Space (play/pause) wins
    Keys.onShortcutOverride: function (event) { event.accepted = event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter }
    Keys.onReturnPressed: card.openIt()
    Keys.onEnterPressed: card.openIt()
    Keys.onSpacePressed: card.openIt()
    Keys.onMenuPressed: card.menuIt()
    Keys.onPressed: function (event) {
        if (pick.keys(event)) return
        if (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier)) { card.menuIt(); event.accepted = true }
    }
    Rectangle {
        x: -4; y: -4; width: card.cardWidth + 8; height: card.cardWidth + 8
        radius: width / 2; color: "transparent"; border.width: 2; border.color: Theme.accent
        visible: card.activeFocus
    }
    Rectangle {  // selected
        x: -5; y: -5; width: card.cardWidth + 10; height: card.cardWidth + 10
        radius: width / 2; color: "transparent"; border.width: 3; border.color: Theme.accent
        visible: card.selected
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
            text: Theme.shown(card.name)
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
        onPressAndHold: if (!PickDrag.pick) card.menuIt()
        onPressed: function (mouse) { pick.press(this, mouse) }
        onPositionChanged: function (mouse) { if (pressed) pick.move(this, mouse) }
        onReleased: pick.release(this)
        onCanceled: pick.cancel(this)
        onClicked: function (mouse) {
            if (mouse.button === Qt.RightButton) card.menuIt()
            else if (!pick.click(mouse)) card.openIt()
        }
    }
    Loader {  // (made only for composers' cards: artists share the window's menu)
        id: composerMenu
        active: card.composer
        sourceComponent: Component { CollectionMenu {} }
    }
}
