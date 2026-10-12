import QtQuick
import QtQuick.Controls
import "."

Item {
    id: page
    objectName: "search"
    property string query: ""
    // One read per result set; rows below use these plain lists instead of the Python models
    readonly property var results: library.searchResults
    readonly property var tracks: results.tracks || []
    readonly property var albums: results.albums || []
    readonly property var artists: results.artists || []

    Flickable {
        id: fl
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: col
            x: 28; y: 20
            width: fl.width - 56
            spacing: 14

            Text {
                textFormat: Text.PlainText
                visible: page.query.length === 0
                text: "Search your library"
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(18)
            }
            Text {
                textFormat: Text.PlainText
                visible: page.query.length > 0 && page.tracks.length === 0
                         && page.albums.length === 0 && page.artists.length === 0
                text: "No results for “" + page.query + "”"
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(18)
            }

            Text {
                textFormat: Text.PlainText
                visible: page.artists.length > 0
                text: "Artists"
                color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold
            }
            ListView {
                visible: page.artists.length > 0
                width: parent.width; height: 210
                orientation: ListView.Horizontal
                spacing: 18; clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: page.artists
                delegate: ArtistCard {
                    required property var modelData
                    name: modelData.name
                    subtitle: modelData.albums + (modelData.albums === 1 ? " album" : " albums")
                    artUrl: modelData.artUrl
                }
            }

            Text {
                textFormat: Text.PlainText
                visible: page.albums.length > 0
                text: "Albums"
                color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold
            }
            ListView {
                visible: page.albums.length > 0
                width: parent.width; height: 240
                orientation: ListView.Horizontal
                spacing: 18; clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: page.albums
                delegate: AlbumCard {
                    required property var modelData
                    required property int index
                    albumKey: modelData.album_key
                    title: modelData.album
                    subtitle: modelData.album_artist || ""
                    artist: modelData.album_artist || ""
                    artUrl: modelData.artUrl
                    selectionSource: page.albums
                    rowIndex: index
                }
            }

            Text {
                textFormat: Text.PlainText
                visible: page.tracks.length > 0
                text: "Songs"
                color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold
            }
            Repeater {
                model: page.tracks
                TrackRow {
                    required property var modelData
                    required property int index
                    selectionSource: page.tracks
                    path: modelData.path
                    audioFormat: modelData.codec || ""
                    audioBitrate: modelData.bitrate || 0
                    rowIndex: index
                    width: col.width
                    title: modelData.title || ""
                    artist: modelData.artist || ""
                    album: modelData.album || ""
                    durText: modelData.durText || ""
                    artUrl: modelData.artUrl || ""
                    current: Rows.currentId === modelData.id
                    onActivated: library.playSearchTracks(index)
                    onEnqueue: player.enqueue(modelData)
                }
            }
        }
    }
}
