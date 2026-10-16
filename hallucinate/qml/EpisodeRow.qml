import QtQuick
import QtQuick.Controls
import "."

// One podcast episode: its cover, title, the show (when shown among other shows), date and length or time
// left, how far you've got, and its download state. Click plays it from where you stopped.
Rectangle {
    id: row
    property var episode: ({})
    property bool showPodcast: false
    readonly property bool playing: player.hasTrack && player.current.kind === "episode"
                                    && player.current.episode_id === episode.id
    signal menu()
    width: parent ? parent.width : 400
    height: 64
    radius: 14
    color: rowMouse.containsMouse || playing ? Theme.glassHover : "transparent"
    border.width: playing ? 1 : 0
    border.color: Theme.accent

    Cover {
        id: art
        x: 10
        anchors.verticalCenter: parent.verticalCenter
        width: 44; height: 44; radius: 10
        source: row.episode.artUrl || ""
        fallback: (row.episode.podcast || row.episode.title || "?").charAt(0)
    }
    Column {
        anchors { left: art.right; leftMargin: 12; right: tail.left; rightMargin: 10; verticalCenter: parent.verticalCenter }
        spacing: 3
        Text {
            textFormat: Text.PlainText
            width: parent.width
            elide: Text.ElideRight
            text: row.episode.title || ""
            color: row.playing ? Theme.accent : row.episode.played ? Theme.textDim : Theme.text
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
            font.weight: row.episode.played ? Font.Normal : Font.DemiBold
        }
        Text {
            textFormat: Text.PlainText
            width: parent.width
            elide: Text.ElideRight
            text: (row.showPodcast && row.episode.podcast ? row.episode.podcast + "  ·  " : "") + (row.episode.detail || "")
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
        }
        Rectangle {  // how far you've got
            visible: (row.episode.progress || 0) > 0 && !row.episode.played
            width: Math.min(160, parent.width); height: 3; radius: 1.5
            color: Theme.stroke
            Rectangle { width: parent.width * (row.episode.progress || 0); height: parent.height; radius: 1.5; color: Theme.accent }
        }
    }
    MouseArea {
        id: rowMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: function (mouse) {
            if (mouse.button === Qt.RightButton) row.menu()
            else if (row.playing) player.toggle()
            else podcasts.play(row.episode.id)
        }
        onPressAndHold: row.menu()
        Accessible.role: Accessible.Button
        Accessible.name: (row.playing ? "Playing: " : "Play ") + (row.episode.title || "") + ", " + (row.episode.detail || "")
        Accessible.onPressAction: podcasts.play(row.episode.id)
    }
    Row {
        id: tail
        anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
        spacing: 2
        IconButton {
            visible: !row.episode.local && (row.episode.url || "").length > 0
            icon: row.episode.downloading ? "close" : "download"
            size: 16
            tip: row.episode.downloading ? "Stop downloading" : "Download"
            onClicked: row.episode.downloading ? podcasts.cancelDownload(row.episode.id) : podcasts.download(row.episode.id)
        }
        IconButton { icon: "more"; size: 16; tip: "More"; onClicked: row.menu() }
    }
}
