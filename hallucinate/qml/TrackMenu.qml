import QtQuick
import QtQuick.Controls
import "."

Menu {
    id: menu
    property string path: ""
    property string trackTitle: ""
    property string context: ""
    property int index: -1

    function show(p, t, c, i) { path = p; trackTitle = t; context = c; index = i; popup() }

    Item {
        objectName: "menuRating"
        width: 220; height: 38
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
    MenuSeparator {}
    MenuItem { text: "Play next"; icon.name: "next"; onTriggered: userLib.playNextPath(menu.path) }
    MenuItem { text: "Add to queue"; icon.name: "queue"; onTriggered: userLib.enqueuePath(menu.path) }
    MenuItem {
        text: userLib.likesRevision >= 0 && userLib.isLiked(menu.path) ? "Remove from Liked Songs" : "Add to Liked Songs"
        icon.name: "heart"
        onTriggered: userLib.toggleLike(menu.path)
    }
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
                onTriggered: userLib.addToPlaylist(id, menu.path)
            }
            onObjectAdded: (i, o) => plMenu.addItem(o)
            onObjectRemoved: (i, o) => plMenu.removeItem(o)
        }
    }
    MenuItem {
        text: "Edit tags…"
        icon.name: "edit"
        enabled: !/\.[A-Za-z0-9]+#\d+$/.test(menu.path)  // CUE sheet songs are edited in the .cue file
        onTriggered: Nav.editTags(menu.path)
    }
    MenuItem {
        visible: menu.context === "playlist"
        height: visible ? implicitHeight : 0
        text: "Remove from this playlist"
        icon.name: "remove"
        icon.color: Theme.error
        onTriggered: userLib.removeFromPlaylist(menu.index)
    }

    Dialog {
        id: newDlg
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "New playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { nf.text = ""; nf.forceActiveFocus() }
        onAccepted: if (nf.text.trim().length) { var id = userLib.addToNewPlaylist(nf.text.trim(), menu.path); Nav.openPlaylist(id) }
        TextField { id: nf; width: 280; placeholderText: "Playlist name"; selectByMouse: true; onAccepted: newDlg.accept() }
    }
}
