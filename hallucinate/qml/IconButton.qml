import QtQuick
import QtQuick.Controls
import "."

Item {
    id: btn
    property string icon: ""
    property bool active: false
    property int size: 20
    property string tip: ""
    signal clicked()
    implicitWidth: size + 18
    implicitHeight: size + 18
    opacity: enabled ? 1 : 0.4
    activeFocusOnTab: true
    // A focused control takes Space and Enter itself; without this the window's Space (play/pause) wins
    Keys.onShortcutOverride: function (event) { event.accepted = event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter }
    Keys.onSpacePressed: btn.clicked()
    Keys.onReturnPressed: btn.clicked()
    Keys.onEnterPressed: btn.clicked()
    // What a screen reader says when the button has no tooltip; toggles also say whether they're on.
    readonly property var spokenNames: ({
        play: qsTr("Play"), pause: qsTr("Pause"), prev: qsTr("Previous track"), next: qsTr("Next track"), shuffle: qsTr("Shuffle"),
        repeat: qsTr("Repeat"), repeat1: qsTr("Repeat one song"), radio: qsTr("Radio"), queue: qsTr("Queue"), heart: qsTr("Like"),
        close: qsTr("Close"), more: qsTr("More actions"), plus: "Add", minus: qsTr("Remove"), back: qsTr("Back"), search: qsTr("Search"),
        settings: qsTr("Settings"), sidebar: qsTr("Sidebar"), fullscreen: qsTr("Full screen"), expand: qsTr("Mini player"),
        note: qsTr("Lyrics"), folder: qsTr("Open folder"), vinyl: qsTr("Vinyl"), download: qsTr("Download"), down: qsTr("Show more"),
        history: qsTr("History"), playlist: qsTr("Playlist"), smartlist: qsTr("Smart playlist"), duplicates: qsTr("Duplicates")
    })
    readonly property bool toggles: ["shuffle", "repeat", "repeat1", "radio", "queue", "heart", "vinyl"].indexOf(icon) >= 0
    Accessible.role: Accessible.Button
    Accessible.name: tip.length ? tip : (spokenNames[icon] || icon)
    Accessible.checkable: toggles
    Accessible.checked: toggles && active
    Accessible.onPressAction: btn.clicked()
    Rectangle { anchors.fill: parent; anchors.margins: -2; radius: width / 2; color: "transparent"; border.width: 2; border.color: Theme.accent; visible: btn.activeFocus }

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: Theme.surfaceHi
        opacity: ma.containsMouse ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }
    Icon {
        anchors.centerIn: parent
        width: btn.size; height: btn.size
        name: btn.icon
        filled: btn.icon === "heart" && btn.active
        color: btn.active ? Theme.accent : (ma.containsMouse ? Theme.text : Theme.textDim)
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: btn.clicked()
    }
    ToolTip.visible: ma.containsMouse && tip.length > 0
    ToolTip.text: tip
    ToolTip.delay: 600
}
