import QtQuick
import QtQuick.Controls
import "."

// Right-click on an artist (cards, lists, links), a folder or a genre: play or shuffle everything, queue it, add it
// to a playlist, go to it, and (artists and folders) take its songs out of the library or move them to the trash.
Menu {
    id: collectionMenu  // not "menu": a MenuItem's own `menu` (its submenu) would hide it in the playlist items
    objectName: "collectionMenu"
    property string kind: "artist"  // or "folder", "genre" or "composer"
    property string name: ""        // the artist, the folder's name or the genre
    property string path: ""        // the folder
    readonly property bool artist: kind === "artist"
    readonly property bool genre: kind === "genre"
    readonly property bool composer: kind === "composer"
    readonly property string what: artist ? "Every song by " + name : genre ? "Every " + name + " song"
                                 : composer ? "Every song " + name + " wrote"
                                                                          : "Everything in “" + name + "”"

    property var copies: ({ servers: 0, kept: 0, waiting: 0 })  // songs from a music server, kept here or not
    function showNow() { if (ofSelection()) return; copies = serverCopies.status(paths()); popup() }
    // on one of several things selected, the menu is the selection's (every song of all of them)
    function ofSelection() {
        if (Selection.count < 2 || !Selection.has(kind, kind === "folder" ? path : name)) return false
        Nav.selectionMenu()
        return true
    }
    function showArtist(n) { kind = "artist"; name = n; path = ""; showNow() }
    function showFolder(p, n) {
        kind = "folder"; path = p; name = n || p.split("/").pop()
        if (ofSelection()) return
        copies = ({ servers: 0, kept: 0, waiting: 0 }); popup()
    }
    function showGenre(n) { kind = "genre"; name = n; path = ""; showNow() }
    function showComposer(n) { kind = "composer"; name = n; path = ""; showNow() }
    signal genreRenamed(string oldName, string newName)  // its songs are being retagged
    function paths() {
        return artist ? library.artistPaths(name) : genre ? library.genrePaths(name)
             : composer ? library.composerPaths(name) : library.folderPaths(path)
    }
    function play(shuffle) {
        if (artist) library.playArtist(name, shuffle)
        else if (genre) { if (shuffle) player.setShuffle(true); library.playGenre(name, shuffle) }
        else if (composer) { if (shuffle) player.setShuffle(true); library.playComposer(name, shuffle) }
        else library.playFolder(path, shuffle)
    }
    function songCount(list) { return Theme.num(list.length) + (list.length === 1 ? " song" : " songs") }

    MenuItem { text: "Play"; icon.name: "play"; onTriggered: collectionMenu.play(false) }
    MenuItem { text: "Shuffle"; icon.name: "shuffle"; onTriggered: collectionMenu.play(true) }
    MenuItem {
        visible: collectionMenu.artist
        height: visible ? implicitHeight : 0
        text: "Start radio"; icon.name: "radio"
        onTriggered: library.startArtistRadio(collectionMenu.name)
    }
    MenuItem { text: "Play next"; icon.name: "next"; onTriggered: { var p = collectionMenu.paths(); userLib.playNextPaths(p); Nav.notify(collectionMenu.songCount(p) + " will play next") } }
    MenuItem { text: "Add to queue"; icon.name: "queue"; onTriggered: { var p = collectionMenu.paths(); userLib.enqueuePaths(p); Nav.notify(collectionMenu.songCount(p) + " added to the queue") } }
    Menu {
        id: plMenu
        objectName: "addToPlaylistMenu"
        title: "Add to playlist"
        icon.name: "playlist"
        // which playlists already hold these songs: ticked, and a click takes them out (issue 101)
        property var held: ({})
        property var heldPaths: []
        onAboutToShow: {
            heldPaths = collectionMenu.paths()
            held = userLib.playlistCounts(heldPaths)
            for (var i = 0; i < count; i++) { var it = itemAt(i); if (it && it.have !== undefined) it.checked = it.full }
        }
        MenuItem { text: "New playlist…"; icon.name: "plus"; onTriggered: newDlg.open() }
        MenuSeparator {}
        Instantiator {
            model: userLib.playlists
            delegate: MenuItem {
                required property int id
                required property string name
                readonly property int have: plMenu.held[String(id)] || 0
                readonly property bool full: have > 0 && have >= plMenu.heldPaths.length
                checkable: true
                text: Theme.plain(name) + (have > 0 && !full ? "  (" + Theme.num(have) + " of " + plMenu.heldPaths.length + ")" : "")
                onTriggered: full ? Nav.removeFromPlaylistId(id, name, collectionMenu.paths(), "")
                                  : Nav.addToPlaylist(id, name, collectionMenu.paths(), "")
            }
            onObjectAdded: (i, o) => plMenu.addItem(o)
            onObjectRemoved: (i, o) => plMenu.removeItem(o)
        }
    }
    MenuSeparator {}
    MenuItem {
        visible: collectionMenu.artist
        height: visible ? implicitHeight : 0
        text: "Go to " + Theme.plain(collectionMenu.name); icon.name: "artist"
        onTriggered: Nav.openArtist(collectionMenu.name)
    }
    MenuItem {
        objectName: "collectionGoToGenre"
        visible: collectionMenu.genre
        height: visible ? implicitHeight : 0
        text: "Go to genre " + Theme.plain(collectionMenu.name); icon.name: "note"
        onTriggered: Nav.openGenre(collectionMenu.name)
    }
    MenuItem {
        objectName: "collectionGoToComposer"
        visible: collectionMenu.composer
        height: visible ? implicitHeight : 0
        text: "Go to composer " + Theme.plain(collectionMenu.name); icon.name: "note"
        onTriggered: Nav.openComposer(collectionMenu.name)
    }
    MenuItem {
        objectName: "collectionRenameGenre"
        visible: collectionMenu.genre
        height: visible ? implicitHeight : 0
        text: "Rename genre…"; icon.name: "edit"
        onTriggered: renameDlg.open()
    }
    MenuItem {
        visible: collectionMenu.kind === "folder"
        height: visible ? implicitHeight : 0
        text: "Show in file manager"; icon.name: "folder"
        onTriggered: library.showInFolder(collectionMenu.path)
    }
    MenuItem {
        objectName: "collectionKeep"
        visible: collectionMenu.copies.servers > 0 && collectionMenu.copies.kept + collectionMenu.copies.waiting < collectionMenu.copies.servers
        height: visible ? implicitHeight : 0
        text: "Keep on this computer"; icon.name: "download"
        onTriggered: serverCopies.keep(collectionMenu.paths())
    }
    MenuItem {
        objectName: "collectionUnkeep"
        visible: collectionMenu.copies.kept + collectionMenu.copies.waiting > 0
        height: visible ? implicitHeight : 0
        text: "Remove the copies from this computer"; icon.name: "remove"
        onTriggered: serverCopies.remove(collectionMenu.paths())
    }
    MenuSeparator { visible: !collectionMenu.genre && !collectionMenu.composer; height: visible ? implicitHeight : 0 }
    // (not for a genre: its songs are spread over the whole library, too much to remove from one click)
    MenuItem {
        objectName: "collectionRemove"
        visible: !collectionMenu.genre && !collectionMenu.composer
        height: visible ? implicitHeight : 0
        text: "Remove from library…"; icon.name: "remove"; icon.color: Theme.error
        onTriggered: Nav.removeSongs(collectionMenu.paths(), collectionMenu.what)
    }
    MenuItem {
        objectName: "collectionTrash"
        visible: !collectionMenu.genre && !collectionMenu.composer
        height: visible ? implicitHeight : 0
        text: "Move to trash…"; icon.name: "trash"; icon.color: Theme.error
        onTriggered: Nav.trashSongs(collectionMenu.paths(), collectionMenu.what)
    }

    // A genre's new name, written to every song that has it. A name you already use joins the two.
    Dialog {
        id: renameDlg
        objectName: "renameGenreDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "Rename “" + Theme.plain(collectionMenu.name) + "”"
        standardButtons: Dialog.Ok | Dialog.Cancel
        readonly property string newName: rf.text.trim()
        readonly property bool joins: newName.length > 0 && newName.toLowerCase() !== collectionMenu.name.toLowerCase()
                                      && library.genreList.some(function (g) { return g.name.toLowerCase() === renameDlg.newName.toLowerCase() })
        onOpened: { rf.text = collectionMenu.name; rf.selectAll(); rf.forceActiveFocus() }
        onAccepted: {
            if (!newName.length || newName === collectionMenu.name) return
            metaEditor.renameGenre(collectionMenu.name, newName)
            Nav.notify("Renaming " + collectionMenu.name + " to " + newName + " in its songs…")
            collectionMenu.genreRenamed(collectionMenu.name, newName)
        }
        Column {
            spacing: 10
            width: 320
            TextField {
                id: rf; width: parent.width; placeholderText: "Genre name"; selectByMouse: true
                onAccepted: if (text.trim().length) renameDlg.accept()
                onTextChanged: { var b = renameDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.Wrap
                text: renameDlg.joins ? "You already have " + renameDlg.newName + ": the two become one genre."
                                      : "Written to the tags of every song with this genre."
                color: renameDlg.joins ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(12.5)
            }
        }
    }

    Dialog {
        id: newDlg
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "New playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { nf.text = ""; nf.forceActiveFocus() }
        onAccepted: if (nf.text.trim().length) Nav.openPlaylist(userLib.addPathsToNewPlaylist(nf.text.trim(), collectionMenu.paths()))
        TextField {
            id: nf; implicitWidth: 280; placeholderText: "Playlist name"; selectByMouse: true
            onAccepted: if (text.trim().length) newDlg.accept()  // no nameless playlists
            onTextChanged: { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
}
