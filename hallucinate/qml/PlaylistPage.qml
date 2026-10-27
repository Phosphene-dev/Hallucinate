import QtQuick
import QtQuick.Controls
import "."

Item {
    id: page
    // Ctrl+A with no row focused (main.qml): the page's list
    function selectAll() { Selection.selectAll(list.toString(), list.model, "song", list.count && list.itemAtIndex(0) ? list.itemAtIndex(0).selectionOrigin : "") }
    objectName: "playlist"
    property bool liked: false
    property int playlistId: -1
    property string playlistName: ""
    readonly property var tracksModel: liked ? userLib.likedTracks : userLib.playlistTracks

    Component.onCompleted: if (!liked) userLib.openPlaylist(playlistId)
    function syncName() {
        for (var i = 0; i < userLib.playlists.count; i++)
            if (userLib.playlists.get(i).id === page.playlistId) page.playlistName = userLib.playlists.get(i).name
    }
    // renamed elsewhere (the sidebar's menu): keep the heading in step
    Connections {
        target: userLib.playlists
        enabled: !page.liked
        function onModelReset() { page.syncName() }
        function onDataChanged() { page.syncName() }
        function onRowsInserted() { page.syncName() }
    }

    Dialog {
        id: renameDlg
        anchors.centerIn: parent
        modal: true
        title: "Rename playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: if (nameField.text.trim().length) { userLib.renamePlaylist(page.playlistId, nameField.text.trim()); page.playlistName = nameField.text.trim() }
        TextField { id: nameField; implicitWidth: 280; text: page.playlistName; selectByMouse: true; onAccepted: renameDlg.accept() }
    }
    ConfirmDialog {
        id: deleteDlg
        objectName: "deletePlaylistDialog"
        title: "Delete this playlist?"
        body: "“" + page.playlistName + "” goes away for good. The songs in it stay in your library."
        confirmText: "Delete playlist"
        destructive: true
        onAccepted: { var id = page.playlistId; userLib.deletePlaylist(id); Nav.goHome(); Nav.routeGone("playlist", id) }
    }

    // how long it all lasts, and whether a song is in it more than once
    readonly property var summary: {
        var n = list.count, seconds = 0, seen = {}, twice = 0
        var items = page.tracksModel ? page.tracksModel.toList() : []
        for (var i = 0; i < items.length; i++) {
            seconds += items[i].duration || 0
            if (seen[items[i].path]) twice++
            seen[items[i].path] = true
        }
        return { seconds: seconds, twice: twice, n: n }
    }
    readonly property real seconds: summary.seconds
    Menu {
        id: moreMenu
        objectName: "playlistMenu"
        // its songs from a music server, kept on this computer or not (read as it opens)
        property var copies: ({ servers: 0, kept: 0, waiting: 0 })
        onAboutToShow: copies = page.tracksModel ? serverCopies.status(page.tracksModel.toList().map(function (t) { return t.path })) : copies
        MenuItem { objectName: "exportPlaylist"; text: "Export…"; icon.name: "download"; enabled: list.count > 0; onTriggered: Nav.exportPlaylist(page.liked ? "liked" : "playlist", page.liked ? "Liked Songs" : page.playlistName) }
        MenuItem { visible: !page.liked; height: visible ? implicitHeight : 0; text: "Rename…"; icon.name: "edit"; onTriggered: { nameField.text = page.playlistName; renameDlg.open() } }
        MenuItem {
            objectName: "duplicatePlaylist"
            visible: !page.liked; height: visible ? implicitHeight : 0
            text: "Make a copy"; icon.name: "plus"
            onTriggered: Nav.openPlaylist(userLib.duplicatePlaylist(page.playlistId, page.playlistName + " (copy)"))
        }
        MenuItem {
            objectName: "dedupePlaylist"
            visible: !page.liked; height: visible ? implicitHeight : 0
            enabled: page.summary.twice > 0
            text: page.summary.twice > 0 ? "Remove " + page.summary.twice + (page.summary.twice === 1 ? " repeat" : " repeats") : "No songs repeat"
            icon.name: "duplicates"
            onTriggered: { var n = userLib.removePlaylistDuplicates(page.playlistId); Nav.notify(n + (n === 1 ? " repeat" : " repeats") + " taken out; each song is in it once") }
        }
        MenuItem {
            objectName: "playlistKeep"
            visible: moreMenu.copies.servers > 0 && moreMenu.copies.kept + moreMenu.copies.waiting < moreMenu.copies.servers
            height: visible ? implicitHeight : 0
            text: "Keep on this computer"; icon.name: "download"
            onTriggered: serverCopies.keep(page.tracksModel.toList().map(function (t) { return t.path }))
        }
        MenuItem {
            objectName: "playlistUnkeep"
            visible: moreMenu.copies.kept + moreMenu.copies.waiting > 0
            height: visible ? implicitHeight : 0
            text: "Remove the copies from this computer"; icon.name: "remove"
            onTriggered: serverCopies.remove(page.tracksModel.toList().map(function (t) { return t.path }))
        }
        MenuSeparator { visible: !page.liked; height: visible ? implicitHeight : 0 }
        MenuItem { objectName: "deletePlaylist"; visible: !page.liked; height: visible ? implicitHeight : 0; text: "Delete playlist…"; icon.name: "trash"; icon.color: Theme.error; onTriggered: deleteDlg.open() }
    }

    ListView {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: list
        anchors.fill: parent
        anchors.leftMargin: 20; anchors.rightMargin: 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: page.tracksModel
        ScrollBar.vertical: ScrollBar {}

        KeepAtTop { target: list }  // stays at the top when the header changes height
        header: Item {
            width: list.width
            height: 150
            Column {
                anchors { left: parent.left; leftMargin: 8; bottom: parent.bottom; bottomMargin: 12 }
                spacing: 8
                Text { text: page.liked ? "COLLECTION" : "PLAYLIST"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold; textFormat: Text.PlainText }
                Text {
                    textFormat: Text.PlainText
                    text: page.liked ? "Liked Songs" : page.playlistName
                    width: Math.min(implicitWidth, list.width - 24)
                    elide: Text.ElideRight
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: (Theme.fontSize(30)) * Theme.displayScale
                    font.weight: Font.Bold
                }
                Text {
                    objectName: "playlistCount"
                    text: list.count + (list.count === 1 ? " song" : " songs") + (page.seconds >= 60 ? "  ·  " + Theme.fmtHours(page.seconds) : "")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText
                }
                Row {
                    spacing: 10
                    PillButton { primary: true; text: "Play"; enabled: list.count > 0; onClicked: page.liked ? userLib.playLiked(0) : userLib.playPlaylist(0, false) }
                    PillButton { text: "Shuffle"; enabled: list.count > 0; onClicked: page.liked ? (player.setShuffle(true), userLib.playLiked(Math.floor(Math.random() * list.count))) : userLib.playPlaylist(0, true) }
                    IconButton {
                        objectName: "playlistMore"
                        height: 38
                        icon: "more"; size: 18; tip: "More: export, rename, copy, tidy or delete"
                        onClicked: moreMenu.popup()
                    }
                }
            }
        }
        footer: Item {
            width: list.width
            height: list.count === 0 ? 300 : 0
            EmptyState {
                anchors.centerIn: parent
                visible: list.count === 0
                icon: page.liked ? "heart" : "playlist"
                title: page.liked ? "No liked songs yet" : "This playlist is empty"
                hint: page.liked ? "Tap the heart on any song and it's kept here."
                                 : "Use “…” on a song, or select a few and choose Add to playlist."
            }
        }
        delegate: TrackRow {
            selectionSource: ListView.view ? ListView.view.model : null
            path: model.path
            audioFormat: model.codec
            bitDepth: model.bit_depth || 0
            sampleRate: model.sample_rate || 0
            explicitTag: model.explicit || 0
            audioBitrate: model.bitrate
            rowIndex: index
            context: page.liked ? "liked" : "playlist"
            width: ListView.view.width - 12
            number: index + 1
            title: model.title
            artist: model.artist
            album: model.album
            durText: model.durText
            artUrl: model.artUrl
            current: Rows.currentId === model.id
            onActivated: page.liked ? userLib.playLiked(index) : userLib.playPlaylist(index, false)
            onEnqueue: player.enqueue(page.tracksModel.get(index))
        }
    }
}
