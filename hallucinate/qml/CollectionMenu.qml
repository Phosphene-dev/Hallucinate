import QtQuick
import QtQuick.Controls
import "."

// Right-click on an artist (cards, lists, links), a folder or a genre: play or shuffle everything, queue it, add it
// to a playlist, go to it, and (artists and folders) take its songs out of the library or move them to the trash.
Menu {
    id: menu
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
    function showNow() { copies = serverCopies.status(paths()); popup() }
    function showArtist(n) { kind = "artist"; name = n; path = ""; showNow() }
    function showFolder(p, n) { kind = "folder"; path = p; name = n || p.split("/").pop(); copies = ({ servers: 0, kept: 0, waiting: 0 }); popup() }
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
    function songCount(list) { return list.length + (list.length === 1 ? " song" : " songs") }

    MenuItem { text: "Play"; icon.name: "play"; onTriggered: menu.play(false) }
    MenuItem { text: "Shuffle"; icon.name: "shuffle"; onTriggered: menu.play(true) }
    MenuItem {
        visible: menu.artist
        height: visible ? implicitHeight : 0
        text: "Start radio"; icon.name: "radio"
        onTriggered: library.startArtistRadio(menu.name)
    }
    MenuItem { text: "Play next"; icon.name: "next"; onTriggered: { var p = menu.paths(); userLib.playNextPaths(p); Nav.notify(menu.songCount(p) + " will play next") } }
    MenuItem { text: "Add to queue"; icon.name: "queue"; onTriggered: { var p = menu.paths(); userLib.enqueuePaths(p); Nav.notify(menu.songCount(p) + " added to the queue") } }
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
                onTriggered: { var p = menu.paths(); userLib.addPathsToPlaylist(id, p); Nav.notify(menu.songCount(p) + " added to “" + name + "”") }
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
        objectName: "collectionGoToGenre"
        visible: menu.genre
        height: visible ? implicitHeight : 0
        text: "Go to genre " + Theme.plain(menu.name); icon.name: "note"
        onTriggered: Nav.openGenre(menu.name)
    }
    MenuItem {
        objectName: "collectionGoToComposer"
        visible: menu.composer
        height: visible ? implicitHeight : 0
        text: "Go to composer " + Theme.plain(menu.name); icon.name: "note"
        onTriggered: Nav.openComposer(menu.name)
    }
    MenuItem {
        objectName: "collectionRenameGenre"
        visible: menu.genre
        height: visible ? implicitHeight : 0
        text: "Rename genre…"; icon.name: "edit"
        onTriggered: renameDlg.open()
    }
    MenuItem {
        visible: menu.kind === "folder"
        height: visible ? implicitHeight : 0
        text: "Show in file manager"; icon.name: "folder"
        onTriggered: library.showInFolder(menu.path)
    }
    MenuItem {
        objectName: "collectionKeep"
        visible: menu.copies.servers > 0 && menu.copies.kept + menu.copies.waiting < menu.copies.servers
        height: visible ? implicitHeight : 0
        text: "Keep on this computer"; icon.name: "download"
        onTriggered: serverCopies.keep(menu.paths())
    }
    MenuItem {
        objectName: "collectionUnkeep"
        visible: menu.copies.kept + menu.copies.waiting > 0
        height: visible ? implicitHeight : 0
        text: "Remove the copies from this computer"; icon.name: "remove"
        onTriggered: serverCopies.remove(menu.paths())
    }
    MenuSeparator { visible: !menu.genre && !menu.composer; height: visible ? implicitHeight : 0 }
    // (not for a genre: its songs are spread over the whole library, too much to remove from one click)
    MenuItem {
        objectName: "collectionRemove"
        visible: !menu.genre && !menu.composer
        height: visible ? implicitHeight : 0
        text: "Remove from library…"; icon.name: "remove"; icon.color: Theme.error
        onTriggered: Nav.removeSongs(menu.paths(), menu.what)
    }
    MenuItem {
        objectName: "collectionTrash"
        visible: !menu.genre && !menu.composer
        height: visible ? implicitHeight : 0
        text: "Move to trash…"; icon.name: "trash"; icon.color: Theme.error
        onTriggered: Nav.trashSongs(menu.paths(), menu.what)
    }

    // A genre's new name, written to every song that has it. A name you already use joins the two.
    Dialog {
        id: renameDlg
        objectName: "renameGenreDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "Rename “" + Theme.plain(menu.name) + "”"
        standardButtons: Dialog.Ok | Dialog.Cancel
        readonly property string newName: rf.text.trim()
        readonly property bool joins: newName.length > 0 && newName.toLowerCase() !== menu.name.toLowerCase()
                                      && library.genreList.some(function (g) { return g.name.toLowerCase() === renameDlg.newName.toLowerCase() })
        onOpened: { rf.text = menu.name; rf.selectAll(); rf.forceActiveFocus() }
        onAccepted: {
            if (!newName.length || newName === menu.name) return
            metaEditor.renameGenre(menu.name, newName)
            Nav.notify("Renaming " + menu.name + " to " + newName + " in its songs…")
            menu.genreRenamed(menu.name, newName)
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
        onAccepted: if (nf.text.trim().length) Nav.openPlaylist(userLib.addPathsToNewPlaylist(nf.text.trim(), menu.paths()))
        TextField {
            id: nf; width: 280; placeholderText: "Playlist name"; selectByMouse: true
            onAccepted: if (text.trim().length) newDlg.accept()  // no nameless playlists
            onTextChanged: { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
}
