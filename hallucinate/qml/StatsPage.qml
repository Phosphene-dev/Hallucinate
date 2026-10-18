import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Item {
    id: page
    objectName: "stats"

    function periodIndex() {
        switch (userLib.statsPeriod) {
        case "7d": return 1
        case "30d": return 2
        case "365d": return 3
        default: return 0
        }
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.height + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: content
            objectName: "statsColumn"
            x: Theme.contentX(parent.width)
            y: 22
            width: Theme.contentWidth(parent.width)
            spacing: 18

            RowLayout {
                width: parent.width
                Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: "Listening stats"
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.fontSize(25)
                    font.weight: Font.Bold
                }
                StyledCombo {
                    id: period
                    Layout.preferredWidth: 170
                    model: ["All time", "Last 7 days", "Last 30 days", "Last 12 months"]
                    currentIndex: page.periodIndex()
                    onActivated: userLib.setStatsPeriod(["all", "7d", "30d", "365d"][currentIndex])
                }
            }

            Row {
                spacing: 12
                Rectangle {
                    width: 190; height: 82; radius: Theme.radius
                    color: Theme.surface
                    Column {
                        anchors.centerIn: parent
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: userLib.statsSummary.listens || 0; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(21); font.weight: Font.Bold; textFormat: Text.PlainText }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "listens"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); textFormat: Text.PlainText }
                    }
                }
                Rectangle {
                    width: 230; height: 82; radius: Theme.radius
                    color: Theme.surface
                    Column {
                        anchors.centerIn: parent
                        Text {
                            textFormat: Text.PlainText
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: {
                                var seconds = userLib.statsSummary.listeningSeconds || 0
                                var hours = Math.floor(seconds / 3600)
                                var minutes = Math.floor((seconds % 3600) / 60)
                                return hours + "h " + minutes + "m"
                            }
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.fontSize(21)
                            font.weight: Font.Bold
                        }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "estimated listening time"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); textFormat: Text.PlainText }
                    }
                }
            }

            Text {
                textFormat: Text.PlainText
                text: userLib.topTracks.count > 0 ? "Top tracks" : "No listening history for this period yet."
                color: Theme.text
                font.family: Theme.displayFamily
                font.pixelSize: Theme.fontSize(16)
                font.weight: Font.DemiBold
            }
            Column {
                width: parent.width
                Repeater {
                    model: userLib.topTracks
                    TrackRow {
                        selectionSource: userLib.topTracks
                        width: parent.width
                        path: model.path
                        audioFormat: model.codec
                        audioBitrate: model.bitrate
                        rowIndex: index
                        number: index + 1
                        title: model.title
                        artist: model.artist + " · " + model.plays + (model.plays === 1 ? " listen" : " listens")
                        album: model.album
                        durText: model.durText
                        artUrl: model.artUrl
                        current: Rows.currentId === model.id
                        onActivated: userLib.playTopTrack(index)
                        onEnqueue: player.enqueue(userLib.topTracks.get(index))
                    }
                }
            }

            Text {
                textFormat: Text.PlainText
                visible: userLib.topArtists.count > 0
                text: "Top artists"
                color: Theme.text
                font.family: Theme.displayFamily
                font.pixelSize: Theme.fontSize(16)
                font.weight: Font.DemiBold
            }
            Column {
                visible: userLib.topArtists.count > 0
                width: parent.width
                Repeater {
                    model: userLib.topArtists
                    Rectangle {
                        required property int index
                        required property string name
                        required property int plays
                        required property int albums
                        objectName: index === 0 ? "statsTopArtist" : ""
                        width: parent.width
                        height: 42
                        color: artistHover.hovered ? Theme.glassHover : index % 2 ? "transparent" : Theme.surface
                        radius: Theme.radiusSmall
                        HoverHandler { id: artistHover }
                        Accessible.role: Accessible.Button
                        Accessible.name: name + ", " + plays + (plays === 1 ? " listen" : " listens")
                        Accessible.onPressAction: Nav.openArtist(name)
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onPressAndHold: Nav.artistMenu(name)
                            onClicked: function (mouse) { mouse.button === Qt.RightButton ? Nav.artistMenu(name) : Nav.openArtist(name) }
                        }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            Text { Layout.fillWidth: true; text: name; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); elide: Text.ElideRight; textFormat: Text.PlainText }
                            Text { text: albums + (albums === 1 ? " album" : " albums"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); textFormat: Text.PlainText }
                            Text { text: plays + (plays === 1 ? " listen" : " listens"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); textFormat: Text.PlainText }
                        }
                    }
                }
            }

            Text {
                textFormat: Text.PlainText
                visible: userLib.topAlbums.count > 0
                text: "Top albums"
                color: Theme.text
                font.family: Theme.displayFamily
                font.pixelSize: Theme.fontSize(16)
                font.weight: Font.DemiBold
            }
            Column {
                visible: userLib.topAlbums.count > 0
                width: parent.width
                Repeater {
                    model: userLib.topAlbums
                    Rectangle {
                        required property int index
                        required property string album
                        required property string album_artist
                        required property string album_key
                        required property int plays
                        objectName: index === 0 ? "statsTopAlbum" : ""
                        width: parent.width
                        height: 42
                        color: albumHover.hovered ? Theme.glassHover : index % 2 ? "transparent" : Theme.surface
                        radius: Theme.radiusSmall
                        HoverHandler { id: albumHover }
                        Accessible.role: Accessible.Button
                        Accessible.name: album + ", " + album_artist + ", " + plays + (plays === 1 ? " listen" : " listens")
                        Accessible.onPressAction: Nav.openAlbum(album_key)
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onPressAndHold: Nav.albumMenu([album_key], album, album_artist)
                            onClicked: function (mouse) {
                                mouse.button === Qt.RightButton ? Nav.albumMenu([album_key], album, album_artist) : Nav.openAlbum(album_key)
                            }
                        }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            Text { Layout.fillWidth: true; text: album + " · " + album_artist; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); elide: Text.ElideRight; textFormat: Text.PlainText }
                            Text { text: plays + (plays === 1 ? " listen" : " listens"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); textFormat: Text.PlainText }
                        }
                    }
                }
            }

            SectionHeader {
                visible: userLib.recentPlayed.count > 0
                title: "Recently played"
            }
            ListView {
                visible: userLib.recentPlayed.count > 0
                width: parent.width
                height: 248
                orientation: ListView.Horizontal
                spacing: 20
                clip: true
                model: userLib.recentPlayed
                boundsBehavior: Flickable.StopAtBounds
                delegate: AlbumCard {
                    albumKey: model.album_key
                    title: model.album
                    subtitle: model.album_artist
                    artist: model.album_artist
                    artUrl: model.artUrl
                }
            }

            SectionHeader {
                visible: userLib.homeMix.count > 0
                title: "Your mix"
                subtitle: "Songs you play and like most, a few per artist"
            }
            Column {
                visible: userLib.homeMix.count > 0
                width: parent.width
                Repeater {
                    model: userLib.homeMix
                    TrackRow {
                        selectionSource: userLib.homeMix
                        width: parent.width
                        path: model.path
                        audioFormat: model.codec
                        audioBitrate: model.bitrate
                        rowIndex: index
                        number: index + 1
                        title: model.title
                        artist: model.artist
                        album: model.album
                        durText: model.durText
                        artUrl: model.artUrl
                        current: Rows.currentId === model.id
                        onActivated: userLib.playHomeMix(index)
                        onEnqueue: player.enqueue(userLib.homeMix.get(index))
                    }
                }
            }
        }
    }
}
