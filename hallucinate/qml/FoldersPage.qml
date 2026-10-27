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
            x: Theme.contentX(fl.width); y: 20
            width: Theme.contentWidth(fl.width)
            spacing: 16

            // Breadcrumbs
            Flow {
                objectName: "folderCrumbs"
                width: col.width
                spacing: 6
                Text {
                    textFormat: Text.PlainText
                    text: "Folders"
                    color: page.path.length ? Theme.textDim : Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: (Theme.fontSize(page.path.length ? 18 : 25)) * Theme.displayScale
                    font.weight: Font.Bold
                    LinkArea { enabled: page.path.length > 0; onClicked: page.path = "" }
                }
                Repeater {
                    model: page.listing.crumbs || []
                    Row {
                        required property var modelData
                        required property int index
                        spacing: 6
                        Text {
                            textFormat: Text.PlainText
                            anchors.baseline: crumb.baseline
                            text: "›"
                            color: Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSize(18)
                        }
                        Text {
                            textFormat: Text.PlainText
                            id: crumb
                            readonly property bool last: index === (page.listing.crumbs || []).length - 1
                            text: modelData.name
                            color: last ? Theme.text : Theme.textDim
                            font.family: Theme.displayFamily
                            font.pixelSize: (Theme.fontSize(last ? 25 : 18)) * Theme.displayScale
                            font.weight: Font.Bold
                            LinkArea { enabled: !crumb.last; onClicked: page.path = modelData.path }
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

            Item { width: 1; height: 30; visible: noFolders.visible }
            EmptyState {
                id: noFolders
                anchors.horizontalCenter: parent.horizontalCenter
                visible: page.folders.length === 0 && page.tracks.length === 0
                icon: "folder"
                title: library.folders.length ? "Nothing here yet" : "No music folders yet"
                hint: library.folders.length ? "No music in this folder."
                                             : "Add the folder where you keep your music to browse it here."
                actionText: library.folders.length ? "" : "Open Settings"
                onAction: Nav.openSettings()
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
                        required property int index
                        Pick { id: folderPick; target: tile; kind: "folder"; entry: tile.modelData; source: page.folders; index: tile.index }
                        // from the keyboard: Tab to it, Enter opens it, the Menu key its menu
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: "Open " + tile.modelData.name + ", " + Theme.num(tile.modelData.songs) + (tile.modelData.songs === 1 ? " song" : " songs")
                        Accessible.selected: folderPick.selected
                        Accessible.onPressAction: page.path = tile.modelData.path
                        Keys.onShortcutOverride: function (event) { event.accepted = [Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter].indexOf(event.key) >= 0 || ((event.modifiers & Qt.ControlModifier) && (event.key === Qt.Key_A || event.key === Qt.Key_Space)) }
                        Keys.onPressed: function (event) {
                            if (folderPick.keys(event)) return
                            if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) { Nav.folderMenu(tile.modelData.path, tile.modelData.name); event.accepted = true }
                        }
                        Keys.onReturnPressed: page.path = tile.modelData.path
                        Keys.onEnterPressed: page.path = tile.modelData.path
                        Keys.onSpacePressed: page.path = tile.modelData.path
                        Rectangle { anchors.fill: parent; anchors.margins: -3; radius: Theme.round(18); color: "transparent"; border.width: 2; border.color: Theme.accent; visible: tile.activeFocus }
                        width: Math.max(240, (col.width - 2 * 10) / 3 - 1)
                        height: 68
                        radius: Theme.round(16)
                        color: tileHover.hovered ? Theme.glassHover : Theme.glass
                        HoverHandler { id: tileHover }
                        border.width: folderPick.selected ? 2 : 1
                        border.color: folderPick.selected ? Theme.accent : Theme.stroke
                        Cover {
                            id: folderArt
                            x: 10; anchors.verticalCenter: parent.verticalCenter
                            width: 48; height: 48; radius: Theme.round(10)
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
                                textFormat: Text.PlainText
                                width: parent.width
                                text: tile.modelData.name
                                color: Theme.text
                                elide: Text.ElideRight
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(14)
                                font.weight: Font.DemiBold
                            }
                            Text {
                                textFormat: Text.PlainText
                                width: parent.width
                                text: Theme.num(tile.modelData.songs) + (tile.modelData.songs === 1 ? " song" : " songs") + "  ·  " + tile.modelData.durText
                                color: Theme.textDim
                                elide: Text.ElideRight
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(11)
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onPressAndHold: if (!PickDrag.pick) Nav.folderMenu(tile.modelData.path, tile.modelData.name)
                            Accessible.role: Accessible.Button
                            Accessible.name: "Open " + tile.modelData.name + ", " + tile.modelData.songs
                                             + (tile.modelData.songs === 1 ? " song" : " songs")
                            Accessible.onPressAction: page.path = tile.modelData.path
                            onPressed: function (mouse) { folderPick.press(this, mouse) }
                            onPositionChanged: function (mouse) { folderPick.move(this, mouse) }
                            onReleased: folderPick.release(this)
                            onCanceled: folderPick.cancel(this)
                            onClicked: function (mouse) {
                                if (mouse.button === Qt.RightButton) Nav.folderMenu(tile.modelData.path, tile.modelData.name)
                                else if (!folderPick.click(mouse)) page.path = tile.modelData.path
                            }
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
                SectionHeader { title: "Songs"; subtitle: Theme.num(page.tracks.length) + (page.tracks.length === 1 ? " song in this folder" : " songs in this folder") }
                Item { width: 1; height: 6 }
                Repeater {
                    model: page.tracks
                    TrackRow {
                        selectionSource: page.tracks
                        required property var modelData
                        required property int index
                        rowIndex: index
                        width: col.width
                        number: modelData.track_no > 0 ? modelData.track_no : index + 1
                        path: modelData.path
                        title: modelData.title
                        artist: modelData.artist
                        album: modelData.album
                        durText: modelData.durText
                        showArt: false
                        audioFormat: modelData.codec
                        bitDepth: modelData.bit_depth || 0
                        sampleRate: modelData.sample_rate || 0
                        explicitTag: modelData.explicit || 0
                        audioBitrate: modelData.bitrate
                        current: Rows.currentPath === modelData.path
                        onActivated: player.playList(page.tracks, index)
                        onEnqueue: player.enqueue(modelData)
                    }
                }
            }
        }
    }
}
