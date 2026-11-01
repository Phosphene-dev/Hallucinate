import QtQuick
import QtQuick.Controls
import "."

// One genre: its albums, artists and most played songs, and the genres that go with it. Songs count for each
// of their genres, so an album tagged "IDM; Ambient" is under both.
Item {
    id: page
    objectName: "genre"
    property string genreName
    property int revision: 0
    property int seenRevision: -1
    readonly property bool shown: StackView.status === StackView.Active || StackView.status === StackView.Activating
                                  || StackView.view === null
    function catchUp() {
        if (seenRevision !== library.detailRevision) { seenRevision = library.detailRevision; revision++ }
    }
    Component.onCompleted: seenRevision = library.detailRevision
    Connections {
        target: library
        function onDetailChanged() { if (page.shown) page.catchUp() }
    }
    onShownChanged: if (shown) catchUp()
    readonly property var info: page.revision >= 0 && genreName ? library.genrePage(genreName) : ({})
    readonly property var tracksModel: page.revision >= 0 && genreName ? library.genreTracksModel(genreName) : null
    readonly property var albumList: info.albumList || []
    readonly property var artistList: info.artistList || []
    property bool allAlbums: false
    function plural(n, one, many) { return Theme.num(n) + " " + (n === 1 ? one : many) }
    // Play next, add to the queue or a playlist: every song of the genre
    CollectionMenu {
        id: genreMenu; objectName: "genreMenu"
        onGenreRenamed: function (oldName, newName) { page.renamedTo = newName }
    }
    // renamed here: once its songs are retagged (the library reloads), show the genre under its new name
    property string renamedTo: ""
    Connections {
        target: metaEditor
        function onChanged() { if (page.renamedTo) { page.genreName = page.renamedTo; page.renamedTo = ""; page.revision++ } }
        function onFailed() { page.renamedTo = "" }
    }

    // A list of the songs, made as they scroll into view, under a header with everything else (#121: a column
    // that made all of a big genre's rows, and their covers, at once scrolled in jerks)
    ListView {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: fl
        objectName: "genreList"
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        cacheBuffer: 400
        ScrollBar.vertical: ScrollBar {}
        model: page.tracksModel
        footer: Item { width: 1; height: 40 }
        delegate: Item {
            width: fl.width
            height: songRow.height + 4
            TrackRow {
                id: songRow
                x: Theme.contentX(fl.width)  // (a list puts its rows at its left edge)
                width: Theme.contentWidth(fl.width)
                selectionSource: page.tracksModel
                path: model.path
                audioFormat: model.codec
                bitDepth: model.bit_depth || 0
                sampleRate: model.sample_rate || 0
                explicitTag: model.explicit || 0
                audioBitrate: model.bitrate
                rowIndex: index
                title: model.title
                artist: model.artist
                album: model.album
                durText: model.durText
                artUrl: model.artUrl
                current: Rows.currentId === model.id
                onActivated: library.playGenreSongs(page.genreName, index)
                onEnqueue: player.enqueue(page.tracksModel.get(index))
            }
        }
        header: Item {
          width: fl.width
          height: col.height + 24 + 10
          Column {
            id: col
            x: Theme.contentX(fl.width); y: 24
            width: Theme.contentWidth(fl.width)
            spacing: 26

            // Header: a few of its covers, its name and what it holds
            Row {
                spacing: 26
                Item {
                    width: 180; height: 180
                    Repeater {
                        model: Math.min(3, page.albumList.length)
                        Cover {
                            required property int index
                            width: 150; height: 150
                            x: index * 15; y: index * 15
                            z: -index
                            opacity: 1 - index * 0.25
                            radius: Theme.radius
                            source: page.albumList[index].artUrl || ""
                            fallback: page.genreName.charAt(0)
                        }
                    }
                    Cover {
                        visible: page.albumList.length === 0
                        width: 150; height: 150
                        radius: Theme.radius
                        fallback: page.genreName.charAt(0) || "♪"
                    }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    width: col.width - 210
                    spacing: 8
                    Text {
                        textFormat: Text.PlainText
                        text: qsTr("GENRE")
                        color: Theme.accent
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(11)
                        font.weight: Font.Bold
                        font.letterSpacing: 1.5
                    }
                    Text {
                        textFormat: Text.PlainText
                        objectName: "genreTitle"
                        width: parent.width
                        text: page.info.name || page.genreName
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: (Theme.fontSize(36)) * Theme.displayScale
                        font.weight: Font.Bold
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                    Text {
                        textFormat: Text.PlainText
                        objectName: "genreFacts"
                        width: parent.width
                        text: [page.plural(page.info.albums || 0, "album", "albums"),
                               page.plural(page.info.artists || 0, "artist", "artists"),
                               page.plural(page.info.tracks || 0, "song", "songs"),
                               page.info.seconds ? Theme.fmtHours(page.info.seconds) : ""].filter(s => s).join("  ·  ")
                        color: Theme.textDim
                        wrapMode: Text.Wrap
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(14)
                    }
                    Flow {
                        width: parent.width
                        spacing: 10
                        topPadding: 10
                        PillButton {
                            primary: true; text: qsTr("Play all")
                            enabled: (page.info.tracks || 0) > 0
                            onClicked: library.playGenre(page.genreName, false)
                        }
                        PillButton {
                            text: qsTr("Shuffle")
                            enabled: (page.info.tracks || 0) > 0
                            onClicked: { player.setShuffle(true); library.playGenre(page.genreName, true) }
                        }
                        IconButton {
                            objectName: "genrePageMore"
                            height: 38
                            enabled: (page.info.tracks || 0) > 0
                            icon: "more"; size: 18; tip: qsTr("More: play next, add to the queue or a playlist")
                            onClicked: genreMenu.showGenre(page.genreName)
                        }
                    }
                }
            }

            // Genres that go with it
            Column {
                width: col.width
                spacing: 10
                visible: (page.info.related || []).length > 0
                SectionHeader { title: qsTr("Goes with") }
                Flow {
                    objectName: "relatedGenres"
                    width: col.width
                    spacing: 8
                    Repeater {
                        model: page.info.related || []
                        Chip {
                            required property var modelData
                            text: modelData.name
                            onClicked: Nav.openGenre(modelData.name)
                            Accessible.name: "Genre: " + modelData.name
                        }
                    }
                }
            }

            // Artists
            Column {
                width: col.width
                spacing: 10
                visible: page.artistList.length > 0
                SectionHeader { title: qsTr("Artists") }
                Flow {
                    width: col.width
                    spacing: 10
                    Repeater {
                        model: page.artistList.slice(0, 40)
                        Rectangle {
                            required property var modelData
                            implicitWidth: artistRow.implicitWidth + 24
                            height: 44
                            radius: Theme.round(height / 2)
                            color: artistHover.hovered ? Theme.glassHover : Theme.glass
                            border.color: Theme.stroke
                            Row {
                                id: artistRow
                                x: 6; anchors.verticalCenter: parent.verticalCenter
                                spacing: 10
                                Cover {
                                    width: 32; height: 32; radius: Theme.round(16)
                                    source: parent.parent.modelData.artUrl || ""
                                    fallback: (parent.parent.modelData.name || "?").charAt(0)
                                }
                                Text {
                                    textFormat: Text.PlainText
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: parent.parent.modelData.name
                                    color: Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSize(13)
                                }
                            }
                            HoverHandler { id: artistHover; cursorShape: Qt.PointingHandCursor }
                            // right-click (or a long press) for the artist's menu
                            TapHandler { onTapped: Nav.openArtist(parent.modelData.name); onLongPressed: Nav.artistMenu(parent.modelData.name) }
                            TapHandler { acceptedButtons: Qt.RightButton; onTapped: Nav.artistMenu(parent.modelData.name) }
                            Accessible.role: Accessible.Link
                            Accessible.name: modelData.name
                            Accessible.onPressAction: Nav.openArtist(modelData.name)
                        }
                    }
                }
            }

            // Albums
            Column {
                width: col.width
                spacing: 14
                visible: page.albumList.length > 0
                Row {
                    spacing: 14
                    SectionHeader { title: qsTr("Albums") }
                    Text {
                        textFormat: Text.PlainText
                        visible: page.albumList.length > 24
                        anchors.verticalCenter: parent.verticalCenter
                        text: page.allAlbums ? qsTr("Show fewer") : "Show all " + Theme.num(page.albumList.length)
                        color: Theme.accent
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(13)
                        font.weight: Font.DemiBold
                        LinkArea { onClicked: page.allAlbums = !page.allAlbums }
                    }
                }
                Flow {
                    objectName: "genreAlbums"
                    width: col.width
                    spacing: 18
                    Repeater {
                        model: page.allAlbums ? page.albumList : page.albumList.slice(0, 24)
                        AlbumCard {
                            required property var modelData
                            required property int index
                            rowIndex: index
                            selectionSource: page.allAlbums ? page.albumList : page.albumList.slice(0, 24)
                            cardWidth: 160
                            albumKey: modelData.album_key
                            title: modelData.album
                            artist: modelData.album_artist
                            subtitle: (modelData.year > 0 ? modelData.year + "  ·  " : "") + modelData.album_artist
                            artUrl: modelData.artUrl
                        }
                    }
                }
            }

            // Songs, most played first
            Column {
                width: col.width
                spacing: 4
                visible: page.tracksModel !== null && page.tracksModel.count > 0
                SectionHeader {
                    title: qsTr("Songs")
                    subtitle: (page.info.tracks || 0) > (page.tracksModel ? page.tracksModel.count : 0)
                              ? "The " + Theme.num(page.tracksModel.count) + " most played; Play all plays every one" : ""
                }
                Item { width: 1; height: 6 }
            }
          }
        }
    }

    EmptyState {
        anchors.centerIn: parent
        visible: page.info.tracks === 0
        icon: "search"
        title: "No songs in " + page.genreName
        hint: qsTr("None of your songs carry this genre any more.")
    }
}
