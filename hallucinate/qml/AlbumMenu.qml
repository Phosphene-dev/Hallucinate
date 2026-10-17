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

    MenuItem { text: "Play"; icon.name: "play"; onTriggered: menu.single ? library.playAlbum(menu.keys[0], 0) : userLib.playPaths(menu.paths()) }
    MenuItem { text: "Play next"; icon.name: "next"; onTriggered: { userLib.playNextPaths(menu.paths()); Nav.notify(menu.what + " will play next") } }
    MenuItem { text: "Add to queue"; icon.name: "queue"; onTriggered: { userLib.enqueuePaths(menu.paths()); Nav.notify(menu.what + " added to the queue") } }
    Menu {
        id: plMenu
        title: "Add to playlist"
        icon.name: "playlist"
        MenuItem { text: "New playlist…"; icon.name: "plus"; onTriggered: newDlg.open() }
        MenuSeparator {}
        Instantiator {
            model: userLib.playlists
            delegate: MenuItem {
                required property int id
                required property string name
                text: Theme.plain(name)
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
        icon.name: "edit"
        onTriggered: Nav.editAlbum(menu.keys[0])
    }
    MenuItem {
        visible: menu.single && menu.artist.length > 0
        height: visible ? implicitHeight : 0
        text: "Go to " + Theme.plain(menu.artist)
        icon.name: "artist"
        onTriggered: Nav.openArtist(menu.artist)
    }
    MenuSeparator {}
    MenuItem { objectName: "albumRemove"; text: "Remove from library…"; icon.name: "remove"; icon.color: Theme.error; onTriggered: Nav.removeAlbums(menu.keys, menu.what) }
    MenuItem { objectName: "albumTrash"; text: "Move to trash…"; icon.name: "trash"; icon.color: Theme.error; onTriggered: Nav.trashAlbums(menu.keys, menu.what) }

    Dialog {
        id: newDlg
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "New playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { nf.text = ""; nf.forceActiveFocus() }
        onAccepted: if (nf.text.trim().length) Nav.openPlaylist(userLib.addPathsToNewPlaylist(nf.text.trim(), menu.paths()))
        TextField {
            id: nf; width: 280; placeholderText: "Playlist name"; selectByMouse: true
            onAccepted: if (text.trim().length) newDlg.accept()  // no nameless playlists
            onTextChanged: { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
}
