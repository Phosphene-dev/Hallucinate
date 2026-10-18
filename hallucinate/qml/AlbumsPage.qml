import QtQuick
import QtQuick.Controls
import "."

// Albums four ways: A–Z, a wall ordered by cover colour, a timeline by decade and year, and by genre.
Item {
    id: page
    objectName: "albums"
    readonly property real minCell: 190
    readonly property int cols: Math.max(2, Math.floor((width - 40) / minCell))
    property string view: shell.uiValue("albumsView", "grid")
    readonly property var views: [{ id: "grid", t: "A–Z" }, { id: "colour", t: "Colour" }, { id: "timeline", t: "Timeline" },
                                 { id: "genres", t: "Genres" }]
    onViewChanged: {
        shell.setUiValue("albumsView", view)
        if (view === "colour") library.loadAlbumWall()
    }
    Component.onCompleted: if (view === "colour") library.loadAlbumWall()
    // the wall is only worked out while it's on screen: refresh it when the library changes under it
    Connections {
        target: library
        function onChanged() { if (page.view === "colour") library.loadAlbumWall() }
    }

    Row {
        id: header
        x: 28; y: 20
        width: parent.width - 56
        spacing: 18
        Text {
            textFormat: Text.PlainText
            id: title
            anchors.verticalCenter: parent.verticalCenter
            text: "Albums"
            color: Theme.text
            font.family: Theme.displayFamily
            font.pixelSize: Theme.fontSize(25)
            font.weight: Font.Bold
        }
        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Repeater {
                model: page.views
                Chip {
                    required property var modelData
                    objectName: "albumsView_" + modelData.id
                    text: modelData.t
                    selected: page.view === modelData.id
                    onClicked: page.view = modelData.id
                }
            }
        }
    }

    Loader {
        anchors { top: header.bottom; topMargin: 14; left: parent.left; right: parent.right; bottom: parent.bottom }
        sourceComponent: page.view === "colour" ? wallView : page.view === "timeline" ? timelineView
                       : page.view === "genres" ? genresView : gridView
    }

    Component {
        id: gridView
        GridView {
            id: grid
            leftMargin: 20; rightMargin: 8
            cellWidth: Math.floor((width - 28) / page.cols)
            cellHeight: cellWidth + 76
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: library.albums
            cacheBuffer: 600
            ScrollBar.vertical: ScrollBar {}
            delegate: Item {
                width: grid.cellWidth; height: grid.cellHeight
                AlbumCard {
                    x: 8; y: 8
                    cardWidth: grid.cellWidth - 24
                    albumKey: model.album_key
                    title: model.album
                    subtitle: (model.year > 0 ? model.year + " • " : "") + model.album_artist
                    artist: model.album_artist
                    artUrl: model.artUrl
                    selectionSource: library.albums
                    rowIndex: index
                }
            }
        }
    }

    // Covers edge to edge, ordered round the colour wheel; hover for the title
    Component {
        id: wallView
        Item {
            GridView {
                id: wall
                objectName: "colourWall"
                anchors { fill: parent; leftMargin: 24; rightMargin: 12 }
                readonly property int wallCols: Math.max(4, Math.floor(width / 112))
                cellWidth: Math.floor((width - 12) / wallCols)
                cellHeight: cellWidth
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: library.albumWall
                cacheBuffer: 800
                ScrollBar.vertical: ScrollBar {}
                delegate: Item {
                    id: tile
                    required property string album_key
                    required property string album
                    required property string album_artist
                    required property string artUrl
                    required property string color
                    required property int index
                    width: wall.cellWidth; height: wall.cellHeight
                    z: tileMouse.containsMouse ? 2 : 0
                    Rectangle {
                        anchors { fill: parent; margins: 2 }
                        radius: 6
                        color: tile.color.length ? tile.color : Theme.surface
                    }
                    Cover {
                        anchors { fill: parent; margins: 2 }
                        radius: 6
                        source: tile.artUrl
                        fallback: tile.album.charAt(0)
                        scale: Theme.reduceMotion ? 1 : (tileMouse.containsMouse ? 1.12 : 1)
                        Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                    }
                    Rectangle {  // selected
                        anchors { fill: parent; margins: 1 }
                        radius: 7
                        color: "transparent"
                        border.width: 3
                        border.color: Theme.accent
                        visible: AlbumSelection.count > 0 && AlbumSelection.has(tile.album_key)
                    }
                    MouseArea {
                        id: tileMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        Accessible.role: Accessible.Button
                        Accessible.name: tile.album + (tile.album_artist ? ", " + tile.album_artist : "")
                        Accessible.onPressAction: Nav.openAlbum(tile.album_key)
                        onClicked: function (mouse) {
                            if (mouse.button === Qt.RightButton) Nav.albumMenu([tile.album_key], tile.album, tile.album_artist)
                            else if (mouse.modifiers & Qt.ControlModifier) AlbumSelection.toggle(library.albumWall, tile.index, tile.album_key)
                            else if (mouse.modifiers & Qt.ShiftModifier) AlbumSelection.extend(library.albumWall, tile.index, tile.album_key)
                            else { AlbumSelection.clear(); Nav.openAlbum(tile.album_key) }
                        }
                        onPressAndHold: Nav.albumMenu([tile.album_key], tile.album, tile.album_artist)
                    }
                    ToolTip.visible: tileMouse.containsMouse
                    ToolTip.text: Theme.plain(tile.album + " — " + tile.album_artist)
                    ToolTip.delay: 300
                }
            }
            BusyIndicator {
                anchors.centerIn: parent
                running: library.wallLoading && wall.count === 0
                visible: running
            }
            Text {
                textFormat: Text.PlainText
                anchors.centerIn: parent
                visible: library.wallLoading && wall.count === 0
                anchors.verticalCenterOffset: 44
                text: "Reading the colours of your covers…"
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
            }
        }
    }

    // Decades as headings, then each year as a row of covers
    Component {
        id: timelineView
        ListView {
            id: timeline
            objectName: "timeline"
            leftMargin: 28; rightMargin: 12
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: library.timeline
            cacheBuffer: 1200
            ScrollBar.vertical: ScrollBar {}
            readonly property real coverSize: Math.max(96, Math.min(150, (width - 160) / 7))
            delegate: Loader {
                required property var model
                width: timeline.width - 40
                sourceComponent: model.kind === "decade" ? decadeRow : yearRow
                property var row: model
            }
            Component {
                id: decadeRow
                Item {
                    readonly property var row: parent ? parent.row : ({})
                    height: 70
                    Text {
                        textFormat: Text.PlainText
                        id: decadeLabel
                        anchors { left: parent.left; bottom: parent.bottom; bottomMargin: 10 }
                        text: parent.row.label
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.fontSize(30)
                        font.weight: Font.Bold
                    }
                    Text {
                        textFormat: Text.PlainText
                        anchors { left: decadeLabel.right; leftMargin: 14; baseline: decadeLabel.baseline }
                        text: parent.row.count + (parent.row.count === 1 ? " album" : " albums")
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(13)
                    }
                    Rectangle {
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                        height: 1
                        color: Theme.stroke
                    }
                }
            }
            Component {
                id: yearRow
                Item {
                    id: yearItem
                    readonly property var row: parent ? parent.row : ({})
                    readonly property var albums: row && row.albums ? row.albums : []
                    // A busy year (hundreds of albums in a big library) shows two lines until asked for the rest,
                    // so scrolling the timeline never has to draw them all.
                    readonly property int perLine: Math.max(1, Math.floor((yearFlow.width + 14) / (timeline.coverSize + 14)))
                    property bool expanded: false
                    readonly property int shown: expanded ? albums.length : Math.min(albums.length, perLine * 2)
                    height: Math.max(yearFlow.height, 40) + (moreButton.visible ? moreButton.height + 10 : 0) + 24
                    // the year on a thread down the left, a dot for each year
                    Rectangle { x: 34; width: 2; height: parent.height; color: Theme.stroke }
                    Rectangle {
                        x: 29; y: 22; width: 12; height: 12; radius: 6
                        color: Theme.accent
                        border.width: 3; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.3)
                    }
                    Text {
                        textFormat: Text.PlainText
                        x: 52; y: 16
                        width: 64
                        text: yearItem.row.year > 0 ? yearItem.row.year : "—"
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.fontSize(16)
                        font.weight: Font.DemiBold
                    }
                    Flow {
                        id: yearFlow
                        x: 124; y: 14
                        width: parent.width - x
                        spacing: 14
                        Repeater {
                            model: yearItem.shown  // a count, so "Show all" adds covers instead of rebuilding them
                            Item {
                                id: entry
                                required property int index
                                readonly property var modelData: yearItem.albums[index] || ({})
                                width: timeline.coverSize
                                height: timeline.coverSize + 40
                                Cover {
                                    id: tlCover
                                    width: timeline.coverSize; height: width
                                    radius: 12
                                    source: entry.modelData.artUrl || ""
                                    fallback: (entry.modelData.album || "?").charAt(0)
                                    y: tlMouse.containsMouse ? -3 : 0
                                    Behavior on y { NumberAnimation { duration: 140 } }
                                }
                                Text {
                                    textFormat: Text.PlainText
                                    anchors { top: tlCover.bottom; topMargin: 6 }
                                    width: parent.width
                                    text: entry.modelData.album
                                    color: Theme.text
                                    elide: Text.ElideRight
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSize(12)
                                    font.weight: Font.Medium
                                }
                                Text {
                                    textFormat: Text.PlainText
                                    anchors { top: tlCover.bottom; topMargin: 22 }
                                    width: parent.width
                                    text: entry.modelData.album_artist
                                    color: Theme.textDim
                                    elide: Text.ElideRight
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSize(11)
                                }
                                MouseArea {
                                    id: tlMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                    Accessible.role: Accessible.Button
                                    Accessible.name: entry.modelData.album + (entry.modelData.album_artist ? ", " + entry.modelData.album_artist : "")
                                    Accessible.onPressAction: Nav.openAlbum(entry.modelData.album_key)
                                    onClicked: function (mouse) {
                                        if (mouse.button === Qt.RightButton)
                                            Nav.albumMenu([entry.modelData.album_key], entry.modelData.album, entry.modelData.album_artist || "")
                                        else
                                            Nav.openAlbum(entry.modelData.album_key)
                                    }
                                    onPressAndHold: Nav.albumMenu([entry.modelData.album_key], entry.modelData.album, entry.modelData.album_artist || "")
                                }
                            }
                        }
                    }
                    PillButton {
                        id: moreButton
                        objectName: "timelineMore"
                        x: 124
                        anchors { top: yearFlow.bottom; topMargin: 10 }
                        height: 30
                        visible: yearItem.shown < yearItem.albums.length
                        text: "Show all " + yearItem.albums.length
                        onClicked: yearItem.expanded = true
                    }
                }
            }
        }
    }
    EmptyState {
        objectName: "noMusic"
        anchors.centerIn: parent
        visible: library.ready && library.trackCount === 0
        icon: "folder"
        title: "No music yet"
        hint: library.folders.length ? "Hallucinate is looking through your music folders; songs appear as they're found."
                                     : "Add the folder where you keep your music and it shows up here."
        actionText: library.folders.length ? "" : "Open Settings"
        onAction: Nav.openSettings()
    }

    // Every genre as a tile with a cover from it, most songs first (or A–Z); click one for its page
    Component {
        id: genresView
        Item {
            id: genresBox
            property bool az: shell.uiValue("genresOrder", "count") === "az"
            onAzChanged: shell.setUiValue("genresOrder", az ? "az" : "count")
            CollectionMenu { id: genreTileMenu; objectName: "genreMenu" }
            readonly property var genres: az ? library.genreList.slice().sort(function (a, b) {
                return a.name.localeCompare(b.name) }) : library.genreList
            Row {
                id: genreOrder
                x: 28
                spacing: 6
                Chip { text: "Most songs"; selected: !genresBox.az; onClicked: genresBox.az = false }
                Chip { objectName: "genresAz"; text: "A–Z"; selected: genresBox.az; onClicked: genresBox.az = true }
            }
            GridView {
                id: genreGrid
                objectName: "genreGrid"
                anchors { top: genreOrder.bottom; topMargin: 12; left: parent.left; right: parent.right; bottom: parent.bottom }
                leftMargin: 20; rightMargin: 8
                cellWidth: Math.floor((width - 28) / Math.max(2, Math.floor((width - 40) / 230)))
                cellHeight: 92
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: genresBox.genres
                ScrollBar.vertical: ScrollBar {}
                delegate: Item {
                    required property var modelData
                    width: genreGrid.cellWidth; height: genreGrid.cellHeight
                    Rectangle {
                        anchors { fill: parent; margins: 6 }
                        radius: Theme.radius
                        color: tileHover.hovered ? Theme.glassHover : Theme.glass
                        border.color: Theme.stroke
                        Cover {
                            id: tileCover
                            x: 10; anchors.verticalCenter: parent.verticalCenter
                            width: 60; height: 60
                            radius: Theme.radiusSmall
                            source: modelData.artUrl || ""
                            fallback: modelData.name.charAt(0)
                        }
                        Column {
                            anchors { left: tileCover.right; leftMargin: 12; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                            spacing: 3
                            Text {
                                textFormat: Text.PlainText
                                width: parent.width
                                text: modelData.name
                                elide: Text.ElideRight
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(14)
                                font.weight: Font.DemiBold
                            }
                            Text {
                                textFormat: Text.PlainText
                                width: parent.width
                                text: modelData.albums + (modelData.albums === 1 ? " album" : " albums") + "  ·  "
                                      + modelData.tracks + (modelData.tracks === 1 ? " song" : " songs")
                                elide: Text.ElideRight
                                color: Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(12)
                            }
                        }
                        HoverHandler { id: tileHover; cursorShape: Qt.PointingHandCursor }
                        // right-click (or a long press): play, queue or add the whole genre to a playlist
                        TapHandler { onTapped: Nav.openGenre(modelData.name); onLongPressed: genreTileMenu.showGenre(modelData.name) }
                        TapHandler { acceptedButtons: Qt.RightButton; onTapped: genreTileMenu.showGenre(modelData.name) }
                        Accessible.role: Accessible.Link
                        Accessible.name: "Genre: " + modelData.name
                        Accessible.onPressAction: Nav.openGenre(modelData.name)
                    }
                }
            }
            EmptyState {
                anchors.centerIn: genreGrid
                visible: genreGrid.count === 0 && library.ready
                icon: "note"
                title: "No genres yet"
                hint: "Songs' genre tags show up here. Library health can find genres online for albums without one."
            }
        }
    }
}
