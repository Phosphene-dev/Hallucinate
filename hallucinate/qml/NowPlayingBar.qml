import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// The player floats over the backdrop as a glass pill, softly lit by the current cover.
Item {
    id: bar
    property bool queueOpen: false
    property bool lyricsOpen: false
    readonly property bool compact: width < 1100   // tiling window managers, small screens
    readonly property bool narrow: width < 860
    signal toggleQueue()
    signal toggleLyrics()
    height: Theme.playerHeight

    // Soft shadow from stacked translucent outlines (no shader needed)
    Repeater {
        model: 4
        Rectangle {
            required property int index
            anchors { fill: glassPill; margins: -(index + 1) * 3; topMargin: -(index + 1) * 2; bottomMargin: -(index + 1) * 4 }
            radius: glassPill.radius + (index + 1) * 3
            color: "transparent"
            border.width: 3
            border.color: Qt.rgba(0, 0, 0, Theme.light ? 0.035 - index * 0.007 : 0.11 - index * 0.025)
        }
    }
    Rectangle {
        id: glassPill
        anchors.fill: parent
        radius: 26
        color: Theme.glassStrong
        border.width: 1
        border.color: Theme.stroke
        clip: true
        // Cover-coloured light leaking in from the left
        Rectangle {
            anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
            width: parent.width * 0.45
            radius: parent.radius
            opacity: player.hasTrack ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 600 } }
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.rgba(Theme.art0.r, Theme.art0.g, Theme.art0.b, Theme.light ? 0.16 : 0.22) }
                GradientStop { position: 1; color: Qt.rgba(Theme.art0.r, Theme.art0.g, Theme.art0.b, 0) }
            }
        }
    }

    // Now playing
    Row {
        id: nowInfo
        anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
        width: Math.max(160, bar.width * (bar.compact ? 0.24 : 0.27))
        spacing: 12
        Cover {
            id: art
            objectName: "barCover"
            width: 60; height: 60; radius: 14
            source: player.hasTrack ? player.current.artUrl : ""
            Accessible.role: player.hasTrack ? Accessible.Button : Accessible.Graphic
            Accessible.name: player.hasTrack ? "Open the album " + (player.current.album || "") : "Nothing playing"
            Accessible.onPressAction: if (player.hasTrack && player.current.album_key) Nav.openAlbum(player.current.album_key)
            MouseArea {
                anchors.fill: parent
                enabled: player.hasTrack && player.current.album_key
                cursorShape: Qt.PointingHandCursor
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onPressAndHold: Nav.trackMenu(player.current.path, player.current.title, "playing", -1)
                onClicked: function (mouse) {
                    if (mouse.button === Qt.RightButton) Nav.trackMenu(player.current.path, player.current.title, "playing", -1)
                    else Nav.openAlbum(player.current.album_key)
                }
            }
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - art.width - 12
            spacing: 3
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: player.hasTrack ? player.current.title : "Nothing playing"
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
                elide: Text.ElideRight
                Accessible.role: Accessible.StaticText
                Accessible.name: text
                MouseArea {  // right-click the playing song for its menu
                    anchors.fill: parent
                    enabled: player.hasTrack
                    acceptedButtons: Qt.RightButton
                    onClicked: Nav.trackMenu(player.current.path, player.current.title, "playing", -1)
                }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: player.error.length > 0 ? player.error : (player.hasTrack ? player.current.artist : "")
                color: player.error.length > 0 ? Theme.error : Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(12)
                elide: Text.ElideRight
                Accessible.role: player.error.length > 0 ? Accessible.StaticText : Accessible.Link
                Accessible.name: text
                Accessible.onPressAction: if (!player.error && player.hasTrack) Nav.openArtist(player.current.album_artist)
                MouseArea {
                    anchors.fill: parent
                    enabled: !player.error && player.hasTrack
                    cursorShape: Qt.PointingHandCursor
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onClicked: function (mouse) {
                        if (mouse.button === Qt.RightButton) Nav.artistMenu(player.current.album_artist || player.current.artist)
                        else Nav.openArtist(player.current.album_artist)
                    }
                }
            }
            Row {
                spacing: 6
                visible: player.hasTrack
                AudioInfoBadge {
                    visible: player.showTrackInfo && player.hasTrack
                    formatName: player.hasTrack ? player.current.codec || "" : ""
                    bitrate: player.hasTrack ? player.current.bitrate || 0 : 0
                }
                StarRating { visible: !bar.narrow; anchors.verticalCenter: parent.verticalCenter; path: player.hasTrack ? player.current.path || "" : ""; size: 12 }
                SignalPath { visible: player.hasTrack && stages.length > 0 }
            }
        }
    }

    // Transport: centred, as wide as the room between the track info and the controls on the right allows
    Column {
        anchors.centerIn: parent
        width: Math.max(200, Math.min(560, bar.width * 0.42, bar.width - 2 * Math.max(nowInfo.width + 24, rightControls.width + 16) - 24))
        spacing: 4
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 6
            IconButton { icon: "shuffle"; active: player.shuffle; onClicked: player.toggleShuffle() }
            IconButton { icon: "prev"; onClicked: player.previous() }
            Rectangle {
                width: 44; height: 44; radius: 22
                Accessible.role: Accessible.Button
                Accessible.name: player.playing ? "Pause" : "Play"
                Accessible.onPressAction: player.toggle()
                scale: pp.pressed ? 0.94 : (pp.containsMouse ? 1.06 : 1)
                Behavior on scale { NumberAnimation { duration: 120 } }
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.accentHi }
                    GradientStop { position: 1; color: Qt.tint(Theme.accent, Qt.rgba(Theme.art1.r, Theme.art1.g, Theme.art1.b, 0.45)) }
                }
                Icon {
                    anchors.centerIn: parent
                    width: 18; height: 18
                    name: player.playing ? "pause" : "play"
                    color: Theme.onAccent
                }
                MouseArea { id: pp; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: player.toggle() }
            }
            IconButton { icon: "next"; onClicked: player.next() }
            IconButton {
                icon: player.repeat === 2 ? "repeat1" : "repeat"
                active: player.repeat !== 0
                onClicked: player.cycleRepeat()
            }
            IconButton {
                objectName: "radioButton"
                icon: "radio"
                active: player.radio
                tip: player.radio ? "Radio on: similar songs keep playing after the queue" : "Radio: keep playing similar songs when the queue ends"
                onClicked: player.setRadio(!player.radio)
            }
        }
        RowLayout {
            width: parent.width
            spacing: 10
            Text { text: Theme.fmtTime(player.position); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); Layout.preferredWidth: 38; horizontalAlignment: Text.AlignRight; textFormat: Text.PlainText }
            WaveformSeek {
                Layout.fillWidth: true
                Layout.preferredHeight: 26
            }
            Text { text: Theme.fmtTime(player.duration); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); Layout.preferredWidth: 38; textFormat: Text.PlainText }
        }
    }

    // Volume + queue
    Row {
        id: rightControls
        anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
        spacing: 6
        IconButton {
            icon: "more"; tip: "Speed and sleep timer"
            active: player.speed !== 1 || player.sleepRemaining >= 0 || player.sleepAfterTrack
            onClicked: playbackMenu.popup()
            PlaybackMenu { id: playbackMenu }
        }
        IconButton { objectName: "openNowPlaying"; icon: "fullscreen"; tip: "Now playing (F)"; onClicked: Nav.toggleNowPlaying() }
        IconButton { icon: "expand"; tip: "Mini player (Ctrl+M)"; visible: !bar.compact; onClicked: shell.toggleMini() }
        IconButton { visible: shell.features.lyrics !== false; icon: "note"; active: bar.lyricsOpen; tip: "Lyrics"; onClicked: bar.toggleLyrics() }
        IconButton { icon: "queue"; active: bar.queueOpen; onClicked: bar.toggleQueue() }
        Icon { anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18; name: "volume"; color: Theme.textDim }
        StyledSlider {
            anchors.verticalCenter: parent.verticalCenter
            width: bar.compact ? 64 : 100
            from: 0; to: 1
            value: player.volume
            onMoved: player.setVolume(value)
        }
    }
}
