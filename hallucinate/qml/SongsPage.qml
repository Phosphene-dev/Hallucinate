import QtQuick
import QtQuick.Controls
import "."

Item {
    id: page
    // Ctrl+A with no row focused (main.qml): the page's list
    function selectAll() { Selection.selectAll(list.toString(), list.model, "song") }
    objectName: "songs"
    property bool duplicatesVisible: false
    // play the list as shown (duplicates, filtered, sorted or all), from `index`
    function playShown(index) {
        if (duplicatesVisible) library.playDuplicate(index)
        else if (library.filtersActive) library.playFilteredSongs(index)
        else if (library.songSort !== "title") library.playSortedSongs(index)
        else library.playSongs(index)
    }

    function applyFilters() {
        duplicatesVisible = false
        library.filterTracks(
            genreFilter.currentIndex > 0 ? genreFilter.currentText : "",
            yearFilter.currentIndex > 0 ? Number(yearFilter.currentText) : 0,
            formatFilter.currentIndex > 0 ? formatFilter.currentText : "")
    }

    Text {
        textFormat: Text.PlainText
        id: title
        x: 28; y: 20
        text: qsTr("Songs")
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale
        font.weight: Font.Bold
    }
    Text {
        textFormat: Text.PlainText
        anchors { left: title.right; leftMargin: 14; baseline: title.baseline }
        text: duplicatesVisible ? Theme.counted(qsTr("%n probable duplicate(s)", "", library.duplicates.count), library.duplicates.count)
            : library.filtersActive ? Theme.counted(qsTr("%n song(s) shown", "", library.filteredTracks.count), library.filteredTracks.count)
            : Theme.counted(qsTr("%n song(s)", "", library.trackCount), library.trackCount)
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(14)
    }
    Flow {  // the filters wrap onto a second line in a narrow window
        id: filters
        x: 28
        y: title.y + title.height + 12
        width: parent.width - 56
        spacing: 10
        StyledCombo {
            id: sortBox
            objectName: "songSort"
            width: 170
            height: 38
            readonly property var keys: ["title", "artist", "album", "genre", "year", "composer", "bpm", "plays", "added"]
            model: [qsTr("Sort by title"), qsTr("Sort by artist"), qsTr("Sort by album"), qsTr("Sort by genre"), qsTr("Sort by year"),
                    qsTr("Sort by composer"), qsTr("Sort by tempo"), qsTr("Most played"), qsTr("Recently added")]
            currentIndex: Math.max(0, keys.indexOf(library.songSort))
            onActivated: function (i) { library.setSongSort(keys[i]); shell.setUiValue("songSort", keys[i]) }
            Component.onCompleted: library.setSongSort(shell.uiValue("songSort", "title"))
            Accessible.name: qsTr("Order of the songs")
        }
        StyledCombo {
            id: genreFilter
            width: 180
            height: 38
            model: [qsTr("All genres")].concat(library.genres)
            selection: library.activeFilters[0] ? model.indexOf(library.activeFilters[0]) : 0  // the filter in force
            Accessible.name: qsTr("Genre to show")
            onActivated: page.applyFilters()
        }
        StyledCombo {
            id: yearFilter
            width: 128
            height: 38
            model: [qsTr("All years")].concat(library.years.map(function(value) { return String(value) }))
            selection: library.activeFilters[1] ? model.indexOf(String(library.activeFilters[1])) : 0
            Accessible.name: qsTr("Year to show")
            onActivated: page.applyFilters()
        }
        StyledCombo {
            id: formatFilter
            width: 130
            height: 38
            model: [qsTr("All formats")].concat(library.formats)
            selection: library.activeFilters[2] ? model.indexOf(library.activeFilters[2]) : 0
            Accessible.name: qsTr("Format to show")
            onActivated: page.applyFilters()
        }
        PillButton {
            objectName: "shuffleSongs"
            height: 38
            text: qsTr("Shuffle")
            visible: !page.duplicatesVisible
            enabled: list.count > 0
            Accessible.description: qsTr("Play the songs shown here in a random order")
            onClicked: { player.setShuffle(true); page.playShown(Math.floor(Math.random() * list.count)) }
        }
        PillButton {
            height: 38
            text: qsTr("Clear")
            visible: library.filtersActive
            onClicked: {
                genreFilter.currentIndex = 0
                yearFilter.currentIndex = 0
                formatFilter.currentIndex = 0
                library.filterTracks("", 0, "")
            }
        }
        PillButton {
            height: 38
            text: duplicatesVisible ? qsTr("Show songs") : library.duplicatesLoading ? qsTr("Finding…") : qsTr("Find duplicates")
            enabled: !library.duplicatesLoading
            onClicked: {
                duplicatesVisible = !duplicatesVisible
                if (duplicatesVisible) library.findDuplicates()
            }
        }
    }
    ListView {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: list
        anchors { top: filters.bottom; topMargin: 10; left: parent.left; right: parent.right; bottom: parent.bottom }
        anchors.leftMargin: 20; anchors.rightMargin: 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: page.duplicatesVisible ? library.duplicates
            : library.filtersActive ? library.filteredTracks
            : library.songSort !== "title" ? library.sortedSongs : library.songs
        cacheBuffer: 400
        ScrollBar.vertical: ScrollBar {}
        delegate: TrackRow {
            selectionSource: ListView.view ? ListView.view.model : null
            path: model.path
            audioFormat: model.codec
            bitDepth: model.bit_depth || 0
            sampleRate: model.sample_rate || 0
            explicitTag: model.explicit || 0
            audioBitrate: model.bitrate
            rowIndex: index
            width: ListView.view.width - 12
            title: model.title
            artist: model.artist + (page.duplicatesVisible ? " · " + Theme.counted(qsTr("%n copies", "", model.duplicateCount), model.duplicateCount) : "")
            // what the list is ordered by, beside the album
            album: library.songSort === "genre" && model.genre ? model.album + "  ·  " + shell.genresText(model.genre, false)
                 : library.songSort === "composer" && model.composer ? model.album + "  ·  " + model.composer
                 : library.songSort === "bpm" && model.bpm ? model.album + "  ·  " + qsTr("%1 BPM").arg(model.bpm) + (model.music_key ? "  ·  " + model.music_key : "")
                 : model.album
            durText: model.durText
            artUrl: model.artUrl
            current: Rows.currentId === model.id
            onActivated: page.playShown(index)
            onEnqueue: player.enqueue(list.model.get(index))
        }
    }
    EmptyState {
        anchors.centerIn: list
        visible: list.count === 0 && (page.duplicatesVisible || library.filtersActive)
        busy: page.duplicatesVisible && library.duplicatesLoading
        icon: page.duplicatesVisible ? "duplicates" : "search"
        title: page.duplicatesVisible ? (library.duplicatesLoading ? qsTr("Checking for duplicates…") : qsTr("No probable duplicates"))
                                      : qsTr("No songs match these filters")
        hint: page.duplicatesVisible ? (library.duplicatesLoading ? "" : qsTr("No two songs share a title, artist and length."))
                                     : qsTr("Try another genre, year or format.")
        actionText: !page.duplicatesVisible && library.filtersActive ? qsTr("Clear filters") : ""
        onAction: {
            genreFilter.currentIndex = 0
            yearFilter.currentIndex = 0
            formatFilter.currentIndex = 0
            library.filterTracks("", 0, "")
        }
    }
    EmptyState {
        objectName: "noMusic"
        anchors.centerIn: parent
        visible: library.ready && library.trackCount === 0
        icon: "folder"
        title: qsTr("No music yet")
        hint: library.folders.length ? qsTr("Hallucinate is looking through your music folders; songs appear as they're found.")
                                     : qsTr("Add the folder where you keep your music and it shows up here.")
        actionText: library.folders.length ? "" : qsTr("Open Settings")
        onAction: Nav.openSettings()
    }
}
