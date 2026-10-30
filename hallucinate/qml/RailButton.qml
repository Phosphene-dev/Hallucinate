import QtQuick
import QtQuick.Controls
import "."

// A navigation entry: icon, and a label when the sidebar is expanded. The selected entry glows.
Item {
    id: item
    property string text
    property string icon
    property bool selected: false
    property bool collapsed: false
    signal clicked()
    property bool hasMenu: false  // right-click (or press and hold) asks for a menu
    signal menuRequested()
    property var pick: null        // a Pick: Ctrl/Shift+click select the entry instead (playlists)
    property bool dropping: false  // something carried hovers over it, to be dropped on it
    height: 42
    activeFocusOnTab: true
    // A focused control takes Space and Enter itself; without this the window's Space (play/pause) wins
    Keys.onShortcutOverride: function (event) { event.accepted = event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter }
    Keys.onSpacePressed: item.clicked()
    Keys.onPressed: function (event) { if (item.pick) item.pick.keys(event) }
    Keys.onReturnPressed: item.clicked()
    Keys.onEnterPressed: item.clicked()
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: item.clicked()

    Rectangle {
        anchors.fill: parent
        radius: Theme.round(height / 2)
        color: "transparent"
        border.width: 2
        border.color: Theme.accent
        visible: item.activeFocus
    }
    Rectangle {
        id: pill
        anchors.fill: parent
        radius: Theme.round(height / 2)
        opacity: Theme.retro ? 0 : item.selected ? 1 : (ma.containsMouse ? 0.7 : 0)
        Behavior on opacity { NumberAnimation { duration: 160 } }
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, item.selected ? 0.30 : 0.14) }
            GradientStop { position: 1; color: Qt.rgba(Theme.art1.r, Theme.art1.g, Theme.art1.b, item.selected ? 0.12 : 0.05) }
        }
        border.width: item.selected ? 1 : 0
        border.color: Theme.strokeHi
    }
    Rectangle {  // selected (Ctrl+click), or about to take what's carried over it
        anchors.fill: parent
        radius: Theme.round(height / 2)
        color: item.dropping ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.22) : "transparent"
        border.width: 2
        border.color: Theme.accent
        visible: item.dropping || (item.pick !== null && item.pick.selected)
    }
    Loader {  // a neon theme marks the open page with a glowing bar at its left edge
        active: Theme.neon && item.selected
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 6; bottomMargin: 6 }
        width: 8
        sourceComponent: Item {
            Rectangle { x: 0; width: 3; height: parent.height; color: Theme.accent }
            Rectangle { x: 0; width: 8; height: parent.height; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.neonLoud ? 0.3 : 0.15) }
        }
    }
    Rectangle {  // a retro theme marks the open page in solid accent, and the one under the pointer plainly
        anchors.fill: parent
        visible: Theme.retro && (item.selected || ma.containsMouse)
        color: item.selected ? Theme.selectedBg : Theme.surfaceHi
    }
    Icon {
        id: glyph
        objectName: "railGlyph"
        // where it sits in the collapsed rail is (nearly) where it sits expanded: kept by the left edge as the sidebar
        // narrows, it never jumps to the middle of the still-wide button and slides back (it used to)
        x: item.collapsed ? Math.min(14, (item.width - width) / 2) : 14
        anchors.verticalCenter: parent.verticalCenter
        width: 20; height: 20
        name: item.icon
        filled: item.icon === "heart"
        color: item.selected ? (Theme.retro ? Theme.selectedText : Theme.accentHi) : (ma.containsMouse ? Theme.text : Theme.textDim)
    }
    Text {
        textFormat: Text.PlainText
        anchors { left: glyph.right; leftMargin: 12; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
        text: item.text
        opacity: item.collapsed ? 0 : 1
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        color: item.selected && Theme.retro ? Theme.selectedText : item.selected || ma.containsMouse ? Theme.text : Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(14)
        font.weight: item.selected ? Font.DemiBold : Font.Normal
        elide: Text.ElideRight
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        acceptedButtons: item.hasMenu ? Qt.LeftButton | Qt.RightButton : Qt.LeftButton
        onPressAndHold: if (item.hasMenu) item.menuRequested()
        onClicked: function (mouse) {
            if (mouse.button === Qt.RightButton) item.menuRequested()
            else if (!(item.pick && item.pick.click(mouse))) item.clicked()
        }
    }
    ToolTip.visible: item.collapsed && ma.containsMouse
    ToolTip.text: Theme.plain(item.text)
    ToolTip.delay: 300
}
