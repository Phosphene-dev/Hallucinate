import QtQuick
import QtQuick.Controls
import "."

// Home is about your library: something to play from your own shelves, when you listen, what your collection
// holds, and albums you haven't heard in a while.
Item {
    id: page
    objectName: "home"
    property var pick: ({})
    readonly property var facts: userLib.home.facts || ({})

    function reroll() { pick = library.randomAlbum(pick.album_key || "") }
    Component.onCompleted: reroll()
    Connections {
        target: library
        function onReloaded() { if (!page.pick.album_key) page.reroll() }
    }

    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: fl
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: col
            objectName: "homeColumn"
            x: Theme.contentX(fl.width); y: 12
            width: Theme.contentWidth(fl.width)
            spacing: 26

            Column {
                width: parent.width
                spacing: 6
                Text {
                    textFormat: Text.PlainText
                    text: qsTr("Home")
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale
                    font.weight: Font.Bold
                }
                Text {
                    textFormat: Text.PlainText
                    objectName: "librarySummary"
                    width: parent.width
                    wrapMode: Text.WordWrap
                    visible: library.trackCount > 0
                    text: [Theme.counted(qsTr("%n album(s)", "", library.albumCount), library.albumCount),
                           Theme.counted(qsTr("%n song(s)", "", library.trackCount), library.trackCount),
                           Theme.counted(qsTr("%n artist(s)", "", library.artistCount), library.artistCount),
                           page.facts.seconds ? qsTr("%1 of music").arg(Theme.fmtHours(page.facts.seconds)) : ""].filter(s => s).join("  ·  ")
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(14)
                }
                Text {
                    textFormat: Text.PlainText
                    objectName: "homeHealthLink"
                    visible: library.trackCount > 0 && shell.features.health !== false
                    text: qsTr("Library health ›")
                    color: healthLinkMouse.containsMouse ? Theme.accentHi : Theme.accent
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(13)
                    font.weight: Font.DemiBold
                    LinkArea { id: healthLinkMouse; name: "Library health"; hoverEnabled: true; onClicked: Nav.openHealth() }
                }
            }

            Rectangle {
                visible: library.trackCount === 0
                width: parent.width
                height: 220
                radius: Theme.radius + 4
                color: Theme.surface
                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    Text {
                        textFormat: Text.PlainText
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: !library.ready ? qsTr("Loading your library…")
                            : library.scanning ? qsTr("Scanning your music…")
                            : library.hasFolders ? qsTr("No music found") : qsTr("Welcome! Let's find your music")
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: (Theme.fontSize(16)) * Theme.displayScale
                        font.weight: Font.DemiBold
                    }
                    Text {
                        textFormat: Text.PlainText
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: library.scanning ? qsTr("Songs appear here as they are found.")
                            : library.missingFolders.length > 0 ? qsTr("Folder not found or unreadable: %1").arg(library.missingFolders.join(", "))
                            : library.hasFolders ? qsTr("Your folders contain no supported audio files. Add another folder or check Settings.")
                            : qsTr("Choose the folder that holds your music to get started.")
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(14)
                    }
                    ScanBar { width: 320; anchors.horizontalCenter: parent.horizontalCenter }
                    PillButton {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: !library.scanning && library.ready
                        primary: true
                        text: qsTr("Choose music folder")
                        onClicked: picker.open()
                    }
                    FolderPicker { id: picker }
                }
            }

            // Something to play, and when you listen
            Flow {
                id: topCards
                readonly property bool both: shell.features.homeRandom !== false && shell.features.homeListening !== false
                visible: library.trackCount > 0 && (shell.features.homeRandom !== false || shell.features.homeListening !== false)
                width: parent.width
                spacing: 18
                RandomAlbumCard {
                    visible: shell.features.homeRandom !== false
                    width: topCards.both && col.width >= 860 ? (col.width - 18) * 0.5 : col.width
                    album: page.pick
                    onReroll: page.reroll()
                }
                ListeningCard {
                    visible: shell.features.homeListening !== false
                    width: topCards.both && col.width >= 860 ? (col.width - 18) * 0.5 : col.width
                }
            }

            // What your collection holds: four across, or two by two when the window is narrow
            Grid {
                id: factRow
                visible: library.trackCount > 0 && shell.features.homeFacts !== false
                width: parent.width
                columns: width >= 760 ? 4 : 2
                spacing: 14
                readonly property real tileWidth: (width - (columns - 1) * spacing) / columns
                // every tile as tall as the format legend needs, so a wrapped legend stays inside its card
                readonly property real tileHeight: Math.max(96, formatsColumn.implicitHeight + 36)
                component Fact: GlassPanel {
                    property string value
                    property string label
                    width: factRow.tileWidth; height: factRow.tileHeight
                    Column {
                        anchors { left: parent.left; right: parent.right; leftMargin: 20; rightMargin: 12; verticalCenter: parent.verticalCenter }
                        spacing: 4
                        Text { width: parent.width; elide: Text.ElideRight; text: value; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(21)) * Theme.displayScale; font.weight: Font.Bold; textFormat: Text.PlainText }
                        Text { width: parent.width; elide: Text.ElideRight; text: label; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); textFormat: Text.PlainText }
                    }
                }
                Fact { value: page.facts.seconds ? Theme.fmtHours(page.facts.seconds).replace(" ", "\u2009") : "–"; label: qsTr("of music") }
                Fact { value: page.facts.bytes ? Theme.fmtBytes(page.facts.bytes) : "–"; label: qsTr("on disk") }
                Fact { value: page.facts.tracks ? Math.round(page.facts.lossless * 100) + "%" : "–"; label: qsTr("lossless") }
                GlassPanel {
                    id: formatsTile
                    objectName: "formatsTile"
                    width: factRow.tileWidth; height: factRow.tileHeight
                    readonly property var formats: page.facts.formats || []
                    readonly property var swatches: [Theme.accent, Theme.art1, Theme.art2, Theme.accentHi, Theme.textDim]
                    Column {
                        id: formatsColumn
                        anchors { left: parent.left; right: parent.right; margins: 18; verticalCenter: parent.verticalCenter }
                        spacing: 10
                        Row {
                            id: formatsBar
                            width: parent.width
                            height: 10
                            spacing: 2
                            clip: true
                            Repeater {
                                model: formatsTile.formats
                                Rectangle {
                                    required property var modelData
                                    required property int index
                                    width: Math.max(3, (formatsBar.width - formatsBar.spacing * (formatsTile.formats.length - 1)) * modelData.share)
                                    height: 10
                                    radius: 5
                                    color: formatsTile.swatches[index % 5]
                                }
                            }
                        }
                        Flow {
                            width: parent.width
                            spacing: 10
                            Repeater {
                                model: formatsTile.formats
                                Row {
                                    required property var modelData
                                    required property int index
                                    spacing: 5
                                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: formatsTile.swatches[index % 5] }
                                    Text { text: modelData.name + " " + Math.round(modelData.share * 100) + "%"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); textFormat: Text.PlainText }
                                }
                            }
                        }
                    }
                }
            }

            component AlbumShelf: Column {
                property alias model: shelf.model
                property string title
                property string subtitle
                spacing: 14
                width: col.width
                SectionHeader { title: parent.title; subtitle: parent.subtitle }
                Item {
                    width: parent.width
                    height: 262
                    ListView {
                        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
                        id: shelf
                        anchors.fill: parent
                        // room around the cards for a hovered cover's lift and glow, which the clip would cut off (#110)
                        anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                        topMargin: 14; leftMargin: 14; rightMargin: 14
                        contentY: -topMargin  // (the cards sit below that room; a sideways list doesn't move them itself)
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
                            selectionSource: ListView.view ? ListView.view.model : null
                            rowIndex: index
                        }
                    }
                    ShelfArrows { row: shelf; anchors.fill: parent }
                }
            }

            AlbumShelf {
                objectName: "rediscoverShelf"
                visible: userLib.rediscover.count > 0 && shell.features.homeShelves !== false
                title: qsTr("Rediscover")
                subtitle: qsTr("Albums you haven't played in a while, or ever")
                model: userLib.rediscover
            }
            AlbumShelf {
                visible: userLib.onThisDay.count > 0 && shell.features.homeShelves !== false
                title: qsTr("On this day")
                subtitle: qsTr("What you were listening to around this date in past years")
                model: userLib.onThisDay
            }
            AlbumShelf {
                visible: library.recentAlbums.count > 0 && shell.features.homeShelves !== false
                title: qsTr("Recently added")
                subtitle: qsTr("New on your shelves")
                model: library.recentAlbums
            }
        }
    }
}
