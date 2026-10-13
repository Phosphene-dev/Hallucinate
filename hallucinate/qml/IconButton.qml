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
    Keys.onSpacePressed: btn.clicked()
    Keys.onReturnPressed: btn.clicked()
    Keys.onEnterPressed: btn.clicked()
    // What a screen reader says when the button has no tooltip; toggles also say whether they're on.
    readonly property var spokenNames: ({
        play: "Play", pause: "Pause", prev: "Previous track", next: "Next track", shuffle: "Shuffle",
        repeat: "Repeat", repeat1: "Repeat one song", radio: "Radio", queue: "Queue", heart: "Like",
        close: "Close", more: "More actions", plus: "Add", minus: "Remove", back: "Back", search: "Search",
        settings: "Settings", sidebar: "Sidebar", fullscreen: "Full screen", expand: "Mini player",
        note: "Lyrics", folder: "Open folder", vinyl: "Vinyl", download: "Download", down: "Show more",
        history: "History", playlist: "Playlist", smartlist: "Smart playlist", duplicates: "Duplicates"
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
