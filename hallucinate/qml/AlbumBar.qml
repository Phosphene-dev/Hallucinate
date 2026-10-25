import QtQuick
import QtQuick.Controls
import "."

// Floats above the player while albums are selected (Ctrl/Shift+click in a grid) and acts on all of them.
Rectangle {
    id: bar
    objectName: "albumBar"
    readonly property bool shown: AlbumSelection.count > 0
    property real maxWidth: parent ? parent.width - 32 : 900
    readonly property bool tight: maxWidth < 860
    width: Math.min(row.implicitWidth + 28, maxWidth)
    height: 52
    radius: Theme.round(26)
    color: Theme.glassStrong
    border.width: 1
    border.color: Theme.strokeHi
    opacity: shown ? 1 : 0
    visible: opacity > 0
    enabled: shown
    Behavior on opacity { NumberAnimation { duration: 160 } }

    function keys() { return AlbumSelection.keys.slice() }
    function what(n) { return n + (n === 1 ? " album" : " albums") }
    function done(message) { AlbumSelection.clear(); if (message) Nav.notify(message) }

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
                objectName: "albumSelectionCount"
                anchors.verticalCenter: parent.verticalCenter
                rightPadding: 6
                text: bar.what(AlbumSelection.count) + " selected"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
                font.weight: Font.DemiBold
            }
            component Action: PillButton { anchors.verticalCenter: parent.verticalCenter; implicitHeight: 34 }
            Action { primary: true; text: "Play"; onClicked: { userLib.playPaths(library.albumPaths(bar.keys())); bar.done("") } }
            Action {
                text: bar.tight ? "Next" : "Play next"
                onClicked: { var k = bar.keys(); userLib.playNextPaths(library.albumPaths(k)); bar.done(bar.what(k.length) + " will play next") }
            }
            Action {
                text: bar.tight ? "Queue" : "Add to queue"
                onClicked: { var k = bar.keys(); userLib.enqueuePaths(library.albumPaths(k)); bar.done(bar.what(k.length) + " added to the queue") }
            }
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
                            onTriggered: {
                                var k = bar.keys()
                                userLib.addPathsToPlaylist(model.id, library.albumPaths(k))
                                bar.done(bar.what(k.length) + " added to “" + model.name + "”")
                            }
                        }
                        onObjectAdded: (index, object) => plMenu.insertItem(index + 2, object)
                        onObjectRemoved: (index, object) => plMenu.removeItem(object)
                    }
                }
            }
            Action {
                objectName: "albumBarRemove"
                text: bar.tight ? "Remove…" : "Remove from library…"
                onClicked: Nav.removeAlbums(bar.keys(), bar.what(AlbumSelection.count))
            }
            Action { text: bar.tight ? "Trash…" : "Move to trash…"; onClicked: Nav.trashAlbums(bar.keys(), bar.what(AlbumSelection.count)) }
            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                icon: "close"; size: 14; tip: "Clear selection (Esc)"
                onClicked: AlbumSelection.clear()
            }
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
            var k = bar.keys()
            userLib.addPathsToNewPlaylist(name, library.albumPaths(k))
            bar.done(bar.what(k.length) + " added to “" + name + "”")
        }
        TextField {
            id: plName; width: 280; placeholderText: "Playlist name"; selectByMouse: true
            onAccepted: if (text.trim().length) newPl.accept()  // no nameless playlists
            onTextChanged: { var b = newPl.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newPl.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
}
