import QtQuick
import QtQuick.Controls
import "."

// Right-click (or "…") on a podcast episode.
Menu {
    id: menu
    objectName: "episodeMenu"
    property var episode: ({})
    property bool showGoToShow: false
    function showFor(e, goToShow) { episode = e; showGoToShow = !!goToShow; popup() }

    MenuItem {
        objectName: "episodeNotes"
        text: "Show notes"; icon.name: "note"
        onTriggered: notes.open()
    }
    MenuSeparator {}
    MenuItem { text: "Play"; icon.name: "play"; onTriggered: podcasts.play(menu.episode.id) }
    MenuItem { text: "Play next"; icon.name: "next"; onTriggered: podcasts.playNext(menu.episode.id) }
    MenuItem { text: "Add to queue"; icon.name: "queue"; onTriggered: podcasts.enqueue(menu.episode.id) }
    MenuItem {
        objectName: "episodeUpNext"
        text: menu.episode.up_next > 0 ? "Remove from Up next" : "Add to Up next"
        icon.name: menu.episode.up_next > 0 ? "remove" : "plus"
        onTriggered: menu.episode.up_next > 0 ? podcasts.removeUpNext(menu.episode.id) : podcasts.addUpNext(menu.episode.id, false)
    }
    MenuItem {
        visible: !(menu.episode.up_next > 0)
        height: visible ? implicitHeight : 0
        text: "Put first in Up next"; icon.name: "next"
        onTriggered: podcasts.addUpNext(menu.episode.id, true)
    }
    MenuSeparator {}
    MenuItem {
        objectName: "episodePlayed"
        text: menu.episode.played ? "Mark as not played" : "Mark as played"
        icon.name: "check"
        onTriggered: podcasts.markPlayed(menu.episode.id, !menu.episode.played)
    }
    MenuItem {
        visible: !menu.episode.local && (menu.episode.url || "").length > 0 && !menu.episode.downloading
        height: visible ? implicitHeight : 0
        text: "Download"; icon.name: "download"
        onTriggered: podcasts.download(menu.episode.id)
    }
    MenuItem {
        visible: !!menu.episode.downloading
        height: visible ? implicitHeight : 0
        text: "Stop downloading"; icon.name: "close"
        onTriggered: podcasts.cancelDownload(menu.episode.id)
    }
    MenuItem {
        visible: !!menu.episode.downloaded
        height: visible ? implicitHeight : 0
        text: "Remove download"; icon.name: "remove"; icon.color: Theme.error
        onTriggered: podcasts.removeDownload(menu.episode.id)
    }
    MenuSeparator {}
    MenuItem {
        visible: menu.showGoToShow
        height: visible ? implicitHeight : 0
        text: "Go to the show"; icon.name: "podcast"
        onTriggered: Nav.openPodcast(menu.episode.podcast_id)
    }
    MenuItem {
        visible: (menu.episode.url || "").length > 0
        height: visible ? implicitHeight : 0
        text: "Copy episode link"; icon.name: "playlist"
        onTriggered: { shell.copyText(menu.episode.url); Nav.notify("Episode link copied") }
    }

    Dialog {
        id: notes
        objectName: "episodeNotesDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(620, (parent ? parent.width : 620) - 40)
        height: Math.min(560, (parent ? parent.height : 560) - 60)
        modal: true
        title: menu.episode.title || ""
        standardButtons: Dialog.Close
        Column {
            id: notesHead
            width: notes.availableWidth
            spacing: 6
            Text {
                textFormat: Text.PlainText
                width: parent.width
                elide: Text.ElideRight
                text: (menu.episode.podcast ? menu.episode.podcast + "  ·  " : "") + (menu.episode.detail || "")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Row {
                spacing: 10
                PillButton { primary: true; text: "Play"; onClicked: { podcasts.play(menu.episode.id); notes.close() } }
                PillButton {
                    text: menu.episode.played ? "Mark as not played" : "Mark as played"
                    onClicked: podcasts.markPlayed(menu.episode.id, !menu.episode.played)
                }
            }
        }
        Flickable {
            anchors { left: parent.left; right: parent.right; top: notesHead.bottom; topMargin: 14; bottom: parent.bottom }
            contentHeight: notesText.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            TextEdit {
                id: notesText
                objectName: "episodeNotesText"
                width: parent.width - 12
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                textFormat: TextEdit.PlainText
                text: (menu.episode.description || "").length ? menu.episode.description : "This episode has no notes."
                color: Theme.text; selectionColor: Theme.accent; selectedTextColor: Theme.onAccent
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                Accessible.role: Accessible.StaticText
                Accessible.name: "Show notes"
            }
        }
    }
}
