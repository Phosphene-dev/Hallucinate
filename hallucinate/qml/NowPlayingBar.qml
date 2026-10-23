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
    readonly property bool tight: width < 740    // half of a small screen: only what's needed most

    WheelHandler {  // with no room for the volume slider, the wheel over the bar is the volume
        enabled: bar.tight
        onWheel: event => player.setVolume(Math.max(0, Math.min(1, player.volume + event.angleDelta.y / 1200)))
    }
    readonly property bool episode: player.hasTrack && player.current.kind === "episode"
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
        objectName: "barNowInfo"
        anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
        width: bar.tight ? 140 : Math.max(160, bar.width * (bar.narrow ? 0.22 : bar.compact ? 0.24 : 0.27))
        spacing: 12
        Cover {
            id: art
            objectName: "barCover"
            width: 60; height: 60; radius: 14
            source: player.hasTrack ? player.current.artUrl : ""
            Accessible.role: player.hasTrack ? Accessible.Button : Accessible.Graphic
            Accessible.name: player.hasTrack ? "Go to what's playing: " + (player.current.album || player.current.title || "") : "Nothing playing"
            Accessible.onPressAction: Nav.goToPlaying()
            MouseArea {
                anchors.fill: parent
                enabled: player.hasTrack
                cursorShape: Qt.PointingHandCursor
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onPressAndHold: Nav.trackMenu(player.current.path, player.current.title, "playing", -1)
                onClicked: function (mouse) {
                    if (mouse.button === Qt.RightButton) Nav.trackMenu(player.current.path, player.current.title, "playing", -1)
                    else Nav.goToPlaying()
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
                MouseArea {  // click: go to what's playing; right-click: its menu
                    anchors.fill: parent
                    enabled: player.hasTrack
                    cursorShape: Qt.PointingHandCursor
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onClicked: function (mouse) {
                        if (mouse.button === Qt.RightButton) Nav.trackMenu(player.current.path, player.current.title, "playing", -1)
                        else Nav.goToPlaying()
                    }
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
                // a song's artist links to their page; a station's or an episode's "artist" isn't one
                readonly property bool linked: !player.error && player.hasTrack && !(player.current.kind || "").length
                readonly property string artistName: player.hasTrack ? (player.current.album_artist || player.current.artist || "") : ""
                Accessible.onPressAction: if (linked && artistName.length) Nav.openArtist(artistName)
                MouseArea {
                    anchors.fill: parent
                    enabled: parent.linked && parent.artistName.length > 0
                    cursorShape: Qt.PointingHandCursor
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onClicked: function (mouse) {
                        if (mouse.button === Qt.RightButton) Nav.artistMenu(parent.artistName)
                        else Nav.openArtist(parent.artistName)
                    }
                }
            }
            Row {
                id: infoRow
                // Only what fits beside the cover: the signal path goes first, then the stars
                readonly property real room: parent.width
                width: Math.min(implicitWidth, room)
                clip: true
                spacing: 6
                visible: player.hasTrack
                AudioInfoBadge {
                    id: infoBadge
                    visible: player.showTrackInfo && player.hasTrack
                    formatName: player.hasTrack ? player.current.codec || "" : ""
                    bitrate: player.hasTrack ? player.current.bitrate || 0 : 0
                }
                StarRating {
                    id: infoStars
                    visible: !bar.narrow && !(player.current.kind || "").length
                             && (infoBadge.visible ? infoBadge.width + 6 : 0) + implicitWidth <= infoRow.room
                    anchors.verticalCenter: parent.verticalCenter; path: player.hasTrack ? player.current.path || "" : ""; size: 12
                }
                SignalPath {
                    visible: player.hasTrack && stages.length > 0
                             && (infoBadge.visible ? infoBadge.width + 6 : 0) + (infoStars.visible ? infoStars.width + 6 : 0)
                                + implicitWidth <= infoRow.room
                }
            }
        }
    }

    // Transport: centred, as wide as the room between the track info and the controls on the right allows. In
    // a narrow window it moves off centre rather than over the track info.
    Column {
        objectName: "barTransport"
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(transportButtons.implicitWidth, 200, Math.min(560, bar.width * 0.42, bar.width - 2 * Math.max(nowInfo.width + 24, rightControls.width + 16) - 24))
        x: Math.max(nowInfo.x + nowInfo.width + 12, Math.min((bar.width - width) / 2, rightControls.x - width - 12))
        spacing: 4
        Row {
            id: transportButtons
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: bar.tight ? 0 : 6
            IconButton { visible: !bar.episode; icon: "shuffle"; active: player.shuffle; onClicked: player.toggleShuffle() }
            IconButton { objectName: "skipBack"; visible: bar.episode; icon: "skipback:" + podcasts.options.skipBack; tip: "Back " + podcasts.options.skipBack + " seconds"; onClicked: player.seekBy(-1000 * podcasts.options.skipBack) }
            IconButton { icon: "prev"; onClicked: player.previous() }
            Rectangle {
                width: 44; height: 44; radius: 22
                Accessible.role: Accessible.Button
                Accessible.name: player.playing ? "Pause" : "Play"
                Accessible.onPressAction: player.toggle()
                scale: Theme.reduceMotion ? 1 : (pp.pressed ? 0.94 : (pp.containsMouse ? 1.06 : 1))
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
            IconButton { objectName: "skipForward"; visible: bar.episode; icon: "skipfwd:" + podcasts.options.skipForward; tip: "Forward " + podcasts.options.skipForward + " seconds"; onClicked: player.seekBy(1000 * podcasts.options.skipForward) }
            IconButton {
                visible: !bar.episode
                icon: player.repeat === 2 ? "repeat1" : "repeat"
                active: player.repeat !== 0
                onClicked: player.cycleRepeat()
            }
            IconButton {
                objectName: "radioButton"
                visible: !bar.episode && !bar.tight  // (also in Ctrl+K)
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
            Text {
                objectName: "barDuration"
                readonly property bool live: player.hasTrack && player.current.kind === "station"
                text: live ? "LIVE" : Theme.fmtTime(player.duration)
                color: live ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); font.weight: live ? Font.Bold : Font.Normal
                Layout.preferredWidth: 38; textFormat: Text.PlainText
            }
        }
    }

    // Volume + queue
    Row {
        id: rightControls
        objectName: "barControls"
        anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
        spacing: 6
        IconButton {
            visible: !bar.tight
            icon: "more"; tip: "Speed and sleep timer"
            active: player.speed !== 1 || player.sleepRemaining >= 0 || player.sleepAfterTrack || player.sleepAfterAlbum
            onClicked: playbackMenu.popup()
            PlaybackMenu { id: playbackMenu }
        }
        IconButton {
            id: chaptersButton
            objectName: "chaptersButton"
            visible: bar.episode && podcasts.chapters.length > 0
            icon: "playlist"; tip: "Chapters"
            onClicked: chaptersMenu.popup(chaptersButton, 0, -chaptersMenu.implicitHeight - 6)
            Menu {
                id: chaptersMenu
                Instantiator {
                    model: podcasts.chapters
                    delegate: MenuItem {
                        required property var modelData
                        required property int index
                        readonly property bool current: player.position >= modelData.start
                                                        && (index + 1 >= podcasts.chapters.length || player.position < podcasts.chapters[index + 1].start)
                        text: Theme.fmtTime(modelData.start) + "   " + modelData.title
                        checkable: true
                        checked: current
                        onTriggered: podcasts.seekChapter(index)
                    }
                    onObjectAdded: (i, o) => chaptersMenu.insertItem(i, o)
                    onObjectRemoved: (i, o) => chaptersMenu.removeItem(o)
                }
            }
        }
        IconButton { objectName: "openNowPlaying"; icon: "fullscreen"; tip: "Now playing (F)"; onClicked: Nav.toggleNowPlaying() }
        IconButton { icon: "expand"; tip: "Mini player (Ctrl+M)"; visible: !bar.compact; onClicked: shell.toggleMini() }
        IconButton { visible: shell.features.lyrics !== false && !bar.tight; icon: "note"; active: bar.lyricsOpen; tip: "Lyrics"; onClicked: bar.toggleLyrics() }
        IconButton { icon: "queue"; active: bar.queueOpen; onClicked: bar.toggleQueue() }
        Icon {
            objectName: "muteButton"
            visible: !bar.tight
            anchors.verticalCenter: parent.verticalCenter
            width: 18; height: 18; name: "volume"
            color: muteArea.containsMouse ? Theme.text : Theme.textDim
            opacity: player.muted ? 0.45 : 1
            Accessible.role: Accessible.Button
            Accessible.name: player.muted ? "Unmute" : "Mute"
            Accessible.checkable: true
            Accessible.checked: player.muted
            Accessible.onPressAction: player.toggleMute()
            Rectangle {  // struck through while muted
                visible: player.muted
                anchors.centerIn: parent
                width: parent.width * 1.2; height: 2; radius: 1
                rotation: -45
                color: Theme.textDim
            }
            MouseArea {
                id: muteArea
                anchors.fill: parent; anchors.margins: -6
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: player.toggleMute()
                ToolTip.visible: containsMouse
                ToolTip.delay: 400
                ToolTip.text: player.muted ? "Unmute" : "Mute"
            }
        }
        StyledSlider {
            visible: !bar.tight  // hidden in a tight bar: the mouse wheel over the bar sets the volume then
            anchors.verticalCenter: parent.verticalCenter
            width: bar.narrow ? 48 : bar.compact ? 64 : 100
            from: 0; to: 1
            value: player.volume
            onMoved: player.setVolume(value)
        }
    }
}
