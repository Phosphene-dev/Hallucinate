import QtQuick
import QtQuick.Controls
import "."

// Right-click on an artist (cards, lists, links) or a folder: play or shuffle everything, queue it, add it to a
// playlist, go to it, and take its songs out of the library or move them to the trash.
Menu {
    id: menu
    objectName: "collectionMenu"
    property string kind: "artist"  // or "folder"
    property string name: ""        // the artist, or the folder's name
    property string path: ""        // the folder
    readonly property bool artist: kind === "artist"
    readonly property string what: artist ? "Every song by " + name : "Everything in “" + name + "”"

    function showArtist(n) { kind = "artist"; name = n; path = ""; popup() }
    function showFolder(p, n) { kind = "folder"; path = p; name = n || p.split("/").pop(); popup() }
    function paths() { return artist ? library.artistPaths(name) : library.folderPaths(path) }
    function count(list) { return list.length + (list.length === 1 ? " song" : " songs") }

    MenuItem { text: "Play"; icon.name: "play"; onTriggered: menu.artist ? library.playArtist(menu.name, false) : library.playFolder(menu.path, false) }
    MenuItem { text: "Shuffle"; icon.name: "shuffle"; onTriggered: menu.artist ? library.playArtist(menu.name, true) : library.playFolder(menu.path, true) }
    MenuItem {
        visible: menu.artist
        height: visible ? implicitHeight : 0
        text: "Start radio"; icon.name: "radio"
        onTriggered: library.startArtistRadio(menu.name)
    }
    MenuItem { text: "Play next"; icon.name: "next"; onTriggered: { var p = menu.paths(); userLib.playNextPaths(p); Nav.notify(menu.count(p) + " will play next") } }
    MenuItem { text: "Add to queue"; icon.name: "queue"; onTriggered: { var p = menu.paths(); userLib.enqueuePaths(p); Nav.notify(menu.count(p) + " added to the queue") } }
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
                onTriggered: { var p = menu.paths(); userLib.addPathsToPlaylist(id, p); Nav.notify(menu.count(p) + " added to “" + name + "”") }
            }
            onObjectAdded: (i, o) => plMenu.addItem(o)
            onObjectRemoved: (i, o) => plMenu.removeItem(o)
        }
    }
    MenuSeparator {}
    MenuItem {
        visible: menu.artist
        height: visible ? implicitHeight : 0
        text: "Go to " + Theme.plain(menu.name); icon.name: "artist"
        onTriggered: Nav.openArtist(menu.name)
    }
    MenuItem {
        visible: !menu.artist
        height: visible ? implicitHeight : 0
        text: "Show in file manager"; icon.name: "folder"
        onTriggered: library.showInFolder(menu.path)
    }
    MenuSeparator {}
    MenuItem {
        objectName: "collectionRemove"
        text: "Remove from library…"; icon.name: "remove"; icon.color: Theme.error
        onTriggered: Nav.removeSongs(menu.paths(), menu.what)
    }
    MenuItem {
        objectName: "collectionTrash"
        text: "Move to trash…"; icon.name: "trash"; icon.color: Theme.error
        onTriggered: Nav.trashSongs(menu.paths(), menu.what)
    }

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
