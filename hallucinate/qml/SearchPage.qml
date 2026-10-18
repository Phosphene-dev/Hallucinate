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
    // with radio and podcasts on, your stations, shows and episodes are found too
    readonly property var stationHits: shell.features.stations === true ? stations.find(query) : []
    readonly property var podcastHits: shell.features.podcasts === true ? podcasts.find(query) : ({ shows: [], episodes: [] })
    readonly property bool anyExtra: stationHits.length > 0 || podcastHits.shows.length > 0 || podcastHits.episodes.length > 0

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
            x: Theme.contentX(fl.width); y: 20
            width: Theme.contentWidth(fl.width)
            spacing: 14

            Item { width: 1; height: 40; visible: noResults.visible }
            EmptyState {
                id: noResults
                anchors.horizontalCenter: parent.horizontalCenter
                visible: page.query.length === 0 || (page.tracks.length === 0 && page.albums.length === 0
                                                      && page.artists.length === 0 && !page.anyExtra)
                icon: "search"
                title: page.query.length === 0 ? "Search your library" : "No results for “" + page.query + "”"
                hint: page.query.length === 0 ? "Songs, albums and artists. Ctrl+K also finds pages and commands."
                                              : "Check the spelling, or try fewer words."
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

            component HitRow: Rectangle {
                id: hit
                property string title
                property string detail
                property string artUrl
                signal activated()
                width: col.width
                height: 56
                radius: 14
                color: hitMouse.containsMouse ? Theme.glassHover : "transparent"
                Cover {
                    id: hitArt
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    width: 38; height: 38; radius: 10
                    source: hit.artUrl
                    fallback: (hit.title || "?").charAt(0)
                }
                Column {
                    anchors { left: hitArt.right; leftMargin: 12; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                    spacing: 3
                    Text { textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight; text: hit.title; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold }
                    Text { textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight; visible: text.length > 0; text: hit.detail; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12) }
                }
                MouseArea {
                    id: hitMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: hit.activated()
                    Accessible.role: Accessible.Button
                    Accessible.name: hit.title
                    Accessible.onPressAction: hit.activated()
                }
            }
            Text {
                textFormat: Text.PlainText
                visible: page.stationHits.length > 0
                text: "Stations"
                color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold
            }
            Repeater {
                model: page.stationHits
                HitRow {
                    required property var modelData
                    title: modelData.name; detail: modelData.detail; artUrl: modelData.artUrl
                    onActivated: stations.play(modelData.id)
                }
            }
            Text {
                textFormat: Text.PlainText
                visible: page.podcastHits.shows.length > 0
                text: "Podcasts"
                color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold
            }
            Repeater {
                model: page.podcastHits.shows
                HitRow {
                    required property var modelData
                    title: modelData.title; detail: modelData.detail; artUrl: modelData.artUrl
                    onActivated: Nav.openPodcast(modelData.id)
                }
            }
            Text {
                textFormat: Text.PlainText
                visible: page.podcastHits.episodes.length > 0
                text: "Episodes"
                color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold
            }
            EpisodeMenu { id: searchEpisodeMenu }
            Repeater {
                model: page.podcastHits.episodes
                EpisodeRow {
                    required property var modelData
                    width: col.width
                    episode: modelData
                    showPodcast: true
                    onMenu: searchEpisodeMenu.showFor(modelData, true)
                }
            }
        }
    }
}
