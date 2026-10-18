import QtQuick
import QtQuick.Controls
import "."

// Floats above the player while songs are selected (Ctrl/Shift+click in a list) and acts on all of them.
Rectangle {
    id: bar
    objectName: "selectionBar"
    signal editTags(var paths)
    signal removeFromPlaylist(var paths)
    readonly property bool shown: Selection.count > 0
    // songs on a music server: no files here to edit or put in the trash
    readonly property bool onServer: Selection.paths.some(function (p) { return /^(subsonic|jellyfin):\/\//.test(p) })
    // selected in the playlist that's open (not Liked Songs or a smart playlist): they can be taken out of it
    readonly property bool inPlaylist: Selection.source !== null && Selection.source === userLib.playlistTracks

    property real maxWidth: parent ? parent.width - 32 : 900
    readonly property bool tight: maxWidth < 860  // short labels in small windows
    width: Math.min(row.implicitWidth + 28, maxWidth)
    height: 52
    radius: 26
    color: Theme.glassStrong
    border.width: 1
    border.color: Theme.strokeHi
    opacity: shown ? 1 : 0
    visible: opacity > 0
    enabled: shown
    Behavior on opacity { NumberAnimation { duration: 160 } }

    function paths() { return Selection.paths.slice() }
    function done(message) { Selection.clear(); if (message) Nav.notify(message) }
    function songs(n) { return n + (n === 1 ? " song" : " songs") }

    Flickable {
        id: scroller
        anchors { fill: parent; leftMargin: 14; rightMargin: 14 }
        contentWidth: row.implicitWidth
        clip: true
        interactive: contentWidth > width
        boundsBehavior: Flickable.StopAtBounds
        Row {
            id: row
            height: parent.height
            spacing: 6
            Text {
                textFormat: Text.PlainText
                objectName: "selectionCount"
                anchors.verticalCenter: parent.verticalCenter
                rightPadding: 6
                text: bar.tight ? Selection.count + " selected" : bar.songs(Selection.count) + " selected"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
                font.weight: Font.DemiBold
            }
            component Action: PillButton { anchors.verticalCenter: parent.verticalCenter; implicitHeight: 34 }
            Action { objectName: "selectionPlay"; primary: true; text: "Play"; onClicked: { userLib.playPaths(bar.paths()); bar.done("") } }
            Action { text: bar.tight ? "Next" : "Play next"; onClicked: { var p = bar.paths(); userLib.playNextPaths(p); bar.done(bar.songs(p.length) + " will play next") } }
            Action { objectName: "selectionQueue"; text: bar.tight ? "Queue" : "Add to queue"; onClicked: { var p = bar.paths(); userLib.enqueuePaths(p); bar.done(bar.songs(p.length) + " added to the queue") } }
            Action {
                id: plButton
                text: bar.tight ? "Playlist…" : "Add to playlist…"
                onClicked: plMenu.popup(plButton, 0, -plMenu.implicitHeight - 6)
                Menu {
                    id: plMenu
                    MenuItem { text: "New playlist…"; icon.name: "plus"; onTriggered: newPl.open() }
                    MenuSeparator {}
                    Instantiator {
                        model: userLib.playlists
                        delegate: MenuItem {
                            text: Theme.plain(model.name)
                            onTriggered: { var p = bar.paths(); userLib.addPathsToPlaylist(model.id, p); bar.done(bar.songs(p.length) + " added to “" + model.name + "”") }
                        }
                        onObjectAdded: (index, object) => plMenu.insertItem(index + 2, object)
                        onObjectRemoved: (index, object) => plMenu.removeItem(object)
                    }
                }
            }
            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                icon: "heart"; size: 16
                visible: shell.features.liked !== false
                readonly property bool all: userLib.likesRevision >= 0 && userLib.allLiked(Selection.paths)
                active: all
                tip: all ? "Unlike all" : "Like all"
                onClicked: { userLib.setLikedPaths(bar.paths(), !all) }
            }
            Action {
                id: rateButton
                text: bar.tight ? "Rate" : "Rate…"
                onClicked: rateMenu.popup(rateButton, 0, -rateMenu.implicitHeight - 6)
                Menu {
                    id: rateMenu
                    Repeater {
                        model: 5
                        MenuItem {
                            required property int index
                            text: "★★★★★".slice(0, 5 - index) + "☆☆☆☆☆".slice(0, index)
                            onTriggered: { var p = bar.paths(); userLib.setRatingPaths(p, 5 - index); bar.done(bar.songs(p.length) + " rated " + (5 - index) + "★") }
                        }
                    }
                    MenuSeparator {}
                    MenuItem { text: "Clear rating"; onTriggered: { userLib.setRatingPaths(bar.paths(), 0); bar.done("") } }
                }
            }
            Action {
                objectName: "selectionEditTags"
                visible: !bar.onServer
                text: bar.tight ? "Tags…" : "Edit tags…"
                enabled: Selection.paths.every(function (p) { return !/\.[A-Za-z0-9]+#\d+$/.test(p) })
                onClicked: bar.editTags(bar.paths())
            }
            Action {
                id: moreButton
                objectName: "selectionMore"
                text: bar.tight ? "More" : "More…"
                onClicked: moreMenu.popup(moreButton, 0, -moreMenu.implicitHeight - 6)
                Menu {
                    id: moreMenu
                    MenuItem {
                        objectName: "selectionRemoveFromPlaylist"
                        visible: bar.inPlaylist
                        height: visible ? implicitHeight : 0
                        text: "Remove from this playlist"; icon.name: "remove"; icon.color: Theme.error
                        onTriggered: bar.removeFromPlaylist(bar.paths())
                    }
                    MenuItem {
                        text: "Remove from library…"; icon.name: "remove"; icon.color: Theme.error
                        onTriggered: Nav.removeSongs(bar.paths(), bar.songs(Selection.count))
                    }
                    MenuItem {
                        objectName: "selectionTrash"
                        visible: !bar.onServer
                        height: visible ? implicitHeight : 0
                        text: "Move to trash…"; icon.name: "trash"; icon.color: Theme.error
                        onTriggered: Nav.trashSongs(bar.paths(), bar.songs(Selection.count))
                    }
                }
            }
            IconButton {
                objectName: "selectionClear"
                anchors.verticalCenter: parent.verticalCenter
                icon: "close"; size: 14; tip: "Clear selection (Esc)"
                onClicked: Selection.clear()
            }
        }
    }

    Rectangle {  // more buttons to the right: scroll (wheel or drag) to reach them
        anchors { right: parent.right; rightMargin: 1; verticalCenter: parent.verticalCenter }
        width: 36; height: parent.height - 2; radius: height / 2
        visible: scroller.contentWidth > scroller.width && !scroller.atXEnd
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 1; color: Theme.glassStrong }
        }
    }

    Dialog {
        id: newPl
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "New playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { plName.text = ""; plName.forceActiveFocus() }
        onAccepted: {
            var name = plName.text.trim()
            if (!name.length) return
            var p = bar.paths()
            userLib.addPathsToNewPlaylist(name, p)
            bar.done(bar.songs(p.length) + " added to “" + name + "”")
        }
        TextField {
            id: plName; width: 280; placeholderText: "Playlist name"; selectByMouse: true
            onAccepted: if (text.trim().length) newPl.accept()  // no nameless playlists
            onTextChanged: { var b = newPl.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newPl.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
}
