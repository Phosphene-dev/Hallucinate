import QtQuick
import QtQuick.Controls
import "."

// Right-click (or "…") on an album, or on a selection of albums: play or shuffle, queue, playlists, likes, its
// folder and genre, tags, remove.
Menu {
    id: albumMenu  // not "menu": a MenuItem's own `menu` (its submenu) would hide it in the playlist items
    objectName: "albumMenu"
    property var keys: []
    property string albumTitle: ""
    property string artist: ""
    readonly property bool single: keys.length === 1
    readonly property string what: single ? "“" + albumTitle + "”" : keys.length + " albums"

    // Read when the menu opens: whether every song is liked already, the first song (for its folder), the genre
    property bool allLiked: false
    property string firstPath: ""
    property string genre: ""
    property var copies: ({ servers: 0, kept: 0, waiting: 0 })  // its songs from a music server, kept here or not
    readonly property bool onServer: /^(subsonic|jellyfin):\/\//.test(firstPath)

    // keys: the album keys to act on (the clicked album, or the whole selection when it was part of it)
    function show(k, title, art) {
        keys = k; albumTitle = title; artist = art
        var p = paths()
        allLiked = userLib.allLiked(p)
        firstPath = p.length ? p[0] : ""
        genre = single ? ((library.albumNotes(k[0]) || {}).genres || [])[0] || "" : ""
        copies = serverCopies.status(p)
        popup()
    }
    function paths() { return library.albumPaths(albumMenu.keys) }
    // every song in a random order, with shuffle on so it carries on that way
    function shuffle() {
        var p = paths()
        for (var i = p.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = p[i]; p[i] = p[j]; p[j] = t }
        player.setShuffle(true)
        userLib.playPaths(p)
    }

    MenuItem { text: "Play"; icon.name: "play"; onTriggered: albumMenu.single ? library.playAlbum(albumMenu.keys[0], 0) : userLib.playPaths(albumMenu.paths()) }
    MenuItem { objectName: "albumShuffle"; text: "Shuffle"; icon.name: "shuffle"; onTriggered: albumMenu.shuffle() }
    MenuItem { text: "Play next"; icon.name: "next"; onTriggered: { userLib.playNextPaths(albumMenu.paths()); Nav.notify(albumMenu.what + " will play next") } }
    MenuItem { text: "Add to queue"; icon.name: "queue"; onTriggered: { userLib.enqueuePaths(albumMenu.paths()); Nav.notify(albumMenu.what + " added to the queue") } }
    Menu {
        id: plMenu
        objectName: "addToPlaylistMenu"
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
                onTriggered: { userLib.addPathsToPlaylist(id, albumMenu.paths()); Nav.notify(albumMenu.what + " added to “" + name + "”") }
            }
            onObjectAdded: (i, o) => plMenu.addItem(o)
            onObjectRemoved: (i, o) => plMenu.removeItem(o)
        }
    }
    MenuItem {
        objectName: "albumLikeAll"
        visible: shell.features.liked !== false
        height: visible ? implicitHeight : 0
        text: albumMenu.allLiked ? "Unlike all songs" : "Like all songs"
        icon.name: "heart"
        onTriggered: {
            var p = albumMenu.paths()
            userLib.setLikedPaths(p, !albumMenu.allLiked)
            Nav.notify((albumMenu.allLiked ? "Unliked" : "Liked") + " every song on " + albumMenu.what)
        }
    }
    MenuSeparator {}
    MenuItem {
        visible: albumMenu.single
        height: visible ? implicitHeight : 0
        text: "Edit album info…"
        icon.name: "edit"
        onTriggered: Nav.editAlbum(albumMenu.keys[0])
    }
    MenuItem {
        visible: albumMenu.single && albumMenu.artist.length > 0
        height: visible ? implicitHeight : 0
        text: "Go to " + Theme.plain(albumMenu.artist)
        icon.name: "artist"
        onTriggered: Nav.openArtist(albumMenu.artist)
    }
    MenuItem {
        objectName: "albumGoToGenre"
        visible: albumMenu.single && albumMenu.genre.length > 0
        height: visible ? implicitHeight : 0
        text: "Go to genre " + Theme.plain(albumMenu.genre)
        icon.name: "note"
        onTriggered: Nav.openGenre(albumMenu.genre)
    }
    MenuItem {
        objectName: "albumShowInFolder"
        visible: albumMenu.single && albumMenu.firstPath.length > 0 && !albumMenu.onServer
        height: visible ? implicitHeight : 0
        text: "Show in folder"
        icon.name: "folder"
        onTriggered: library.showInFolder(albumMenu.firstPath)
    }
    MenuItem {
        objectName: "albumKeep"
        visible: albumMenu.copies.servers > 0 && albumMenu.copies.kept + albumMenu.copies.waiting < albumMenu.copies.servers
        height: visible ? implicitHeight : 0
        text: "Keep on this computer"; icon.name: "download"
        onTriggered: serverCopies.keep(albumMenu.paths())
    }
    MenuItem {
        objectName: "albumUnkeep"
        visible: albumMenu.copies.kept + albumMenu.copies.waiting > 0
        height: visible ? implicitHeight : 0
        text: albumMenu.copies.waiting > 0 && albumMenu.copies.kept === 0 ? "Stop keeping on this computer" : "Remove the copies from this computer"
        icon.name: "remove"
        onTriggered: serverCopies.remove(albumMenu.paths())
    }
    MenuSeparator {}
    MenuItem { objectName: "albumRemove"; text: "Remove from library…"; icon.name: "remove"; icon.color: Theme.error; onTriggered: Nav.removeAlbums(albumMenu.keys, albumMenu.what) }
    MenuItem { objectName: "albumTrash"; text: "Move to trash…"; icon.name: "trash"; icon.color: Theme.error; onTriggered: Nav.trashAlbums(albumMenu.keys, albumMenu.what) }

    Dialog {
        id: newDlg
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "New playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { nf.text = ""; nf.forceActiveFocus() }
        onAccepted: if (nf.text.trim().length) Nav.openPlaylist(userLib.addPathsToNewPlaylist(nf.text.trim(), albumMenu.paths()))
        TextField {
            id: nf; implicitWidth: 280; placeholderText: "Playlist name"; selectByMouse: true
            onAccepted: if (text.trim().length) newDlg.accept()  // no nameless playlists
            onTextChanged: { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
}
