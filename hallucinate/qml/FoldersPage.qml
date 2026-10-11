import QtQuick
import QtQuick.Controls
import "."

// The library as your folders on disk: breadcrumbs, the subfolders (with a cover from inside), then the songs.
Item {
    id: page
    objectName: "folders"
    property string path: shell.uiValue("foldersPath", "")
    property int revision: 0
    readonly property var listing: library.ready && revision >= 0 ? library.folderContents(path) : ({})
    readonly property var folders: listing.folders || []
    readonly property var tracks: listing.tracks || []
    onPathChanged: shell.setUiValue("foldersPath", path)
    Connections {
        target: library
        function onReloaded() { page.revision++ }
    }
    // a remembered folder that has gone away falls back to the top
    onListingChanged: if (path.length && folders.length === 0 && tracks.length === 0 && library.trackCount > 0) path = ""

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
            spacing: 16

            // Breadcrumbs
            Flow {
                objectName: "folderCrumbs"
                width: col.width
                spacing: 6
                Text {
                    text: "Folders"
                    color: page.path.length ? Theme.textDim : Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.fontSize(page.path.length ? 18 : 25)
                    font.weight: Font.Bold
                    MouseArea { anchors.fill: parent; enabled: page.path.length > 0; cursorShape: Qt.PointingHandCursor; onClicked: page.path = "" }
                }
                Repeater {
                    model: page.listing.crumbs || []
                    Row {
                        required property var modelData
                        required property int index
                        spacing: 6
                        Text {
                            anchors.baseline: crumb.baseline
                            text: "›"
                            color: Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSize(18)
                        }
                        Text {
                            id: crumb
                            readonly property bool last: index === (page.listing.crumbs || []).length - 1
                            text: modelData.name
                            color: last ? Theme.text : Theme.textDim
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.fontSize(last ? 25 : 18)
                            font.weight: Font.Bold
                            MouseArea { anchors.fill: parent; enabled: !crumb.last; cursorShape: Qt.PointingHandCursor; onClicked: page.path = modelData.path }
                        }
                    }
                }
            }

            Row {
                spacing: 10
                visible: page.path.length > 0
                PillButton { objectName: "playFolder"; primary: true; text: "Play folder"; onClicked: library.playFolder(page.path, false) }
                PillButton { text: "Shuffle"; onClicked: library.playFolder(page.path, true) }
                PillButton { text: "Add to queue"; onClicked: library.enqueueFolder(page.path) }
                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: (page.listing.parent || "").length > 0 || page.path.length > 0
                    icon: "back"; size: 16; tip: "Up a folder"
                    onClicked: page.path = page.listing.parent || ""
                }
            }

            Text {
                visible: page.folders.length === 0 && page.tracks.length === 0
                text: library.folders.length ? "Nothing here yet." : "Add a music folder in Settings to browse it here."
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(14)
            }

            // Subfolders
            Flow {
                objectName: "subfolders"
                width: col.width
                spacing: 10
                visible: page.folders.length > 0
                Repeater {
                    model: page.folders
                    Rectangle {
                        id: tile
                        required property var modelData
                        width: Math.max(240, (col.width - 2 * 10) / 3 - 1)
                        height: 68
                        radius: 16
                        color: tileHover.hovered ? Theme.glassHover : Theme.glass
                        HoverHandler { id: tileHover }
                        border.width: 1
                        border.color: Theme.stroke
                        Cover {
                            id: folderArt
                            x: 10; anchors.verticalCenter: parent.verticalCenter
                            width: 48; height: 48; radius: 10
                            source: tile.modelData.artUrl || ""
                            fallback: ""
                            Icon {
                                anchors.centerIn: parent
                                visible: !(tile.modelData.artUrl || "").length
                                width: 22; height: 22
                                name: "folder"
                                color: Theme.textDim
                            }
                        }
                        Column {
                            anchors { left: folderArt.right; leftMargin: 12; right: playButton.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                            spacing: 2
                            Text {
                                width: parent.width
                                text: tile.modelData.name
                                color: Theme.text
                                elide: Text.ElideRight
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(14)
                                font.weight: Font.DemiBold
                            }
                            Text {
                                width: parent.width
                                text: tile.modelData.songs + (tile.modelData.songs === 1 ? " song" : " songs") + "  ·  " + tile.modelData.durText
                                color: Theme.textDim
                                elide: Text.ElideRight
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(11)
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.path = tile.modelData.path
                        }
                        IconButton {
                            id: playButton
                            anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                            icon: "play"; size: 14
                            tip: "Play this folder"
                            opacity: tileHover.hovered ? 1 : 0
                            onClicked: library.playFolder(tile.modelData.path, false)
                        }
                    }
                }
            }

            // Songs in this folder
            Column {
                width: col.width
                spacing: 2
                visible: page.tracks.length > 0
                SectionHeader { title: "Songs"; subtitle: page.tracks.length + (page.tracks.length === 1 ? " song in this folder" : " songs in this folder") }
                Item { width: 1; height: 6 }
                Repeater {
                    model: page.tracks
                    TrackRow {
                        required property var modelData
                        required property int index
                        width: col.width
                        number: modelData.track_no > 0 ? modelData.track_no : index + 1
                        path: modelData.path
                        title: modelData.title
                        artist: modelData.artist
                        album: modelData.album
                        durText: modelData.durText
                        showArt: false
                        audioFormat: modelData.codec
                        audioBitrate: modelData.bitrate
                        current: player.hasTrack && player.current.path === modelData.path
                        onActivated: player.playList(page.tracks, index)
                        onEnqueue: player.enqueue(modelData)
                    }
                }
            }
        }
    }
}
