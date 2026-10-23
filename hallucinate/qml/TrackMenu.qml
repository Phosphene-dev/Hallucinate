import QtQuick
import QtQuick.Controls
import "."

// Right-click (or "…") on a song anywhere: play and queue it, playlists, its album, artist and folder, tags,
// and taking it out of the library or moving it to the trash. Opened on a song that is part of a selection, it
// acts on the whole selection (and leaves out what only makes sense for one song).
Menu {
    id: menu
    objectName: "trackMenu"
    property string path: ""
    property string trackTitle: ""
    property string context: ""
    property int index: -1
    property var info: ({})
    property var paths: []
    readonly property bool single: paths.length <= 1
    // a radio station or a streamed episode: no tags, ratings, playlists or files to act on
    readonly property bool stream: paths.some(function (p) { return /^https?:\/\//.test(p) || podcasts.isEpisode(p) })
    // a song on a music server: no file here to show, edit or put in the trash
    readonly property bool onServer: paths.some(function (p) { return /^(subsonic|jellyfin):\/\//.test(p) })
    property var copies: ({ servers: 0, kept: 0, waiting: 0 })  // songs from a music server, kept here or not
    readonly property string what: single ? "“" + trackTitle + "”" : paths.length + " songs"

    function show(p, t, c, i) {
        path = p; trackTitle = t; context = c; index = i; paths = [p]
        info = /^https?:\/\//.test(p) || podcasts.isEpisode(p) ? ({}) : library.trackInfo(p)
        copies = serverCopies.status(paths)
        popup()
    }
    function showMany(list, c) {
        paths = list.slice(); path = list[0]; trackTitle = ""; context = c || ""; index = -1
        info = ({})
        copies = serverCopies.status(paths)
        popup()
    }
    function done(message) { if (!single) Selection.clear(); if (message) Nav.notify(message) }

    // Takes rows (by place) out of the playlist that's open, with Undo in the toast: they go back where they were.
    // Each removal is by the list as it is now, and the writes run in order, so the places stay right.
    function removeFromPlaylist(rows) {
        var pid = userLib.currentPlaylist
        var model = userLib.playlistTracks
        var n = model.count
        rows = rows.filter(function (i) { return i >= 0 && i < n }).sort(function (a, b) { return a - b })
        if (pid < 0 || !rows.length) return
        var removed = rows.map(function (i) { return model.get(i).path })
        rows.forEach(function (i) { userLib.removeFromPlaylist(i) })
        Nav.notifyAction(rows.length === 1 ? "Removed from the playlist" : rows.length + " songs removed from the playlist",
                         "Undo", function () {
            userLib.addPathsToPlaylist(pid, removed)  // back at the end...
            if (userLib.currentPlaylist !== pid) return
            var kept = n - rows.length  // ...then each to its old place, first to last
            rows.forEach(function (at, k) { userLib.moveInPlaylist(kept + k, at) })
        })
    }
    // the same, for songs picked by path (a selection): every row of the open playlist that holds one of them
    function removePathsFromPlaylist(list) {
        var model = userLib.playlistTracks
        var rows = []
        for (var i = 0; i < model.count; i++) if (list.indexOf(model.get(i).path) >= 0) rows.push(i)
        removeFromPlaylist(rows)
        Selection.clear()
    }

    Item {
        objectName: "menuRating"
        visible: menu.single && !menu.stream
        width: 220; height: visible ? 38 : 0
        Text {
            textFormat: Text.PlainText
            x: 14
            anchors.verticalCenter: parent.verticalCenter
            text: "Rating"
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(13)
        }
        StarRating {
            anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
            path: menu.path
            size: 17
        }
    }
    MenuSeparator { visible: menu.single && !menu.stream; height: visible ? implicitHeight : 0 }
    MenuItem {
        objectName: "trackCopyLink"
        visible: menu.stream && menu.single && /^https?:\/\//.test(menu.path)
        height: visible ? implicitHeight : 0
        text: "Copy stream link"; icon.name: "playlist"
        onTriggered: { shell.copyText(menu.path); Nav.notify("Stream link copied") }
    }
    MenuItem {
        visible: !menu.stream; height: visible ? implicitHeight : 0
        text: "Play"; icon.name: "play"; onTriggered: { userLib.playPaths(menu.paths); menu.done("") }
    }
    MenuItem {
        visible: !menu.stream; height: visible ? implicitHeight : 0
        text: "Play next"; icon.name: "next"
        onTriggered: { userLib.playNextPaths(menu.paths); menu.done(menu.single ? "" : menu.what + " will play next") }
    }
    MenuItem {
        visible: !menu.stream; height: visible ? implicitHeight : 0
        text: "Add to queue"; icon.name: "queue"
        onTriggered: { userLib.enqueuePaths(menu.paths); menu.done(menu.what + " added to the queue") }
    }
    MenuItem {
        readonly property bool liked: userLib.likesRevision >= 0 && userLib.allLiked(menu.paths)
        visible: !menu.stream && shell.features.liked !== false; height: visible ? implicitHeight : 0
        text: liked ? "Remove from Liked Songs" : "Add to Liked Songs"
        icon.name: "heart"
        onTriggered: { userLib.setLikedPaths(menu.paths, !liked); menu.done("") }
    }
    Menu {
        id: plMenu
        title: "Add to playlist"
        icon.name: "playlist"
        enabled: !menu.stream
        MenuItem { text: "New playlist…"; icon.name: "plus"; onTriggered: newDlg.open() }
        MenuSeparator {}
        Instantiator {
            model: userLib.playlists
            delegate: MenuItem {
                required property int id
                required property string name
                text: Theme.plain(name)
                onTriggered: { userLib.addPathsToPlaylist(id, menu.paths); menu.done(menu.what + " added to “" + name + "”") }
            }
            onObjectAdded: (i, o) => plMenu.addItem(o)
            onObjectRemoved: (i, o) => plMenu.removeItem(o)
        }
    }
    MenuSeparator { visible: !menu.stream; height: visible ? implicitHeight : 0 }
    MenuItem {
        visible: menu.single && (menu.info.album_key || "").length > 0 && menu.context !== "album"
        height: visible ? implicitHeight : 0
        text: "Go to album"
        icon.name: "album"
        onTriggered: Nav.openAlbum(menu.info.album_key)
    }
    MenuItem {
        id: goArtistItem
        // on an artist's page it'd lead back there, unless the song is on someone else's record (a feature)
        readonly property bool ownRecord: !menu.info.album_artist || menu.info.album_artist === menu.info.artist
        visible: menu.single && (menu.info.album_artist || menu.info.artist || "").length > 0
                 && !(menu.context === "artist" && ownRecord)
        height: visible ? implicitHeight : 0
        text: "Go to " + Theme.plain(menu.info.album_artist || menu.info.artist || "")
        icon.name: "artist"
        onTriggered: Nav.openArtist(menu.info.album_artist || menu.info.artist)
    }
    // the song's genres, each to its page (up to three)
    readonly property var genreNames: menu.single ? String(menu.info.genre || "").split(/\s*[;\/|]\s*/)
                                                    .filter(function (g) { return g.length > 0 }).slice(0, 3) : []
    Instantiator {
        model: menu.genreNames
        MenuItem {
            required property string modelData
            objectName: "trackGenre_" + modelData
            text: "Go to genre " + Theme.plain(modelData)
            icon.name: "note"
            onTriggered: Nav.openGenre(modelData)
        }
        onObjectAdded: function (i, o) {
            var at = 0
            for (var k = 0; k < menu.count; k++) if (menu.itemAt(k) === goArtistItem) at = k + 1
            menu.insertItem(at + i, o)
        }
        onObjectRemoved: (i, o) => menu.removeItem(o)
    }
    // who wrote it (the first composer it credits)
    readonly property string composerName: menu.single ? String(menu.info.composer || "").split(/\s*[;|]\s*/)[0] : ""
    MenuItem {
        objectName: "trackComposer"
        visible: menu.composerName.length > 0 && menu.context !== "composer"
        height: visible ? implicitHeight : 0
        text: "Go to composer " + Theme.plain(menu.composerName)
        icon.name: "note"
        onTriggered: Nav.openComposer(menu.composerName)
    }
    MenuItem {
        objectName: "trackKeep"
        visible: menu.copies.servers > 0 && menu.copies.kept + menu.copies.waiting < menu.copies.servers
        height: visible ? implicitHeight : 0
        text: "Keep on this computer"; icon.name: "download"
        onTriggered: serverCopies.keep(menu.paths)
    }
    MenuItem {
        objectName: "trackUnkeep"
        visible: menu.copies.kept + menu.copies.waiting > 0
        height: visible ? implicitHeight : 0
        text: menu.copies.waiting > 0 && menu.copies.kept === 0 ? "Stop keeping on this computer" : "Remove the copies from this computer"
        icon.name: "remove"
        onTriggered: serverCopies.remove(menu.paths)
    }
    MenuItem {
        objectName: "trackShowInFolder"
        visible: menu.single && !menu.stream && !menu.onServer
        height: visible ? implicitHeight : 0
        enabled: menu.info.exists === true
        text: "Show in folder"
        icon.name: "folder"
        onTriggered: library.showInFolder(menu.path)
    }
    MenuItem {
        visible: !menu.stream; height: visible ? implicitHeight : 0
        text: "Edit tags…"
        icon.name: "edit"
        // CUE sheet songs are edited in the .cue file, and a server's songs on the server
        enabled: !menu.onServer && menu.paths.every(function (p) { return !/\.[A-Za-z0-9]+#\d+$/.test(p) })
        onTriggered: menu.single ? Nav.editTags(menu.path) : Nav.editTagsMany(menu.paths)
    }
    MenuItem {
        objectName: "trackRemoveFromQueue"
        visible: menu.single && menu.context === "queue"
        height: visible ? implicitHeight : 0
        text: "Remove from the queue"
        icon.name: "close"
        onTriggered: { player.removeAt(menu.index); Nav.notifyAction("Removed from the queue", "Undo", function () { player.undoQueue() }) }
    }
    MenuItem {
        objectName: "trackRemoveFromPlaylist"
        visible: menu.context === "playlist"
        height: visible ? implicitHeight : 0
        text: "Remove from this playlist"
        icon.name: "remove"
        icon.color: Theme.error
        onTriggered: menu.single ? menu.removeFromPlaylist([menu.index]) : menu.removePathsFromPlaylist(menu.paths)
    }
    MenuSeparator { visible: !menu.stream; height: visible ? implicitHeight : 0 }
    MenuItem {
        objectName: "trackRemove"
        visible: !menu.stream; height: visible ? implicitHeight : 0
        text: "Remove from library…"; icon.name: "remove"; icon.color: Theme.error
        onTriggered: Nav.removeSongs(menu.paths, menu.what)
    }
    MenuItem {
        objectName: "trackTrash"
        visible: !menu.stream && !menu.onServer; height: visible ? implicitHeight : 0
        text: "Move to trash…"; icon.name: "trash"; icon.color: Theme.error
        enabled: !menu.single || menu.info.exists === true
        onTriggered: Nav.trashSongs(menu.paths, menu.what)
    }

    Dialog {
        id: newDlg
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "New playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { nf.text = ""; nf.forceActiveFocus() }
        onAccepted: if (nf.text.trim().length) { Nav.openPlaylist(userLib.addPathsToNewPlaylist(nf.text.trim(), menu.paths)); menu.done("") }
        TextField {
            id: nf; width: 280; placeholderText: "Playlist name"; selectByMouse: true
            onAccepted: if (text.trim().length) newDlg.accept()  // no nameless playlists
            onTextChanged: { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
}
