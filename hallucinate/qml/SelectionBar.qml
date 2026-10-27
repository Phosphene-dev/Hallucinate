import QtQuick
import QtQuick.Controls
import "."

// Floats above the player while anything is selected (see Selection) and acts on all of it. Songs, albums,
// artists, genres, composers, folders, plays and playlists are all music: the bar plays, queues, adds to a playlist,
// likes and rates all their songs. Queue entries, podcast episodes and radio stations have their own actions.
// Acting ends the selection; ✕ or Esc clears it, with Undo.
Rectangle {
    id: bar
    objectName: "selectionBar"
    signal editTags(var paths)
    signal removeFromPlaylist(var paths)
    readonly property bool shown: Selection.count > 0
    readonly property string domain: Selection.domain
    readonly property bool music: domain === "music"
    function only(kinds) { return Selection.count > 0 && Selection.items.every(function (i) { return kinds.indexOf(i.kind) >= 0 }) }
    readonly property bool songsOnly: Selection.count > 0 && only(["song"])
    readonly property bool filesOnly: Selection.count > 0 && only(["song", "album"])  // what removing and tag editing take
    readonly property bool playlistsOnly: Selection.count > 0 && only(["playlist", "smart"])
    // songs on a music server: no files here to edit or put in the trash
    readonly property bool onServer: Selection.paths.some(function (p) { return /^(subsonic|jellyfin):\/\//.test(p) })
    // selected in the playlist that's open (not Liked Songs or a smart playlist): they can be taken out of it
    readonly property bool inPlaylist: songsOnly && Selection.origin.length > 0 && Selection.origin === "playlist:" + userLib.currentPlaylist

    property real maxWidth: parent ? parent.width - 32 : 900
    readonly property bool tight: maxWidth < 860  // short labels in small windows
    width: Math.min(row.implicitWidth + 28, maxWidth)
    height: 52
    radius: Theme.round(26)
    color: Theme.glassStrong
    Bevel {}
    border.width: 1
    border.color: Theme.strokeHi
    opacity: shown ? 1 : 0
    visible: opacity > 0
    enabled: shown
    Behavior on opacity { NumberAnimation { duration: 160 } }

    function paths() { return Selection.songPaths() }
    function keysOf(kind) { return Selection.items.filter(function (i) { return i.kind === kind }).map(function (i) { return i.key }) }
    function numbers(kind) { return keysOf(kind).map(function (k) { return parseInt(k) }) }
    function done(message) { Selection.clear(); if (message) Nav.notify(message) }
    function songs(n) { return n + (n === 1 ? " song" : " songs") }
    // "3 albums", "12 songs": what the toast says was acted on
    function what() { return Selection.count === 1 && Selection.items[0].title ? "“" + Selection.items[0].title + "”" : Selection.summary(false) }
    function clearWithUndo() {
        if (Selection.count < 2) { Selection.clear(); return }
        var snap = Selection.snapshot(), n = Selection.summary(false)
        Selection.clear()
        Nav.notifyAction("Cleared the selection (" + n + ")", "Undo", function () { Selection.restore(snap) })
    }

    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
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
                objectName: "selectionCount"
                anchors.verticalCenter: parent.verticalCenter
                rightPadding: 6
                text: Selection.summary(bar.tight) + " selected"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
                font.weight: Font.DemiBold
            }
            component Action: PillButton { anchors.verticalCenter: parent.verticalCenter; implicitHeight: 34 }

            // ---- music --------------------------------------------------------------------------------------
            Action { objectName: "selectionPlay"; visible: bar.music; primary: true; text: "Play"; onClicked: { userLib.playPaths(bar.paths()); bar.done("") } }
            Action {
                visible: bar.music
                text: bar.tight ? "Next" : "Play next"
                onClicked: { var p = bar.paths(); userLib.playNextPaths(p); bar.done(bar.songs(p.length) + " will play next") }
            }
            Action {
                objectName: "selectionQueue"
                visible: bar.music
                text: bar.tight ? "Queue" : "Add to queue"
                onClicked: { var p = bar.paths(); userLib.enqueuePaths(p); bar.done(bar.songs(p.length) + " added to the queue") }
            }
            Action {
                id: plButton
                objectName: "selectionAddToPlaylist"
                visible: bar.music || bar.domain === "queue"
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
                            onTriggered: { var p = bar.paths(); userLib.addPathsToPlaylist(model.id, p); bar.done(bar.songs(p.length) + " added to “" + model.name + "”") }
                        }
                        onObjectAdded: (index, object) => plMenu.insertItem(index + 2, object)
                        onObjectRemoved: (index, object) => plMenu.removeItem(object)
                    }
                }
            }
            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                icon: "heart"; size: 16
                visible: bar.music && shell.features.liked !== false
                // (worked out for songs picked one by one; for albums, artists… a click likes them all)
                readonly property bool all: bar.songsOnly && userLib.likesRevision >= 0 && userLib.allLiked(Selection.paths)
                active: all
                tip: all ? "Unlike all" : "Like all"
                onClicked: { var p = bar.paths(); userLib.setLikedPaths(p, !all); Nav.notify(all ? bar.songs(p.length) + " unliked" : bar.songs(p.length) + " liked") }
            }
            Action {
                id: rateButton
                visible: bar.music
                text: bar.tight ? "Rate" : "Rate…"
                onClicked: rateMenu.popup(rateButton, 0, -rateMenu.implicitHeight - 6)
                Menu {
                    id: rateMenu
                    Repeater {
                        model: 5
                        MenuItem {
                            required property int index
                            text: "★★★★★".slice(0, 5 - index) + "☆☆☆☆☆".slice(0, index)
                            onTriggered: { var p = bar.paths(); userLib.setRatingPaths(p, 5 - index); bar.done(bar.songs(p.length) + " rated " + (5 - index) + "★") }
                        }
                    }
                    MenuSeparator {}
                    MenuItem { text: "Clear rating"; onTriggered: { userLib.setRatingPaths(bar.paths(), 0); bar.done("") } }
                }
            }
            Action {
                objectName: "selectionEditTags"
                visible: bar.filesOnly && !bar.onServer
                text: bar.tight ? "Tags…" : "Edit tags…"
                enabled: Selection.paths.every(function (p) { return !/\.[A-Za-z0-9]+#\d+$/.test(p) })
                onClicked: bar.editTags(bar.paths())
            }
            Action {
                id: moreButton
                objectName: "selectionMore"
                visible: bar.music
                text: bar.tight ? "More" : "More…"
                onClicked: moreMenu.popup(moreButton, 0, -moreMenu.implicitHeight - 6)
                Menu {
                    id: moreMenu
                    component Item_: MenuItem { height: visible ? implicitHeight : 0 }
                    Item_ {
                        objectName: "selectionRemoveFromPlaylist"
                        visible: bar.inPlaylist
                        text: "Remove from this playlist"; icon.name: "remove"; icon.color: Theme.error
                        onTriggered: bar.removeFromPlaylist(Selection.paths.slice())
                    }
                    Item_ {
                        objectName: "selectionRemoveFromHistory"
                        visible: bar.only(["history"])
                        text: Selection.count === 1 ? "Remove from history" : "Remove these plays from history"; icon.name: "remove"; icon.color: Theme.error
                        onTriggered: {
                            var ids = bar.numbers("history"), n = ids.length
                            userLib.removeHistoryEntries(ids)
                            bar.done(n === 1 ? "Removed from your history" : n + " plays removed from your history")
                        }
                    }
                    Item_ {
                        objectName: "selectionDeletePlaylists"
                        visible: bar.playlistsOnly
                        text: Selection.count === 1 ? "Delete playlist…" : "Delete playlists…"; icon.name: "trash"; icon.color: Theme.error
                        onTriggered: deleteDlg.open()
                    }
                    Item_ {
                        objectName: "selectionRemove"
                        visible: bar.filesOnly
                        text: "Remove from library…"; icon.name: "remove"; icon.color: Theme.error
                        onTriggered: bar.only(["album"]) ? Nav.removeAlbums(bar.keysOf("album"), Selection.summary(false))
                                                         : Nav.removeSongs(bar.paths(), Selection.summary(false))
                    }
                    Item_ {
                        objectName: "selectionTrash"
                        visible: bar.filesOnly && !bar.onServer
                        text: "Move to trash…"; icon.name: "trash"; icon.color: Theme.error
                        onTriggered: bar.only(["album"]) ? Nav.trashAlbums(bar.keysOf("album"), Selection.summary(false))
                                                         : Nav.trashSongs(bar.paths(), Selection.summary(false))
                    }
                    Item_ {
                        visible: !bar.filesOnly && !bar.playlistsOnly && !bar.inPlaylist && !bar.only(["history"])
                        enabled: false
                        text: "Removing works on songs and albums"
                    }
                }
            }

            // ---- the queue --------------------------------------------------------------------------------
            Action {
                visible: bar.domain === "queue"
                primary: true
                text: bar.tight ? "Next" : "Play next"
                onClicked: { player.moveIndexesNext(bar.numbers("queue")); bar.done(Selection.summary(false) + " moved up next") }
            }
            Action {
                objectName: "selectionRemoveFromQueue"
                visible: bar.domain === "queue"
                text: bar.tight ? "Remove" : "Remove from queue"
                onClicked: {
                    var n = Selection.count
                    player.removeIndexes(bar.numbers("queue"))
                    Selection.clear()
                    Nav.notifyAction(bar.songs(n) + " removed from the queue", "Undo", function () { player.undoQueue() })
                }
            }

            // ---- podcast episodes -------------------------------------------------------------------------
            Action { visible: bar.domain === "episode"; primary: true; text: bar.tight ? "Next" : "Play next"; onClicked: { podcasts.playNextMany(bar.numbers("episode")); bar.done("") } }
            Action { visible: bar.domain === "episode"; text: bar.tight ? "Queue" : "Add to queue"; onClicked: { podcasts.enqueueMany(bar.numbers("episode")); bar.done("") } }
            Action { visible: bar.domain === "episode"; text: bar.tight ? "Played" : "Mark played"; onClicked: { podcasts.markPlayedMany(bar.numbers("episode"), true); bar.done("") } }
            Action { visible: bar.domain === "episode"; text: bar.tight ? "Unplayed" : "Mark unplayed"; onClicked: { podcasts.markPlayedMany(bar.numbers("episode"), false); bar.done("") } }
            Action { visible: bar.domain === "episode"; text: "Download"; onClicked: { podcasts.downloadMany(bar.numbers("episode")); bar.done("Downloading " + Selection.summary(false)) } }
            Action { visible: bar.domain === "episode"; text: bar.tight ? "Delete files" : "Remove downloads"; onClicked: { podcasts.removeDownloadMany(bar.numbers("episode")); bar.done("") } }

            // ---- radio stations ---------------------------------------------------------------------------
            Action { visible: bar.domain === "station"; primary: true; text: bar.tight ? "Next" : "Play next"; onClicked: { stations.playNextMany(bar.numbers("station")); bar.done("") } }
            Action { objectName: "selectionRemoveStations"; visible: bar.domain === "station"; text: "Remove"; onClicked: { stations.removeMany(bar.numbers("station")); Selection.clear() } }

            IconButton {
                objectName: "selectionClear"
                anchors.verticalCenter: parent.verticalCenter
                icon: "close"; size: 14; tip: "Clear selection (Esc)"
                onClicked: bar.clearWithUndo()
            }
        }
    }

    Rectangle {  // more buttons to the right: scroll (wheel or drag) to reach them
        anchors { right: parent.right; rightMargin: 1; verticalCenter: parent.verticalCenter }
        width: 36; height: parent.height - 2; radius: Theme.round(height / 2)
        visible: scroller.contentWidth > scroller.width && !scroller.atXEnd
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 1; color: Theme.glassStrong }
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
            var p = bar.paths()
            userLib.addPathsToNewPlaylist(name, p)
            bar.done(bar.songs(p.length) + " added to “" + name + "”")
        }
        TextField {
            id: plName; implicitWidth: 280; placeholderText: "Playlist name"; selectByMouse: true
            onAccepted: if (text.trim().length) newPl.accept()  // no nameless playlists
            onTextChanged: { var b = newPl.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newPl.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
    ConfirmDialog {
        id: deleteDlg
        objectName: "deletePlaylistsDialog"
        title: Selection.count === 1 ? "Delete this playlist?" : "Delete " + Selection.count + " playlists?"
        confirmText: "Delete"
        destructive: true
        body: Selection.summary(false) + " will be deleted. The songs in them stay in your library."
        onAccepted: {
            bar.numbers("playlist").forEach(function (id) { userLib.deletePlaylist(id) })
            bar.numbers("smart").forEach(function (id) { userLib.deleteSmartPlaylist(id) })
            bar.done(Selection.summary(false) + " deleted")
        }
    }
}
