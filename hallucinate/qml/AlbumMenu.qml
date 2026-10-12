import QtQuick
import QtQuick.Controls
import "."

// Right-click (or "…") on an album, or on a selection of albums: play, queue, playlists, tags, remove.
Menu {
    id: menu
    objectName: "albumMenu"
    property var keys: []
    property string albumTitle: ""
    property string artist: ""
    readonly property bool single: keys.length === 1
    readonly property string what: single ? "“" + albumTitle + "”" : keys.length + " albums"

    // keys: the album keys to act on (the clicked album, or the whole selection when it was part of it)
    function show(k, title, art) { keys = k; albumTitle = title; artist = art; popup() }
    function paths() { return library.albumPaths(menu.keys) }

    MenuItem { text: "Play"; onTriggered: menu.single ? library.playAlbum(menu.keys[0], 0) : userLib.playPaths(menu.paths()) }
    MenuItem { text: "Play next"; onTriggered: { userLib.playNextPaths(menu.paths()); Nav.notify(menu.what + " will play next") } }
    MenuItem { text: "Add to queue"; onTriggered: { userLib.enqueuePaths(menu.paths()); Nav.notify(menu.what + " added to the queue") } }
    Menu {
        id: plMenu
        title: "Add to playlist"
        MenuItem { text: "New playlist…"; onTriggered: newDlg.open() }
        MenuSeparator {}
        Instantiator {
            model: userLib.playlists
            delegate: MenuItem {
                required property int id
                required property string name
                text: name
                onTriggered: { userLib.addPathsToPlaylist(id, menu.paths()); Nav.notify(menu.what + " added to “" + name + "”") }
            }
            onObjectAdded: (i, o) => plMenu.addItem(o)
            onObjectRemoved: (i, o) => plMenu.removeItem(o)
        }
    }
    MenuSeparator {}
    MenuItem {
        visible: menu.single
        height: visible ? implicitHeight : 0
        text: "Edit album info…"
        onTriggered: Nav.editAlbum(menu.keys[0])
    }
    MenuItem {
        visible: menu.single && menu.artist.length > 0
        height: visible ? implicitHeight : 0
        text: "Go to " + menu.artist
        onTriggered: Nav.openArtist(menu.artist)
    }
    MenuItem { objectName: "albumRemove"; text: "Remove from library…"; onTriggered: Nav.removeAlbums(menu.keys, menu.what) }
    MenuItem { objectName: "albumTrash"; text: "Move to trash…"; onTriggered: Nav.trashAlbums(menu.keys, menu.what) }

    Dialog {
        id: newDlg
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "New playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { nf.text = ""; nf.forceActiveFocus() }
        onAccepted: if (nf.text.trim().length) Nav.openPlaylist(userLib.addPathsToNewPlaylist(nf.text.trim(), menu.paths()))
        TextField { id: nf; width: 280; placeholderText: "Playlist name"; selectByMouse: true; onAccepted: newDlg.accept() }
    }
}
