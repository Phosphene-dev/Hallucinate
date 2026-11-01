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
    // What fits (#111): 0 everything with full labels; 1 short labels; 2 Play next, Rate and Edit tags move into
    // More (an episode's last three into its own More); 3 Add to queue and Like too; 4 Add to playlist too; 5 the
    // count loses its "selected". Worked out again whenever the room or the selection changes; anything still
    // too wide scrolls, with arrows to say so.
    property int level: 0
    readonly property bool tight: level >= 1
    readonly property bool folded: level >= 2
    readonly property bool foldedMore: level >= 3
    readonly property bool foldedAll: level >= 4
    // How wide the bar's row was at each level, for this selection's kind of actions: resizing the window goes
    // straight to the level that fits, rather than back to 0 and folding up again on every step (#117)
    property var widths: ({})
    readonly property string actionsKey: [domain, songsOnly, filesOnly, playlistsOnly, inPlaylist, onServer].join()
    function fit() { if (shown && row.implicitWidth + 28 > maxWidth + 0.5 && level < 5) { level++; Qt.callLater(fit) } }
    function refit() {
        var l = 0
        while (l < 5 && widths[l] !== undefined && widths[l] + 28 > maxWidth + 0.5) l++
        level = l
        Qt.callLater(fit)  // (a level not seen yet is measured, and folded further if need be)
    }
    onMaxWidthChanged: refit()
    onActionsKeyChanged: { widths = {}; refit() }
    onShownChanged: if (shown) refit()
    Connections {
        target: row
        function onImplicitWidthChanged() { bar.widths[bar.level] = row.implicitWidth; Qt.callLater(bar.fit) }
    }
    width: Math.min(row.implicitWidth + 28, maxWidth)
    height: 52
    radius: Theme.round(26)
    color: Theme.glassStrong
    Bevel {}
    border.width: 1
    border.color: Theme.strokeHi
    // Now Playing covers the window: the bar steps out of its way and comes back after (#116); the selection stays
    property bool covered: false
    opacity: shown && !covered ? 1 : 0
    visible: opacity > 0
    enabled: shown && !covered
    Behavior on opacity { NumberAnimation { duration: 160 } }

    function paths() { return Selection.songPaths() }
    function keysOf(kind) { return Selection.items.filter(function (i) { return i.kind === kind }).map(function (i) { return i.key }) }
    function numbers(kind) { return keysOf(kind).map(function (k) { return parseInt(k) }) }
    function done(message) { Selection.clear(); if (message) Nav.notify(message) }

    // "3 albums", "12 songs": what the toast says was acted on
    function what() { return Selection.count === 1 && Selection.items[0].title ? qsTr("“%1”").arg(Selection.items[0].title) : Selection.summary(false) }
    function clearWithUndo() {
        if (Selection.count < 2) { Selection.clear(); return }
        var snap = Selection.snapshot(), n = Selection.summary(false)
        Selection.clear()
        Nav.notifyAction(qsTr("Cleared the selection (%1)").arg(n), qsTr("Undo"), function () { Selection.restore(snap) })
    }

    Flickable {
        WheelScroll { row: scroller }  // the wheel moves it sideways
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
                //: %1 is what's selected: "3 albums, 12 songs"
text: bar.level >= 5 ? Selection.summary(bar.tight) : qsTr("%1 selected").arg(Selection.summary(bar.tight))
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
                font.weight: Font.DemiBold
            }
            component Action: PillButton { anchors.verticalCenter: parent.verticalCenter; implicitHeight: 34 }

            // ---- music --------------------------------------------------------------------------------------
            Action { objectName: "selectionPlay"; visible: bar.music; primary: true; text: qsTr("Play"); onClicked: { userLib.playPaths(bar.paths()); bar.done("") } }
            Action {
                visible: bar.music && !bar.folded
                text: bar.tight ? qsTr("Next") : qsTr("Play next")
                onClicked: { var p = bar.paths(); userLib.playNextPaths(p); bar.done(Theme.counted(qsTr("%n song(s) will play next", "", p.length), p.length)) }
            }
            Action {
                objectName: "selectionQueue"
                visible: bar.music && !bar.foldedMore
                text: bar.tight ? qsTr("Queue") : qsTr("Add to queue")
                onClicked: { var p = bar.paths(); userLib.enqueuePaths(p); bar.done(Theme.counted(qsTr("%n song(s) added to the queue", "", p.length), p.length)) }
            }
            Action {
                id: plButton
                objectName: "selectionAddToPlaylist"
                visible: (bar.music && !bar.foldedAll) || bar.domain === "queue"
                text: bar.tight ? qsTr("Playlist…") : qsTr("Add to playlist…")
                onClicked: plMenu.popup(plButton, 0, -plMenu.implicitHeight - 6)
                Menu {
                    id: plMenu
                    MenuItem { text: qsTr("New playlist…"); icon.name: "plus"; onTriggered: newPl.open() }
                    MenuSeparator {}
                    Instantiator {
                        model: userLib.playlists
                        delegate: MenuItem {
                            text: Theme.plain(model.name)
                            onTriggered: { var p = bar.paths(); Selection.clear(); Nav.addToPlaylist(model.id, model.name, p, "") }
                        }
                        onObjectAdded: (index, object) => plMenu.insertItem(index + 2, object)
                        onObjectRemoved: (index, object) => plMenu.removeItem(object)
                    }
                }
            }
            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                icon: "heart"; size: 16
                visible: bar.music && shell.features.liked !== false && !bar.foldedMore
                // (worked out for songs picked one by one; for albums, artists… a click likes them all)
                readonly property bool all: bar.songsOnly && userLib.likesRevision >= 0 && userLib.allLiked(Selection.paths)
                active: all
                tip: all ? qsTr("Unlike all") : qsTr("Like all")
                onClicked: { var p = bar.paths(); userLib.setLikedPaths(p, !all); Nav.notify(all ? Theme.counted(qsTr("%n song(s) unliked", "", p.length), p.length) : Theme.counted(qsTr("%n song(s) liked", "", p.length), p.length)) }
            }
            Action {
                id: rateButton
                visible: bar.music && !bar.folded
                text: bar.tight ? qsTr("Rate") : qsTr("Rate…")
                onClicked: rateMenu.popup(rateButton, 0, -rateMenu.implicitHeight - 6)
                Menu {
                    id: rateMenu
                    Repeater {
                        model: 5
                        MenuItem {
                            required property int index
                            text: "★★★★★".slice(0, 5 - index) + "☆☆☆☆☆".slice(0, index)
                            onTriggered: { var p = bar.paths(); userLib.setRatingPaths(p, 5 - index); bar.done(Theme.counted(qsTr("%n song(s) rated %1★", "", p.length), p.length).arg(5 - index)) }
                        }
                    }
                    MenuSeparator {}
                    MenuItem { text: qsTr("Clear rating"); onTriggered: { userLib.setRatingPaths(bar.paths(), 0); bar.done("") } }
                }
            }
            Action {
                objectName: "selectionEditTags"
                visible: bar.filesOnly && !bar.onServer && !bar.folded
                text: bar.tight ? qsTr("Tags…") : qsTr("Edit tags…")
                enabled: Selection.paths.every(function (p) { return !/\.[A-Za-z0-9]+#\d+$/.test(p) })
                onClicked: bar.editTags(bar.paths())
            }
            Action {
                id: moreButton
                objectName: "selectionMore"
                visible: bar.music
                text: bar.tight ? qsTr("More") : qsTr("More…")
                onClicked: moreMenu.popup(moreButton, 0, -moreMenu.implicitHeight - 6)
                Menu {
                    id: moreMenu
                    component Item_: MenuItem { height: visible ? implicitHeight : 0 }
                    // what didn't fit in the bar (see level)
                    Item_ {
                        objectName: "selectionMorePlayNext"
                        visible: bar.folded
                        text: qsTr("Play next")
                        onTriggered: { var p = bar.paths(); userLib.playNextPaths(p); bar.done(Theme.counted(qsTr("%n song(s) will play next", "", p.length), p.length)) }
                    }
                    Item_ {
                        visible: bar.foldedMore
                        text: qsTr("Add to queue")
                        onTriggered: { var p = bar.paths(); userLib.enqueuePaths(p); bar.done(Theme.counted(qsTr("%n song(s) added to the queue", "", p.length), p.length)) }
                    }
                    Item_ {
                        visible: bar.foldedMore && shell.features.liked !== false
                        readonly property bool all: bar.songsOnly && userLib.likesRevision >= 0 && userLib.allLiked(Selection.paths)
                        text: all ? qsTr("Unlike all") : qsTr("Like all")
                        onTriggered: { var p = bar.paths(); userLib.setLikedPaths(p, !all); Nav.notify(all ? Theme.counted(qsTr("%n song(s) unliked", "", p.length), p.length) : Theme.counted(qsTr("%n song(s) liked", "", p.length), p.length)) }
                    }
                    Menu {
                        id: playlistSub
                        title: qsTr("Add to playlist")
                        MenuItem { text: qsTr("New playlist…"); icon.name: "plus"; onTriggered: newPl.open() }
                        MenuSeparator {}
                        Instantiator {
                            model: userLib.playlists
                            delegate: MenuItem {
                                text: Theme.plain(model.name)
                                onTriggered: { var p = bar.paths(); Selection.clear(); Nav.addToPlaylist(model.id, model.name, p, "") }
                            }
                            onObjectAdded: (index, object) => playlistSub.insertItem(index + 2, object)
                            onObjectRemoved: (index, object) => playlistSub.removeItem(object)
                        }
                    }
                    Menu {
                        id: rateSub
                        title: qsTr("Rate")
                        Repeater {
                            model: 5
                            MenuItem {
                                required property int index
                                text: "★★★★★".slice(0, 5 - index) + "☆☆☆☆☆".slice(0, index)
                                onTriggered: { var p = bar.paths(); userLib.setRatingPaths(p, 5 - index); bar.done(Theme.counted(qsTr("%n song(s) rated %1★", "", p.length), p.length).arg(5 - index)) }
                            }
                        }
                        MenuSeparator {}
                        MenuItem { text: qsTr("Clear rating"); onTriggered: { userLib.setRatingPaths(bar.paths(), 0); bar.done("") } }
                    }
                    Item_ {
                        visible: bar.folded && bar.filesOnly && !bar.onServer
                        text: qsTr("Edit tags…")
                        enabled: Selection.paths.every(function (p) { return !/\.[A-Za-z0-9]+#\d+$/.test(p) })
                        onTriggered: bar.editTags(bar.paths())
                    }
                    MenuSeparator { visible: bar.folded; height: visible ? implicitHeight : 0 }
                    Item_ {
                        objectName: "selectionRemoveFromPlaylist"
                        visible: bar.inPlaylist
                        text: qsTr("Remove from this playlist"); icon.name: "remove"; icon.color: Theme.error
                        onTriggered: bar.removeFromPlaylist(Selection.paths.slice())
                    }
                    Item_ {
                        objectName: "selectionRemoveFromHistory"
                        visible: bar.only(["history"])
                        text: Selection.count === 1 ? qsTr("Remove from history") : qsTr("Remove these plays from history"); icon.name: "remove"; icon.color: Theme.error  // i18n: keep (two sentences)
                        onTriggered: {
                            var ids = bar.numbers("history"), n = ids.length
                            userLib.removeHistoryEntries(ids)
                            bar.done(n === 1 ? qsTr("Removed from your history") : Theme.counted(qsTr("%n play(s) removed from your history", "", n), n))
                        }
                    }
                    Item_ {
                        objectName: "selectionDeletePlaylists"
                        visible: bar.playlistsOnly
                        text: qsTr("Delete playlist(s)…", "", Selection.count); icon.name: "trash"; icon.color: Theme.error
                        onTriggered: deleteDlg.open()
                    }
                    Item_ {
                        objectName: "selectionRemove"
                        visible: bar.filesOnly
                        text: qsTr("Remove from library…"); icon.name: "remove"; icon.color: Theme.error
                        onTriggered: bar.only(["album"]) ? Nav.removeAlbums(bar.keysOf("album"), Selection.summary(false))
                                                         : Nav.removeSongs(bar.paths(), Selection.summary(false))
                    }
                    Item_ {
                        objectName: "selectionTrash"
                        visible: bar.filesOnly && !bar.onServer
                        text: qsTr("Move to trash…"); icon.name: "trash"; icon.color: Theme.error
                        onTriggered: bar.only(["album"]) ? Nav.trashAlbums(bar.keysOf("album"), Selection.summary(false))
                                                         : Nav.trashSongs(bar.paths(), Selection.summary(false))
                    }
                    Item_ {
                        visible: !bar.filesOnly && !bar.playlistsOnly && !bar.inPlaylist && !bar.only(["history"])
                        enabled: false
                        text: qsTr("Removing works on songs and albums")
                    }
                }
            }

            // ---- the queue --------------------------------------------------------------------------------
            Action {
                visible: bar.domain === "queue"
                primary: true
                text: bar.tight ? qsTr("Next") : qsTr("Play next")
                onClicked: { player.moveIndexesNext(bar.numbers("queue")); bar.done(qsTr("%1 moved up next").arg(Selection.summary(false))) }
            }
            Action {
                objectName: "selectionRemoveFromQueue"
                visible: bar.domain === "queue"
                text: bar.tight ? qsTr("Remove") : qsTr("Remove from queue")
                onClicked: {
                    var n = Selection.count
                    player.removeIndexes(bar.numbers("queue"))
                    Selection.clear()
                    Nav.notifyAction(Theme.counted(qsTr("%n song(s) removed from the queue", "", n), n), qsTr("Undo"), function () { player.undoQueue() })
                }
            }

            // ---- podcast episodes -------------------------------------------------------------------------
            Action { visible: bar.domain === "episode"; primary: true; text: bar.tight ? qsTr("Next") : qsTr("Play next"); onClicked: { podcasts.playNextMany(bar.numbers("episode")); bar.done("") } }
            Action { visible: bar.domain === "episode"; text: bar.tight ? qsTr("Queue") : qsTr("Add to queue"); onClicked: { podcasts.enqueueMany(bar.numbers("episode")); bar.done("") } }
            Action { visible: bar.domain === "episode"; text: bar.tight ? qsTr("Played") : qsTr("Mark played"); onClicked: { podcasts.markPlayedMany(bar.numbers("episode"), true); bar.done("") } }
            Action { visible: bar.domain === "episode" && !bar.folded; text: bar.tight ? qsTr("Unplayed") : qsTr("Mark unplayed"); onClicked: { podcasts.markPlayedMany(bar.numbers("episode"), false); bar.done("") } }
            Action { visible: bar.domain === "episode" && !bar.folded; text: qsTr("Download"); onClicked: { podcasts.downloadMany(bar.numbers("episode")); bar.done(qsTr("Downloading %1").arg(Selection.summary(false))) } }
            Action { visible: bar.domain === "episode" && !bar.folded; text: bar.tight ? qsTr("Delete files") : qsTr("Remove downloads"); onClicked: { podcasts.removeDownloadMany(bar.numbers("episode")); bar.done("") } }
            Action {
                id: episodeMore
                visible: bar.domain === "episode" && bar.folded
                text: qsTr("More")
                onClicked: episodeMenu.popup(episodeMore, 0, -episodeMenu.implicitHeight - 6)
                Menu {
                    id: episodeMenu
                    MenuItem { text: qsTr("Mark unplayed"); onTriggered: { podcasts.markPlayedMany(bar.numbers("episode"), false); bar.done("") } }
                    MenuItem { text: qsTr("Download"); onTriggered: { podcasts.downloadMany(bar.numbers("episode")); bar.done(qsTr("Downloading %1").arg(Selection.summary(false))) } }
                    MenuItem { text: qsTr("Remove downloads"); onTriggered: { podcasts.removeDownloadMany(bar.numbers("episode")); bar.done("") } }
                }
            }

            // ---- radio stations ---------------------------------------------------------------------------
            Action { visible: bar.domain === "station"; primary: true; text: bar.tight ? qsTr("Next") : qsTr("Play next"); onClicked: { stations.playNextMany(bar.numbers("station")); bar.done("") } }
            Action { objectName: "selectionRemoveStations"; visible: bar.domain === "station"; text: qsTr("Remove"); onClicked: { stations.removeMany(bar.numbers("station")); Selection.clear() } }

            IconButton {
                objectName: "selectionClear"
                anchors.verticalCenter: parent.verticalCenter
                icon: "close"; size: 14; tip: qsTr("Clear selection (Esc)")
                onClicked: bar.clearWithUndo()
            }
        }
    }

    // Still too wide (a very small window): fades and arrows at the ends say there's more, and move to it
    Repeater {
        model: [-1, 1]
        delegate: Rectangle {
            required property int modelData
            readonly property bool more: scroller.contentWidth > scroller.width + 1 && (modelData < 0 ? !scroller.atXBeginning : !scroller.atXEnd)
            objectName: modelData < 0 ? "selectionScrollBack" : "selectionScrollOn"
            anchors.verticalCenter: parent.verticalCenter
            x: modelData < 0 ? 1 : parent.width - width - 1
            width: 44; height: parent.height - 2; radius: Theme.round(height / 2)
            visible: more
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: modelData < 0 ? Theme.glassStrong : "transparent" }
                GradientStop { position: 0.55; color: Theme.glassStrong }
                GradientStop { position: 1; color: modelData < 0 ? "transparent" : Theme.glassStrong }
            }
            Icon {
                anchors.centerIn: parent
                anchors.horizontalCenterOffset: modelData < 0 ? -4 : 4
                width: 14; height: 14
                name: modelData < 0 ? "back" : "forward"
                color: arrowMouse.containsMouse ? Theme.text : Theme.textDim
            }
            MouseArea {
                id: arrowMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: scroller.contentX = Math.max(0, Math.min(scroller.contentWidth - scroller.width,
                                                                    scroller.contentX + modelData * scroller.width * 0.7))
            }
            Accessible.role: Accessible.Button
            Accessible.name: modelData < 0 ? qsTr("Earlier actions") : qsTr("More actions")
        }
    }

    Dialog {
        id: newPl
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: qsTr("New playlist")
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { plName.text = ""; plName.forceActiveFocus() }
        onAccepted: {
            var name = plName.text.trim()
            if (!name.length) return
            var p = bar.paths()
            userLib.addPathsToNewPlaylist(name, p)
            bar.done(Theme.counted(qsTr("%n song(s) added to “%1”", "", p.length), p.length).arg(name))
        }
        TextField {
            id: plName; implicitWidth: 280; placeholderText: qsTr("Playlist name"); selectByMouse: true
            onAccepted: if (text.trim().length) newPl.accept()  // no nameless playlists
            onTextChanged: { var b = newPl.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = newPl.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
    ConfirmDialog {
        id: deleteDlg
        objectName: "deletePlaylistsDialog"
        title: Selection.count === 1 ? qsTr("Delete this playlist?") : Theme.counted(qsTr("Delete %n playlist(s)?", "", Selection.count), Selection.count)
        confirmText: qsTr("Delete")
        destructive: true
        body: qsTr("%1 will be deleted. The songs in them stay in your library.").arg(Selection.summary(false))
        onAccepted: {
            bar.numbers("playlist").forEach(function (id) { userLib.deletePlaylist(id) })
            bar.numbers("smart").forEach(function (id) { userLib.deleteSmartPlaylist(id) })
            bar.done(qsTr("%1 deleted").arg(Selection.summary(false)))
        }
    }
}
