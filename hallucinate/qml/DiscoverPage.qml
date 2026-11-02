import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Discover: music from your own library to find again. Every shelf can be hidden from its own menu (or in
// Settings → Discover), and a hidden shelf isn't even read.
Item {
    id: page
    objectName: "discover"
    Component.onCompleted: discover.open()

    function shelfOn(name) { return shell.features[name] !== false }
    function hideShelf(name, title) {
        discover.setShelf(name, false)
        Nav.notifyAction(qsTr("“%1” hidden. Settings → Discover brings it back").arg(title), qsTr("Undo"),
                         function () { discover.setShelf(name, true) })
    }

    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: col
            objectName: "discoverColumn"
            x: Theme.contentX(parent.width)
            y: 22
            width: Theme.contentWidth(parent.width)
            spacing: 30

            RowLayout {
                width: parent.width
                spacing: 12
                Column {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        textFormat: Text.PlainText
                        text: qsTr("Discover")
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale
                        font.weight: Font.Bold
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("Music in your own library to find again. Worked out on this computer from what you play; nothing is sent anywhere.")
                        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                    }
                }
                IconButton {
                    objectName: "discoverSettings"
                    icon: "settings"
                    tip: qsTr("Discover settings")
                    onClicked: Nav.openSettingsAt("discover")
                }
            }

            EmptyState {
                objectName: "discoverEmpty"
                visible: discover.empty && !discover.loading
                width: parent.width
                icon: "discover"
                title: qsTr("Nothing to suggest yet")
                hint: qsTr("Play some music and come back: suggestions come from what you listen to. Hidden shelves can be brought back in Settings → Discover.")
                actionText: qsTr("Discover settings")
                onAction: Nav.openSettingsAt("discover")
            }

            // --- daily mixes ---------------------------------------------------------------------------
            Column {
                objectName: "mixesShelf"
                visible: page.shelfOn("discoverMixes") && discover.mixes.length > 0
                width: parent.width
                spacing: 14
                ShelfHeader {
                    shelf: "discoverMixes"
                    title: qsTr("Daily mixes")
                    subtitle: qsTr("Made fresh each day from what you play, with a few songs you haven't yet")
                }
                Flow {
                    width: parent.width
                    spacing: 18
                    Repeater {
                        model: discover.mixes
                        MixCard {}
                    }
                }
            }

            AlbumShelf {
                shelf: "discoverForgotten"
                title: qsTr("Forgotten favourites")
                subtitle: qsTr("Albums you played a lot, but not for a while")
                model: discover.forgottenAlbums
            }
            SongShelf {
                shelf: "discoverForgottenSongs"
                listName: "songs"
                title: qsTr("Songs you used to love")
                subtitle: qsTr("Played often, liked or rated highly, then left behind")
                model: discover.forgottenSongs
            }
            Column {
                objectName: "artistsShelf"
                visible: page.shelfOn("discoverForgottenArtists") && discover.forgottenArtists.count > 0
                width: parent.width
                spacing: 14
                ShelfHeader {
                    shelf: "discoverForgottenArtists"
                    title: qsTr("Artists to return to")
                    subtitle: qsTr("Ones you played often, not lately")
                }
                Item {
                    width: parent.width
                    height: 222
                    ListView {
                        WheelScroll {}
                        id: artistRow
                        anchors.fill: parent
                        anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                        topMargin: 14; leftMargin: 14; rightMargin: 14
                        contentY: -topMargin
                        orientation: ListView.Horizontal
                        spacing: 20
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        model: discover.forgottenArtists
                        delegate: ArtistCard {
                            name: model.name
                            subtitle: model.reason || ""
                            artUrl: model.artUrl
                            fromDiscover: true
                        }
                    }
                    ShelfArrows { row: artistRow; anchors.fill: parent }
                }
            }
            SongShelf {
                shelf: "discoverDeepCuts"
                listName: "deepCuts"
                title: qsTr("Deep cuts")
                subtitle: qsTr("Songs you've never played by the artists you play most")
                model: discover.deepCuts
            }
            AlbumShelf {
                shelf: "discoverNeverPlayed"
                title: qsTr("Never played")
                subtitle: qsTr("Albums you added a while ago and haven't listened to yet")
                model: discover.neverPlayed
            }

            // --- on this day ----------------------------------------------------------------------------
            Column {
                objectName: "onThisDayShelf"
                visible: page.shelfOn("discoverOnThisDay") && discover.onThisDay.length > 0
                width: parent.width
                spacing: 14
                ShelfHeader {
                    shelf: "discoverOnThisDay"
                    title: qsTr("On this day")
                    subtitle: qsTr("What you listened to around today's date in other years")
                }
                Repeater {
                    model: discover.onThisDay
                    Column {
                        required property var modelData
                        required property int index
                        width: col.width
                        spacing: 10
                        RowLayout {
                            width: parent.width
                            Text {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                text: qsTr("%1  ·  %2").arg(modelData.label).arg(modelData.year)
                                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
                            }
                            PillButton {
                                text: qsTr("Play those songs")
                                height: 30
                                onClicked: discover.playDay(index, 0)
                            }
                        }
                        Item {
                            width: parent.width
                            height: 262
                            ListView {
                                WheelScroll {}
                                id: dayRow
                                anchors.fill: parent
                                anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                                topMargin: 14; leftMargin: 14; rightMargin: 14
                                contentY: -topMargin
                                orientation: ListView.Horizontal
                                spacing: 20
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                model: modelData.albums
                                delegate: AlbumCard {
                                    required property var modelData
                                    albumKey: modelData.album_key
                                    title: modelData.album
                                    subtitle: modelData.album_artist
                                    artist: modelData.album_artist
                                    artUrl: modelData.artUrl
                                    fromDiscover: true
                                }
                            }
                            ShelfArrows { row: dayRow; anchors.fill: parent }
                        }
                    }
                }
            }
        }
    }

    // A shelf's heading, with its own menu: hide it, or go to Discover's settings
    component ShelfHeader: RowLayout {
        id: header
        property string shelf
        property string title
        property string subtitle
        width: col.width
        SectionHeader { Layout.fillWidth: true; title: header.title; subtitle: header.subtitle }
        IconButton {
            objectName: "shelfMenu_" + header.shelf
            icon: "more"
            tip: qsTr("Options for this shelf")
            onClicked: shelfMenu.popup()
        }
        Menu {
            id: shelfMenu
            MenuItem { objectName: "hideShelf_" + header.shelf; text: qsTr("Hide this shelf"); icon.name: "close"; onTriggered: page.hideShelf(header.shelf, header.title) }
            MenuItem { text: qsTr("Discover settings…"); icon.name: "settings"; onTriggered: Nav.openSettingsAt("discover") }
        }
    }

    component AlbumShelf: Column {
        id: albumShelf
        property string shelf
        property alias model: row.model
        property string title
        property string subtitle
        objectName: "shelf_" + shelf
        visible: page.shelfOn(shelf) && row.count > 0
        width: col.width
        spacing: 14
        ShelfHeader { shelf: albumShelf.shelf; title: albumShelf.title; subtitle: albumShelf.subtitle }
        Item {
            width: parent.width
            height: 262
            ListView {
                WheelScroll {}
                id: row
                anchors.fill: parent
                anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                topMargin: 14; leftMargin: 14; rightMargin: 14
                contentY: -topMargin
                orientation: ListView.Horizontal
                spacing: 20
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                delegate: AlbumCard {
                    albumKey: model.album_key
                    title: model.album
                    subtitle: model.album_artist
                    artist: model.album_artist
                    artUrl: model.artUrl
                    note: model.reason || ""
                    fromDiscover: true
                    selectionSource: ListView.view ? ListView.view.model : null
                    rowIndex: index
                }
            }
            ShelfArrows { row: row; anchors.fill: parent }
        }
    }

    // A few songs, with more a click away (a long list would push everything else off the page)
    component SongShelf: Column {
        id: songShelf
        property string shelf
        property string listName
        property alias model: songs.model
        property string title
        property string subtitle
        property bool expanded: false
        objectName: "shelf_" + shelf
        visible: page.shelfOn(shelf) && songs.count > 0
        width: col.width
        spacing: 10
        ShelfHeader { shelf: songShelf.shelf; title: songShelf.title; subtitle: songShelf.subtitle }
        Row {
            spacing: 10
            PillButton { text: qsTr("Play all"); height: 30; onClicked: discover.playSongs(songShelf.listName, 0) }
        }
        ListView {
            id: songs
            width: parent.width
            height: contentHeight
            interactive: false
            readonly property int shown: songShelf.expanded ? count : Math.min(count, 5)
            delegate: TrackRow {
                width: songs.width
                visible: index < songs.shown
                height: visible ? implicitHeight : 0
                number: index + 1
                title: model.title
                artist: model.artist
                album: model.reason || model.album
                durText: model.durText
                artUrl: model.artUrl
                path: model.path
                context: "discover"
                rowIndex: index
                selectionSource: songs.model
                current: player.current && player.current.path === model.path
                onActivated: discover.playSongs(songShelf.listName, index)
                onEnqueue: player.enqueue(songs.model.get(index))
            }
        }
        PillButton {
            visible: songs.count > 5
            height: 30
            text: songShelf.expanded ? qsTr("Show fewer") : qsTr("Show all %1").arg(songs.count)
            onClicked: songShelf.expanded = !songShelf.expanded
        }
    }

    // One daily mix: up to four covers, its name, what's in it; click to play, menu for the rest
    component MixCard: Rectangle {
        id: mix
        required property var modelData
        required property int index
        objectName: "mix_" + index
        width: 220
        height: 300
        radius: Theme.radius
        color: hover.hovered ? Theme.surfaceHi : Theme.surface
        border.width: 1
        border.color: Theme.stroke
        Accessible.role: Accessible.Button
        Accessible.name: modelData.title
        HoverHandler { id: hover }
        Grid {
            id: mosaic
            x: 14; y: 14
            columns: 2
            readonly property real cell: (mix.width - 28) / 2
            Repeater {
                model: 4
                Cover {
                    required property int index
                    width: mosaic.cell; height: mosaic.cell
                    source: mix.modelData.arts.length ? mix.modelData.arts[index % mix.modelData.arts.length] : ""
                }
            }
        }
        Column {
            anchors { left: parent.left; right: parent.right; top: mosaic.bottom; margins: 14 }
            spacing: 4
            Text {
                textFormat: Text.PlainText
                width: parent.width
                elide: Text.ElideRight
                text: mix.modelData.title
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                elide: Text.ElideRight
                text: mix.modelData.subtitle
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Text {
                textFormat: Text.PlainText
                text: qsTr("%1 songs  ·  %2 min").arg(mix.modelData.count).arg(mix.modelData.minutes)
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
            }
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onClicked: function (mouse) {
                if (mouse.button === Qt.RightButton) mixMenu.popup()
                else discover.playMix(mix.index, false)
            }
        }
        IconButton {
            anchors { right: parent.right; bottom: parent.bottom; margins: 8 }
            icon: "more"
            tip: qsTr("More for this mix")
            onClicked: mixMenu.popup()
        }
        Keys.onReturnPressed: discover.playMix(mix.index, false)
        Keys.onMenuPressed: mixMenu.popup()
        activeFocusOnTab: true
        Menu {
            id: mixMenu
            MenuItem { text: qsTr("Play"); icon.name: "play"; onTriggered: discover.playMix(mix.index, false) }
            MenuItem { text: qsTr("Shuffle"); icon.name: "shuffle"; onTriggered: discover.playMix(mix.index, true) }
            MenuItem {
                text: qsTr("Add to queue"); icon.name: "queue"
                onTriggered: { discover.queueMix(mix.index); Nav.notify(qsTr("“%1” added to the queue").arg(mix.modelData.title)) }
            }
            MenuItem {
                objectName: "saveMix"
                text: qsTr("Save as a playlist"); icon.name: "playlist"
                onTriggered: {
                    var id = discover.saveMix(mix.index)
                    if (id >= 0) Nav.notifyAction(qsTr("Saved as a playlist: it stays as it is when the mix changes"), qsTr("Open"),
                                                  function () { Nav.openPlaylist(id) })
                }
            }
        }
    }
}
