import QtQuick
import QtQuick.Controls
import "."

Item {
    id: page
    objectName: "artists"
    readonly property int cols: Math.max(2, Math.floor((width - 40) / 170))
    // A–Z (the library's own order) or most songs first, sorted here from the same list; remembered
    property string order: shell.uiValue("artistsOrder", "az") === "songs" ? "songs" : "az"
    onOrderChanged: shell.setUiValue("artistsOrder", order)
    property int revision: 0  // the artists changed (a scan): sort again
    Connections {
        target: page.order === "songs" ? library.artists : null
        function onModelReset() { page.revision++ }
        function onRowsInserted() { page.revision++ }
        function onRowsRemoved() { page.revision++ }
        function onDataChanged() { page.revision++ }
    }
    readonly property var bySongs: order === "songs" && revision >= 0
                                   ? library.artists.toList().sort(function (a, b) { return b.tracks - a.tracks || a.name.localeCompare(b.name) })
                                   : null

    Text {
        textFormat: Text.PlainText
        id: title
        x: 28; y: 20
        text: "Artists"
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: Theme.fontSize(25)
        font.weight: Font.Bold
    }
    Row {
        objectName: "artistsOrder"
        anchors { left: title.right; leftMargin: 18; verticalCenter: title.verticalCenter }
        spacing: 6
        Chip { objectName: "artistsAz"; text: "A–Z"; selected: page.order === "az"; onClicked: page.order = "az" }
        Chip { objectName: "artistsMostSongs"; text: "Most songs"; selected: page.order === "songs"; onClicked: page.order = "songs" }
    }
    GridView {
        id: grid
        anchors { top: title.bottom; topMargin: 14; left: parent.left; right: parent.right; bottom: parent.bottom }
        anchors.leftMargin: 20; anchors.rightMargin: 8
        cellWidth: Math.floor((width - 12) / page.cols)
        cellHeight: cellWidth + 60
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: page.bySongs || library.artists
        cacheBuffer: 600
        ScrollBar.vertical: ScrollBar {}
        delegate: Item {
            // the library's list gives roles; the sorted copy is plain objects
            readonly property var artist: page.bySongs ? model.modelData : model
            width: grid.cellWidth; height: grid.cellHeight
            ArtistCard {
                x: 10; y: 8
                cardWidth: grid.cellWidth - 28
                name: parent.artist.name
                subtitle: page.order === "songs" ? parent.artist.tracks + (parent.artist.tracks === 1 ? " song" : " songs")
                                                 : parent.artist.albums + (parent.artist.albums === 1 ? " album" : " albums")
                artUrl: parent.artist.artUrl
            }
        }
    }
    EmptyState {
        objectName: "noMusic"
        anchors.centerIn: parent
        visible: library.ready && library.trackCount === 0
        icon: "folder"
        title: "No music yet"
        hint: library.folders.length ? "Hallucinate is looking through your music folders; songs appear as they're found."
                                     : "Add the folder where you keep your music and it shows up here."
        actionText: library.folders.length ? "" : "Open Settings"
        onAction: Nav.openSettings()
    }
}
