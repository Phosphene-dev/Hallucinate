import QtQuick
import QtQuick.Controls
import "."

// Every genre in the songs' tags, and the songs of the one picked (#88). A tag can hold several genres
// ("Pop; Indie; Rock", or separate values): a song counts for each of them, and shows under each. The list orders
// A–Z, by songs or by plays, and can be filtered; the songs order like the Songs page. Side by side when there's
// room, one at a time when the window is narrow. The genre's own page (albums, artists, related genres) is a click
// away.
Item {
    id: page
    // Ctrl+A with no row focused (main.qml): the page's list
    function selectAll() { if (page.songs && (page.showingSongs || !page.narrow) && songList.activeFocus) Selection.selectAll(songList.toString(), page.songs, "song"); else Selection.selectAll(genreList.toString(), page.genreModel, "genre") }
    objectName: "genres"

    property string order: shell.uiValue("genresListOrder", "az")  // az, songs, plays
    onOrderChanged: shell.setUiValue("genresListOrder", order)
    property string songSort: shell.uiValue("genresSongSort", "album")
    onSongSortChanged: shell.setUiValue("genresSongSort", songSort)
    property string selected: shell.uiValue("genresSelected", "")
    onSelectedChanged: shell.setUiValue("genresSelected", selected)
    property string filter: ""
    readonly property bool narrow: width < 760
    // narrow: the list, or (once one is picked) its songs
    property bool showingSongs: false

    readonly property var orders: ["az", "songs", "plays"]
    readonly property var sorts: ["album", "title", "artist", "year", "plays", "added"]
    readonly property var genreModel: order === "songs" ? library.genreModel : order === "plays" ? library.genresPlayed
                                                                                                  : library.genresAz
    // the songs of the picked genre, as a model made once per genre and order (see Library.genreSongs)
    property int revision: 0
    Connections { target: library; function onReloaded() { page.revision++ } }
    readonly property var songs: selected.length && revision >= 0 ? library.genreSongs(selected, songSort) : null

    function pick(name) {
        selected = name
        showingSongs = true
        songList.positionViewAtBeginning()
    }
    function plural(n, one, many) { return n + " " + (n === 1 ? one : many) }

    // ---- the genres --------------------------------------------------------------------------------------------
    Item {
        id: listPane
        visible: !page.narrow || !page.showingSongs
        anchors { top: parent.top; bottom: parent.bottom; left: parent.left }
        width: page.narrow ? page.width : Math.min(380, Math.max(280, page.width * 0.32))

        Text {
            id: title
            textFormat: Text.PlainText
            x: 28; y: 20
            text: "Genres"
            color: Theme.text
            font.family: Theme.displayFamily
            font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale
            font.weight: Font.Bold
        }
        Text {
            textFormat: Text.PlainText
            anchors { left: title.right; leftMargin: 10; baseline: title.baseline }
            text: library.genreModel.count > 0 ? library.genreModel.count : ""
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(14)
        }
        Flow {
            id: controls
            anchors { top: title.bottom; topMargin: 12; left: parent.left; leftMargin: 24; right: parent.right; rightMargin: 12 }
            spacing: 6
            Chip { objectName: "genresAz"; text: "A–Z"; selected: page.order === "az"; onClicked: page.order = "az" }
            Chip { objectName: "genresBySongs"; text: "Most songs"; selected: page.order === "songs"; onClicked: page.order = "songs" }
            Chip { objectName: "genresByPlays"; text: "Most played"; selected: page.order === "plays"; onClicked: page.order = "plays" }
        }
        TextField {
            id: filterField
            objectName: "genresFilter"
            anchors { top: controls.bottom; topMargin: 10; left: parent.left; leftMargin: 24; right: parent.right; rightMargin: 12 }
            height: 36
            placeholderText: "Filter genres"
            placeholderTextColor: Theme.textDim
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(13)
            leftPadding: 14
            selectByMouse: true
            background: Rectangle { radius: Theme.round(height / 2); color: Theme.surface; border.color: filterField.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
            onTextChanged: page.filter = text.trim().toLowerCase()
            Keys.onEscapePressed: text = ""
        }
        ListView {
            WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
            id: genreList
            objectName: "genresList"
            anchors { top: filterField.bottom; topMargin: 10; left: parent.left; right: parent.right; bottom: parent.bottom }
            anchors.leftMargin: 14; anchors.rightMargin: 6
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: page.genreModel
            cacheBuffer: 400
            ScrollBar.vertical: ScrollBar {}
            delegate: Item {
                id: entry
                required property string name
                required property int tracks
                required property int albums
                required property int plays
                required property string artUrl
                readonly property bool shown: page.filter.length === 0 || name.toLowerCase().indexOf(page.filter) >= 0
                readonly property bool picked: name === page.selected
                required property int index
                Pick { id: genrePick; target: entry; kind: "genre"; entry: ({ name: entry.name }); source: page.genreModel; index: entry.index }
                width: ListView.view.width - 8
                height: shown ? 58 : 0
                visible: shown
                Rectangle {
                    anchors { fill: parent; topMargin: 2; bottomMargin: 2 }
                    radius: Theme.radius
                    color: entry.picked ? Theme.selectedBg : entryHover.hovered ? Theme.glassHover : "transparent"
                    border.width: genrePick.selected ? 2 : 0
                    border.color: Theme.accent
                }
                Cover {
                    id: entryCover
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    width: 42; height: 42
                    radius: Theme.radiusSmall
                    source: entry.artUrl
                    fallback: entry.name.charAt(0)
                }
                Column {
                    anchors { left: entryCover.right; leftMargin: 12; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                    spacing: 2
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        text: entry.name
                        elide: Text.ElideRight
                        color: entry.picked ? Theme.selectedText : Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(14)
                        font.weight: Font.DemiBold
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        text: page.plural(entry.tracks, "song", "songs") + "  ·  " + page.plural(entry.albums, "album", "albums")
                              + (page.order === "plays" ? "  ·  " + page.plural(entry.plays, "play", "plays") : "")
                        elide: Text.ElideRight
                        color: entry.picked ? Theme.selectedText : Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(12)
                    }
                }
                HoverHandler { id: entryHover; cursorShape: Qt.PointingHandCursor }
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onPressAndHold: if (!PickDrag.painting && !PickDrag.carrying) genreMenu.showGenre(entry.name)
                    onPressed: function (mouse) { genrePick.press(this, mouse) }
                    onPositionChanged: function (mouse) { genrePick.move(this, mouse) }
                    onReleased: genrePick.release(this)
                    onCanceled: genrePick.cancel(this)
                    onClicked: function (mouse) {
                        if (mouse.button === Qt.RightButton) genreMenu.showGenre(entry.name)
                        else if (!genrePick.click(mouse)) page.pick(entry.name)
                    }
                }
                Accessible.role: Accessible.ListItem
                Accessible.name: entry.name + ", " + page.plural(entry.tracks, "song", "songs")
                Accessible.onPressAction: page.pick(entry.name)
            }
        }
        EmptyState {
            anchors.centerIn: genreList
            visible: library.ready && library.genreModel.count === 0
            icon: "genre"
            title: "No genres yet"
            hint: "Songs with a genre in their tags show up here, one group for each genre a song names."
        }
    }
    CollectionMenu { id: genreMenu; objectName: "genresMenu" }

    // ---- the picked genre's songs -------------------------------------------------------------------------------
    Item {
        id: songsPane
        visible: !page.narrow || page.showingSongs
        anchors { top: parent.top; bottom: parent.bottom; right: parent.right; left: page.narrow ? parent.left : listPane.right }
        Rectangle {  // between the two
            visible: !page.narrow
            width: 1; height: parent.height - 40; y: 20
            color: Theme.stroke
        }

        IconButton {
            id: backToList
            objectName: "genresBack"
            visible: page.narrow
            x: 16; y: 22
            icon: "back"
            tip: "All genres"
            onClicked: page.showingSongs = false
        }
        Column {
            id: head
            visible: page.selected.length > 0
            anchors { left: page.narrow ? backToList.right : parent.left; leftMargin: page.narrow ? 8 : 28; right: parent.right; rightMargin: 20 }
            y: 20
            spacing: 10
            Text {
                objectName: "genresSelectedTitle"
                textFormat: Text.PlainText
                width: parent.width
                text: page.selected
                elide: Text.ElideRight
                color: Theme.text
                font.family: Theme.displayFamily
                font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale
                font.weight: Font.Bold
            }
            Flow {
                width: parent.width
                spacing: 8
                PillButton { primary: true; text: "Play"; enabled: songList.count > 0; onClicked: library.playGenreSongsSorted(page.selected, page.songSort, 0) }
                PillButton { text: "Shuffle"; enabled: songList.count > 0; onClicked: library.playGenre(page.selected, true) }
                PillButton { objectName: "genresOpenPage"; text: "Albums & artists"; onClicked: Nav.openGenre(page.selected) }
                StyledCombo {
                    objectName: "genresSongSort"
                    width: 170
                    model: ["Album by album", "Title", "Artist", "Newest year", "Most played", "Recently added"]
                    selection: Math.max(0, page.sorts.indexOf(page.songSort))
                    onActivated: function (i) { page.songSort = page.sorts[i] }
                    Accessible.name: "Order of the songs"
                }
            }
            Text {
                textFormat: Text.PlainText
                text: page.songs ? page.plural(songList.count, "song", "songs") + " tagged " + page.selected : ""
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(12)
            }
        }
        ListView {
            WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
            id: songList
            objectName: "genresSongs"
            anchors { top: head.bottom; topMargin: 12; left: parent.left; right: parent.right; bottom: parent.bottom }
            anchors.leftMargin: page.narrow ? 12 : 20; anchors.rightMargin: 8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: page.songs
            cacheBuffer: 400
            ScrollBar.vertical: ScrollBar {}
            delegate: TrackRow {
                selectionSource: page.songs
                path: model.path
                audioFormat: model.codec
                bitDepth: model.bit_depth || 0
                sampleRate: model.sample_rate || 0
                explicitTag: model.explicit || 0
                audioBitrate: model.bitrate
                rowIndex: index
                width: ListView.view.width - 12
                title: model.title
                artist: model.artist
                // a song with several genres says which others it has
                album: model.genre && model.genre.indexOf(";") >= 0 ? model.album + "  ·  " + shell.genresText(model.genre, false) : model.album
                durText: model.durText
                artUrl: model.artUrl
                current: Rows.currentId === model.id
                context: "genre"
                onActivated: library.playGenreSongsSorted(page.selected, page.songSort, index)
                onEnqueue: player.enqueue(page.songs.get(index))
            }
        }
        EmptyState {
            anchors.centerIn: parent
            visible: page.selected.length === 0 && library.genreModel.count > 0
            icon: "genre"
            title: "Pick a genre"
            hint: "Its songs show here: every song whose tags name it, including songs that name several genres."
        }
    }
}
