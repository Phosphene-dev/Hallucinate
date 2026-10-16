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

    MenuItem { text: "Play"; icon.name: "play"; onTriggered: podcasts.play(menu.episode.id) }
    MenuItem { text: "Play next"; icon.name: "next"; onTriggered: podcasts.playNext(menu.episode.id) }
    MenuItem { text: "Add to queue"; icon.name: "queue"; onTriggered: podcasts.enqueue(menu.episode.id) }
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
}
