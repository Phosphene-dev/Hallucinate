import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Window {
    id: mini
    width: 380
    height: 112
    minimumWidth: 320
    maximumWidth: 640
    minimumHeight: 112
    maximumHeight: 112
    visible: shell.miniOpen
    title: qsTr("Hallucinate — Mini")
    flags: Qt.Window | Qt.WindowStaysOnTopHint | (shell.customTitleBar ? Qt.FramelessWindowHint : 0)
    color: Theme.panel
    onClosing: shell.showMain()

    Rectangle {
        anchors.fill: parent
        color: Theme.panel
        // with no system frame (the built-in title bar), an edge and a drag anywhere empty to move it by
        border.width: shell.customTitleBar ? 1 : 0
        border.color: Theme.stroke
    }
    TitleDrag { anchors.fill: parent }

    Cover {
        id: art
        x: 12; y: 12; width: 88; height: 88
        radius: shell.ui.spinningArt === "1" ? width / 2 : Theme.radiusSmall
        source: player.hasTrack ? player.current.artUrl : ""
        SpinningCover {}
    }
    ColumnLayout {
        anchors { left: art.right; leftMargin: 12; right: parent.right; rightMargin: 12; top: parent.top; topMargin: 12; bottom: parent.bottom; bottomMargin: 10 }
        spacing: 2
        MarqueeText {  // a long title glides to its end and back while it plays (#112)
            objectName: "miniTitle"
            Layout.fillWidth: true
            text: player.hasTrack ? player.current.title : qsTr("Nothing playing")
            active: player.playing
            color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
        }
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: player.hasTrack ? Theme.shown(player.current.artist) : ""
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            elide: Text.ElideRight
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            Layout.fillWidth: true
            spacing: 4
            readonly property bool episode: player.hasTrack && player.current.kind === "episode"
            readonly property bool live: player.hasTrack && player.current.kind === "station"
            IconButton { visible: parent.episode; icon: "skipback:" + podcasts.options.skipBack; tip: Theme.counted(qsTr("Back %n second(s)", "", podcasts.options.skipBack), podcasts.options.skipBack); onClicked: player.seekBy(-1000 * podcasts.options.skipBack) }
            IconButton { icon: "prev"; tip: qsTr("Previous"); onClicked: player.previous() }
            IconButton { icon: player.playing ? "pause" : "play"; tip: player.playing ? qsTr("Pause") : qsTr("Play"); size: 24; onClicked: player.toggle() }
            IconButton { icon: "next"; tip: qsTr("Next"); onClicked: player.next() }
            IconButton { visible: parent.episode; icon: "skipfwd:" + podcasts.options.skipForward; tip: Theme.counted(qsTr("Forward %n second(s)", "", podcasts.options.skipForward), podcasts.options.skipForward); onClicked: player.seekBy(1000 * podcasts.options.skipForward) }
            Item { Layout.fillWidth: true }
            Text {
                visible: parent.live
                textFormat: Text.PlainText
                text: qsTr("LIVE")
                color: Theme.accent; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); font.weight: Font.Bold
            }
            VolumeButton {  // a click mutes, the wheel turns it up and down (no room here for a slider above it)
                objectName: "miniVolume"
                Layout.alignment: Qt.AlignVCenter
                iconSize: 16
            }
            IconButton { icon: "expand"; tip: qsTr("Back to full window"); onClicked: shell.showMain() }
        }
        StyledSlider {
            Layout.fillWidth: true
            visible: !(player.hasTrack && player.current.kind === "station")  // a live stream has no length to seek in
            from: 0
            to: Math.max(1, player.duration)
            value: player.position
            enabled: player.hasTrack
            onMoved: player.seek(value)
        }
    }
    Shortcut { sequence: "Space"; onActivated: player.toggle() }
    Shortcut { sequence: "Escape"; onActivated: shell.showMain() }
    WindowEdges { grip: 5 }
}
