import QtQuick
import QtQuick.Controls
import "."

Item {
    id: page
    objectName: "songs"
    property bool duplicatesVisible: false

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
        text: "Songs"
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: Theme.fontSize(25)
        font.weight: Font.Bold
    }
    Text {
        textFormat: Text.PlainText
        anchors { left: title.right; leftMargin: 14; baseline: title.baseline }
        text: duplicatesVisible ? library.duplicates.count + " probable duplicates"
            : library.filtersActive ? library.filteredTracks.count + " filtered tracks"
            : library.trackCount + " tracks"
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
            readonly property var keys: ["title", "artist", "album", "genre", "year"]
            model: ["Sort by title", "Sort by artist", "Sort by album", "Sort by genre", "Sort by year"]
            currentIndex: Math.max(0, keys.indexOf(library.songSort))
            onActivated: function (i) { library.setSongSort(keys[i]); shell.setUiValue("songSort", keys[i]) }
            Component.onCompleted: library.setSongSort(shell.uiValue("songSort", "title"))
            Accessible.name: "Order of the songs"
        }
        StyledCombo {
            id: genreFilter
            width: 180
            height: 38
            model: ["All genres"].concat(library.genres)
            onActivated: page.applyFilters()
        }
        StyledCombo {
            id: yearFilter
            width: 128
            height: 38
            model: ["All years"].concat(library.years.map(function(value) { return String(value) }))
            onActivated: page.applyFilters()
        }
        StyledCombo {
            id: formatFilter
            width: 130
            height: 38
            model: ["All formats"].concat(library.formats)
            onActivated: page.applyFilters()
        }
        PillButton {
            height: 38
            text: "Clear"
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
            text: duplicatesVisible ? "Show songs" : library.duplicatesLoading ? "Finding…" : "Find duplicates"
            enabled: !library.duplicatesLoading
            onClicked: {
                duplicatesVisible = !duplicatesVisible
                if (duplicatesVisible) library.findDuplicates()
            }
        }
    }
    ListView {
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
            audioBitrate: model.bitrate
            rowIndex: index
            width: ListView.view.width - 12
            title: model.title
            artist: model.artist + (page.duplicatesVisible ? " · " + model.duplicateCount + " copies" : "")
            album: library.songSort === "genre" && model.genre ? model.album + "  ·  " + model.genre.split(";")[0].trim() : model.album
            durText: model.durText
            artUrl: model.artUrl
            current: Rows.currentId === model.id
            onActivated: {
                if (page.duplicatesVisible) library.playDuplicate(index)
                else if (library.filtersActive) library.playFilteredSongs(index)
                else if (library.songSort !== "title") library.playSortedSongs(index)
                else library.playSongs(index)
            }
            onEnqueue: player.enqueue(list.model.get(index))
        }
    }
    EmptyState {
        anchors.centerIn: list
        visible: list.count === 0 && (page.duplicatesVisible || library.filtersActive)
        busy: page.duplicatesVisible && library.duplicatesLoading
        icon: page.duplicatesVisible ? "duplicates" : "search"
        title: page.duplicatesVisible ? (library.duplicatesLoading ? "Checking for duplicates…" : "No probable duplicates")
                                      : "No songs match these filters"
        hint: page.duplicatesVisible ? (library.duplicatesLoading ? "" : "No two songs share a title, artist and length.")
                                     : "Try another genre, year or format."
        actionText: !page.duplicatesVisible && library.filtersActive ? "Clear filters" : ""
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
        title: "No music yet"
        hint: library.folders.length ? "Hallucinate is looking through your music folders; songs appear as they're found."
                                     : "Add the folder where you keep your music and it shows up here."
        actionText: library.folders.length ? "" : "Open Settings"
        onAction: Nav.openSettings()
    }
}
