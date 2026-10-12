import QtQuick
import QtQuick.Controls
import "."

// Floats above the player while songs are selected (Ctrl/Shift+click in a list) and acts on all of them.
Rectangle {
    id: bar
    objectName: "selectionBar"
    signal editTags(var paths)
    readonly property bool shown: Selection.count > 0

    width: Math.min(row.implicitWidth + 28, parent ? parent.width - 32 : 900)
    height: 52
    radius: 26
    color: Theme.glassStrong
    border.width: 1
    border.color: Theme.strokeHi
    opacity: shown ? 1 : 0
    visible: opacity > 0
    enabled: shown
    Behavior on opacity { NumberAnimation { duration: 160 } }

    function paths() { return Selection.paths.slice() }
    function done(message) { Selection.clear(); if (message) Nav.notify(message) }
    function songs(n) { return n + (n === 1 ? " song" : " songs") }

    Flickable {
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
                objectName: "selectionCount"
                anchors.verticalCenter: parent.verticalCenter
                rightPadding: 6
                text: bar.songs(Selection.count) + " selected"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
                font.weight: Font.DemiBold
            }
            component Action: PillButton { anchors.verticalCenter: parent.verticalCenter; implicitHeight: 34 }
            Action { objectName: "selectionPlay"; primary: true; text: "Play"; onClicked: { userLib.playPaths(bar.paths()); bar.done("") } }
            Action { text: "Play next"; onClicked: { var p = bar.paths(); userLib.playNextPaths(p); bar.done(bar.songs(p.length) + " will play next") } }
            Action { objectName: "selectionQueue"; text: "Add to queue"; onClicked: { var p = bar.paths(); userLib.enqueuePaths(p); bar.done(bar.songs(p.length) + " added to the queue") } }
            Action {
                id: plButton
                text: "Add to playlist…"
                onClicked: plMenu.popup(plButton, 0, -plMenu.implicitHeight - 6)
                Menu {
                    id: plMenu
                    MenuItem { text: "New playlist…"; onTriggered: newPl.open() }
                    MenuSeparator {}
                    Instantiator {
                        model: userLib.playlists
                        delegate: MenuItem {
                            text: model.name
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
                readonly property bool all: userLib.likesRevision >= 0 && userLib.allLiked(Selection.paths)
                active: all
                tip: all ? "Unlike all" : "Like all"
                onClicked: { userLib.setLikedPaths(bar.paths(), !all) }
            }
            Action {
                id: rateButton
                text: "Rate…"
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
                text: "Edit tags…"
                enabled: Selection.paths.every(function (p) { return !/\.[A-Za-z0-9]+#\d+$/.test(p) })
                onClicked: bar.editTags(bar.paths())
            }
            IconButton {
                objectName: "selectionClear"
                anchors.verticalCenter: parent.verticalCenter
                icon: "close"; size: 14; tip: "Clear selection (Esc)"
                onClicked: Selection.clear()
            }
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
        TextField { id: plName; width: 280; placeholderText: "Playlist name"; selectByMouse: true; onAccepted: newPl.accept() }
    }
}
