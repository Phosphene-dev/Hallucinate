import QtQuick
import QtQuick.Controls
import "."

// Right-click (or "…") on a song anywhere: play and queue it, playlists, its album, artist and folder, tags,
// and taking it out of the library or moving it to the trash. Opened on a song that is part of a selection, it
// acts on the whole selection (and leaves out what only makes sense for one song).
Menu {
    id: songMenu  // not "menu": a MenuItem's own `menu` (its submenu) would hide it in the playlist items
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
    readonly property string what: single ? "“" + trackTitle + "”" : Theme.num(paths.length) + " songs"

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
        Nav.notifyAction(rows.length === 1 ? "Removed from the playlist" : Theme.num(rows.length) + " songs removed from the playlist",
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
        visible: songMenu.single && !songMenu.stream
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
            path: songMenu.path
            size: 17
        }
    }
    MenuSeparator { visible: songMenu.single && !songMenu.stream; height: visible ? implicitHeight : 0 }
    MenuItem {
        objectName: "trackCopyLink"
        visible: songMenu.stream && songMenu.single && /^https?:\/\//.test(songMenu.path)
        height: visible ? implicitHeight : 0
        text: "Copy stream link"; icon.name: "playlist"
        onTriggered: { shell.copyText(songMenu.path); Nav.notify("Stream link copied") }
    }
    MenuItem {
        visible: !songMenu.stream; height: visible ? implicitHeight : 0
        text: "Play"; icon.name: "play"; onTriggered: { userLib.playPaths(songMenu.paths); songMenu.done("") }
    }
    MenuItem {
        visible: !songMenu.stream; height: visible ? implicitHeight : 0
        text: "Play next"; icon.name: "next"
        onTriggered: { userLib.playNextPaths(songMenu.paths); songMenu.done(songMenu.single ? "" : songMenu.what + " will play next") }
    }
    MenuItem {
        visible: !songMenu.stream; height: visible ? implicitHeight : 0
        text: "Add to queue"; icon.name: "queue"
        onTriggered: { userLib.enqueuePaths(songMenu.paths); songMenu.done(songMenu.what + " added to the queue") }
    }
    MenuItem {
        readonly property bool liked: userLib.likesRevision >= 0 && userLib.allLiked(songMenu.paths)
        visible: !songMenu.stream && shell.features.liked !== false; height: visible ? implicitHeight : 0
        text: liked ? "Remove from Liked Songs" : "Add to Liked Songs"
        icon.name: "heart"
        onTriggered: { userLib.setLikedPaths(songMenu.paths, !liked); songMenu.done("") }
    }
    Menu {
        id: plMenu
        objectName: "addToPlaylistMenu"
        title: "Add to playlist"
        icon.name: "playlist"
        enabled: !songMenu.stream
        // which playlists already hold the song(s): ticked, and a click takes them out (issue 101)
        property var held: ({})
        onAboutToShow: {
            held = userLib.playlistCounts(songMenu.paths)
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
                readonly property bool full: have > 0 && have >= songMenu.paths.length
                checkable: true
                text: Theme.plain(name) + (have > 0 && !full ? "  (" + Theme.num(have) + " of " + songMenu.paths.length + ")" : "")
                onTriggered: {
                    var p = songMenu.paths.slice(), w = songMenu.what
                    songMenu.done("")
                    if (full) Nav.removeFromPlaylistId(id, name, p, w)
                    else Nav.addToPlaylist(id, name, p, w)
                }
            }
            onObjectAdded: (i, o) => plMenu.addItem(o)
            onObjectRemoved: (i, o) => plMenu.removeItem(o)
        }
    }
    MenuSeparator { visible: !songMenu.stream; height: visible ? implicitHeight : 0 }
    MenuItem {
        visible: songMenu.single && (songMenu.info.album_key || "").length > 0 && songMenu.context !== "album"
        height: visible ? implicitHeight : 0
        text: "Go to album"
        icon.name: "album"
        onTriggered: Nav.openAlbum(songMenu.info.album_key)
    }
    MenuItem {
        id: goArtistItem
        // on an artist's page it'd lead back there, unless the song is on someone else's record (a feature)
        readonly property bool ownRecord: !songMenu.info.album_artist || songMenu.info.album_artist === songMenu.info.artist
        visible: songMenu.single && (songMenu.info.album_artist || songMenu.info.artist || "").length > 0
                 && !(songMenu.context === "artist" && ownRecord)
        height: visible ? implicitHeight : 0
        text: "Go to " + Theme.plain(songMenu.info.album_artist || songMenu.info.artist || "")
        icon.name: "artist"
        onTriggered: Nav.openArtist(songMenu.info.album_artist || songMenu.info.artist)
    }
    // the song's genres, each to its page (up to three)
    readonly property var genreNames: songMenu.single ? String(songMenu.info.genre || "").split(/\s*[;\/|]\s*/)
                                                    .filter(function (g) { return g.length > 0 }).slice(0, 3) : []
    Instantiator {
        model: songMenu.genreNames
        MenuItem {
            required property string modelData
            objectName: "trackGenre_" + modelData
            text: "Go to genre " + Theme.plain(modelData)
            icon.name: "note"
            onTriggered: Nav.openGenre(modelData)
        }
        onObjectAdded: function (i, o) {
            var at = 0
            for (var k = 0; k < songMenu.count; k++) if (songMenu.itemAt(k) === goArtistItem) at = k + 1
            songMenu.insertItem(at + i, o)
        }
        onObjectRemoved: (i, o) => songMenu.removeItem(o)
    }
    // who wrote it (the first composer it credits)
    readonly property string composerName: songMenu.single ? String(songMenu.info.composer || "").split(/\s*[;|]\s*/)[0] : ""
    MenuItem {
        objectName: "trackComposer"
        visible: songMenu.composerName.length > 0 && songMenu.context !== "composer"
        height: visible ? implicitHeight : 0
        text: "Go to composer " + Theme.plain(songMenu.composerName)
        icon.name: "note"
        onTriggered: Nav.openComposer(songMenu.composerName)
    }
    MenuItem {
        objectName: "trackKeep"
        visible: songMenu.copies.servers > 0 && songMenu.copies.kept + songMenu.copies.waiting < songMenu.copies.servers
        height: visible ? implicitHeight : 0
        text: "Keep on this computer"; icon.name: "download"
        onTriggered: serverCopies.keep(songMenu.paths)
    }
    MenuItem {
        objectName: "trackUnkeep"
        visible: songMenu.copies.kept + songMenu.copies.waiting > 0
        height: visible ? implicitHeight : 0
        text: songMenu.copies.waiting > 0 && songMenu.copies.kept === 0 ? "Stop keeping on this computer" : "Remove the copies from this computer"
        icon.name: "remove"
        onTriggered: serverCopies.remove(songMenu.paths)
    }
    MenuItem {
        objectName: "trackShowInFolder"
        visible: songMenu.single && !songMenu.stream && !songMenu.onServer
        height: visible ? implicitHeight : 0
        enabled: songMenu.info.exists === true
        text: "Show in folder"
        icon.name: "folder"
        onTriggered: library.showInFolder(songMenu.path)
    }
    MenuItem {
        objectName: "trackSpectrum"
        visible: songMenu.single && !songMenu.stream && !songMenu.onServer
        height: visible ? implicitHeight : 0
        enabled: songMenu.info.exists === true
        text: "Spectrum analyzer…"
        icon.name: "wave"
        onTriggered: Nav.openSpectrum(songMenu.path)
    }
    MenuItem {
        visible: !songMenu.stream; height: visible ? implicitHeight : 0
        text: "Edit tags…"
        icon.name: "edit"
        // CUE sheet songs are edited in the .cue file, and a server's songs on the server
        enabled: !songMenu.onServer && songMenu.paths.every(function (p) { return !/\.[A-Za-z0-9]+#\d+$/.test(p) })
        onTriggered: songMenu.single ? Nav.editTags(songMenu.path) : Nav.editTagsMany(songMenu.paths)
    }
    MenuItem {
        objectName: "trackRemoveFromQueue"
        visible: songMenu.single && songMenu.context === "queue"
        height: visible ? implicitHeight : 0
        text: "Remove from the queue"
        icon.name: "close"
        onTriggered: { player.removeAt(songMenu.index); Nav.notifyAction("Removed from the queue", "Undo", function () { player.undoQueue() }) }
    }
    MenuItem {
        objectName: "trackRemoveFromPlaylist"
        visible: songMenu.context === "playlist"
        height: visible ? implicitHeight : 0
        text: "Remove from this playlist"
        icon.name: "remove"
        icon.color: Theme.error
        onTriggered: songMenu.single ? songMenu.removeFromPlaylist([songMenu.index]) : songMenu.removePathsFromPlaylist(songMenu.paths)
    }
    MenuSeparator { visible: !songMenu.stream; height: visible ? implicitHeight : 0 }
    MenuItem {
        objectName: "trackRemove"
        visible: !songMenu.stream; height: visible ? implicitHeight : 0
        text: "Remove from library…"; icon.name: "remove"; icon.color: Theme.error
        onTriggered: Nav.removeSongs(songMenu.paths, songMenu.what)
    }
    MenuItem {
        objectName: "trackTrash"
        visible: !songMenu.stream && !songMenu.onServer; height: visible ? implicitHeight : 0
        text: "Move to trash…"; icon.name: "trash"; icon.color: Theme.error
        enabled: !songMenu.single || songMenu.info.exists === true
        onTriggered: Nav.trashSongs(songMenu.paths, songMenu.what)
    }

    Dialog {
        id: newDlg
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "New playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { nf.text = ""; nf.forceActiveFocus() }
        onAccepted: if (nf.text.trim().length) { Nav.openPlaylist(userLib.addPathsToNewPlaylist(nf.text.trim(), songMenu.paths)); songMenu.done("") }
        TextField {
            id: nf; implicitWidth: 280; placeholderText: "Playlist name"; selectByMouse: true
            onAccepted: if (text.trim().length) newDlg.accept()  // no nameless playlists
            onTextChanged: { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newDlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
}
