import QtQuick
import QtQuick.Controls
import "."

Item {
    id: page
    objectName: "artists"
    readonly property int cols: Math.max(2, Math.floor((width - 40) / 170))
    // A–Z (the library's own order), most songs, most played or newest first: sorted here from the same list
    // (its rows carry plays and when the artist's newest song was added); remembered
    readonly property var orders: ["az", "songs", "plays", "added"]
    property string order: orders.indexOf(shell.uiValue("artistsOrder", "az")) >= 0 ? shell.uiValue("artistsOrder", "az") : "az"
    onOrderChanged: shell.setUiValue("artistsOrder", order)
    property int revision: 0  // the artists changed (a scan): sort again
    Connections {
        target: page.order !== "az" ? library.artists : null
        function onModelReset() { page.revision++ }
        function onRowsInserted() { page.revision++ }
        function onRowsRemoved() { page.revision++ }
        function onDataChanged() { page.revision++ }
    }
    function compare(field) {
        return function (a, b) { return (b[field] || 0) - (a[field] || 0) || a.name.localeCompare(b.name) }
    }
    readonly property var bySongs: order !== "az" && revision >= 0
                                   ? library.artists.toList().sort(compare({songs: "tracks", plays: "plays", added: "added"}[order]))
                                   : null
    // Artists, or (when songs credit any) the composers who wrote them; remembered
    property bool composers: shell.uiValue("artistsView", "artists") === "composers" && library.composerList.length > 0
    function setView(c) { composers = c; shell.setUiValue("artistsView", c ? "composers" : "artists") }
    readonly property var composerRows: !composers ? null : order === "az"
        ? library.composerList.slice().sort(function (a, b) { return a.name.localeCompare(b.name) })
        : library.composerList  // most songs first (as it comes)
    function subtitle(a) {
        if (composers) return a.works > 0 ? a.works + (a.works === 1 ? " work" : " works") : a.tracks + (a.tracks === 1 ? " song" : " songs")
        if (order === "songs") return a.tracks + (a.tracks === 1 ? " song" : " songs")
        if (order === "plays") return (a.plays || 0) + (a.plays === 1 ? " play" : " plays")
        return a.albums + (a.albums === 1 ? " album" : " albums")
    }

    Text {
        textFormat: Text.PlainText
        id: title
        x: 28; y: 20
        text: page.composers ? "Composers" : "Artists"
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale
        font.weight: Font.Bold
    }
    Row {
        anchors { left: title.right; leftMargin: 18; verticalCenter: title.verticalCenter }
        spacing: 10
        Row {
            objectName: "artistsView"
            visible: library.composerList.length > 0
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Chip { objectName: "viewArtists"; text: "Artists"; selected: !page.composers; onClicked: page.setView(false) }
            Chip { objectName: "viewComposers"; text: "Composers"; selected: page.composers; onClicked: page.setView(true) }
        }
        StyledCombo {
            objectName: "artistsOrder"
            width: 190; height: 36
            // composers: A–Z or most songs
            model: page.composers ? ["A–Z", "Most songs"] : ["A–Z", "Most songs", "Most played", "Recently added"]
            selection: page.composers ? (page.order === "az" ? 0 : 1) : page.orders.indexOf(page.order)
            onActivated: function (i) { page.order = page.orders[i] }
            Accessible.name: page.composers ? "Order of the composers" : "Order of the artists"
        }
    }
    GridView {
        id: grid
        anchors { top: title.bottom; topMargin: 14; left: parent.left; right: parent.right; bottom: parent.bottom }
        anchors.leftMargin: 20; anchors.rightMargin: 8
        cellWidth: Math.floor((width - 12) / page.cols)
        cellHeight: cellWidth + 60
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: page.composers ? page.composerRows : page.bySongs || library.artists
        cacheBuffer: 600
        ScrollBar.vertical: ScrollBar {}
        delegate: Item {
            // the library's list gives roles; the sorted copy is plain objects
            readonly property var artist: page.bySongs || page.composers ? model.modelData : model
            width: grid.cellWidth; height: grid.cellHeight
            ArtistCard {
                x: 10; y: 8
                cardWidth: grid.cellWidth - 28
                name: parent.artist.name
                subtitle: page.subtitle(parent.artist)
                composer: page.composers
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
