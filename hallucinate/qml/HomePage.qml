import QtQuick
import QtQuick.Controls
import "."

// Home is about your library: something to play from your own shelves, when you listen, what your collection
// holds, what you've played lately and more. Its sections can be switched off and put in any order (Settings →
// Features → Home, or a section's own menu); the usual order is shell's HOME_SECTIONS.
Item {
    id: page
    objectName: "home"
    property var pick: ({})
    readonly property var facts: userLib.home.facts || ({})

    function reroll() { pick = library.randomAlbum(pick.album_key || "") }
    Component.onCompleted: { reroll(); if (hasMixes && sectionOn("mixes")) discover.open() }
    Connections {
        target: library
        function onReloaded() { if (!page.pick.album_key) page.reroll() }
    }

    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: fl
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: col
            objectName: "homeColumn"
            x: Theme.contentX(fl.width); y: 12
            width: Theme.contentWidth(fl.width)
            spacing: 26

            Column {
                width: parent.width
                spacing: 6
                Text {
                    textFormat: Text.PlainText
                    text: qsTr("Home")
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale
                    font.weight: Font.Bold
                }
                Text {
                    textFormat: Text.PlainText
                    objectName: "librarySummary"
                    width: parent.width
                    wrapMode: Text.WordWrap
                    visible: library.trackCount > 0
                    text: [Theme.counted(qsTr("%n album(s)", "", library.albumCount), library.albumCount),
                           Theme.counted(qsTr("%n song(s)", "", library.trackCount), library.trackCount),
                           Theme.counted(qsTr("%n artist(s)", "", library.artistCount), library.artistCount),
                           page.facts.seconds ? qsTr("%1 of music").arg(Theme.fmtHours(page.facts.seconds)) : ""].filter(s => s).join("  ·  ")
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(14)
                }
                Text {
                    textFormat: Text.PlainText
                    objectName: "homeHealthLink"
                    visible: library.trackCount > 0 && shell.features.health !== false
                    text: qsTr("Library health ›")
                    color: healthLinkMouse.containsMouse ? Theme.accentHi : Theme.accent
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(13)
                    font.weight: Font.DemiBold
                    LinkArea { id: healthLinkMouse; name: "Library health"; hoverEnabled: true; onClicked: Nav.openHealth() }
                }
            }

            Rectangle {
                visible: library.trackCount === 0
                width: parent.width
                height: 220
                radius: Theme.radius + 4
                color: Theme.surface
                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    Text {
                        textFormat: Text.PlainText
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: !library.ready ? qsTr("Loading your library…")
                            : library.scanning ? qsTr("Scanning your music…")
                            : library.hasFolders ? qsTr("No music found") : qsTr("Welcome! Let's find your music")
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: (Theme.fontSize(16)) * Theme.displayScale
                        font.weight: Font.DemiBold
                    }
                    Text {
                        textFormat: Text.PlainText
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: library.scanning ? qsTr("Songs appear here as they are found.")
                            : library.missingFolders.length > 0 ? qsTr("Folder not found or unreadable: %1").arg(library.missingFolders.join(", "))
                            : library.hasFolders ? qsTr("Your folders contain no supported audio files. Add another folder or check Settings.")
                            : qsTr("Choose the folder that holds your music to get started.")
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(14)
                    }
                    ScanBar { width: 320; anchors.horizontalCenter: parent.horizontalCenter }
                    PillButton {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: !library.scanning && library.ready
                        primary: true
                        text: qsTr("Choose music folder")
                        onClicked: picker.open()
                    }
                    FolderPicker { id: picker }
                }
            }

            // Home's sections, in the order chosen (Settings → Features → Home, or a section's own menu); the random
            // album and the listening card sit side by side when they're next to each other and there's room
            Flow {
                id: sections
                objectName: "homeSections"
                visible: library.trackCount > 0
                width: parent.width
                spacing: 24
                Repeater {
                    model: page.shown
                    Item {
                        id: slot
                        required property string modelData
                        required property int index
                        objectName: "homeSection_" + modelData
                        width: page.half(modelData) ? (col.width - sections.spacing) / 2 : col.width
                        height: loader.item ? loader.item.implicitHeight || loader.item.height : 0
                        Loader {
                            id: loader
                            width: parent.width
                            sourceComponent: page.componentFor(slot.modelData)
                        }
                        // right-click anywhere on a section that isn't a card: its menu (move, hide, customize)
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: page.sectionMenu(slot.modelData)
                        }
                        // the cards with no heading of their own: their ⋯ in the corner while pointed at
                        HoverHandler { id: slotHover }
                        IconButton {
                            readonly property bool headless: ["random", "listening", "facts"].indexOf(slot.modelData) >= 0
                            objectName: "homeSectionMenu_" + slot.modelData
                            visible: headless && (slotHover.hovered || activeFocus)
                            anchors { top: parent.top; right: parent.right; margins: 4 }
                            z: 5
                            icon: "more"
                            size: 16
                            tip: qsTr("Options for this section")
                            onClicked: page.sectionMenu(slot.modelData)
                        }
                    }
                }
            }
        }
    }

    // --- the sections ------------------------------------------------------------------------------------
    readonly property var titles: ({
        random: qsTr("Random album"), listening: qsTr("Listening"), facts: qsTr("Library facts"),
        jumpBackIn: qsTr("Jump back in"), mixes: qsTr("Today's mixes"), recent: qsTr("Recently added"),
        playlists: qsTr("Your playlists"), mostPlayed: qsTr("Most played lately"), continue: qsTr("Continue listening"),
        stations: qsTr("Your stations"), rediscover: qsTr("Rediscover"), onThisDay: qsTr("On this day") })
    readonly property bool hasPodcasts: typeof podcasts !== "undefined" && shell.features.podcasts !== false
    readonly property bool hasStations: typeof stations !== "undefined" && shell.features.stations !== false
    readonly property bool hasMixes: typeof discover !== "undefined" && shell.features.discover !== false
                                     && shell.features.discoverMixes !== false
    // Rediscover and On this day are off unless chosen (Discover has fuller ones); the rest are on unless switched off
    function sectionOn(id) {
        var f = shell.homeFeatures[id]
        if (id === "rediscover" || id === "onThisDay") return shell.features[f] === true
        if (shell.features[f] === false) return false
        if (id === "mixes") return hasMixes
        if (id === "continue") return hasPodcasts
        if (id === "stations") return hasStations
        return true
    }
    // (a section with nothing to show yet isn't shown: no heading over an empty shelf)
    function hasContent(id) {
        switch (id) {
        case "jumpBackIn": return userLib.recentPlayed.count > 0
        case "mixes": return discover.mixes.length > 0
        case "recent": return library.recentAlbums.count > 0
        case "playlists": return page.playlists.length > 0
        case "mostPlayed": return userLib.homeTopAlbums.count > 0
        case "continue": return podcasts.inProgress.count > 0
        case "stations": return stations.model.count > 0
        case "rediscover": return userLib.rediscover.count > 0
        case "onThisDay": return userLib.onThisDay.count > 0
        }
        return true
    }
    readonly property var shown: {
        // (read here so the list follows them)
        var deps = [shell.features, userLib.recentPlayed.count, library.recentAlbums.count, page.playlists.length,
                    userLib.homeTopAlbums.count, userLib.rediscover.count, userLib.onThisDay.count,
                    hasMixes ? discover.mixes.length : 0, hasPodcasts ? podcasts.inProgress.count : 0,
                    hasStations ? stations.model.count : 0]
        return shell.homeOrder.filter(function (id) { return page.sectionOn(id) && page.hasContent(id) })
    }
    function half(id) {
        if ((id !== "random" && id !== "listening") || col.width < 860) return false
        var i = shown.indexOf(id), other = id === "random" ? "listening" : "random"
        return shown[i - 1] === other || shown[i + 1] === other
    }
    readonly property var playlists: (userLib.home.playlists || []).filter(function (p) { return p.id >= 0 || shell.features.liked !== false })
    onHasMixesChanged: if (hasMixes && sectionOn("mixes")) discover.open()

    function componentFor(id) {
        switch (id) {
        case "random": return randomSection
        case "listening": return listeningSection
        case "facts": return factsSection
        case "jumpBackIn": return jumpBackInSection
        case "mixes": return mixesSection
        case "recent": return recentSection
        case "playlists": return playlistsSection
        case "mostPlayed": return mostPlayedSection
        case "continue": return continueSection
        case "stations": return stationsSection
        case "rediscover": return rediscoverSection
        case "onThisDay": return onThisDaySection
        }
        return null
    }
    function move(id, step) { shell.moveHomeSectionAmong(id, step, shown) }
    function hide(id) {
        var f = shell.homeFeatures[id]
        shell.setFeature(f, false)
        Nav.notifyAction(qsTr("“%1” hidden. Settings → Features → Home brings it back").arg(titles[id]), qsTr("Undo"),
                         function () { shell.setFeature(f, true) })
    }
    function customize() { Nav.openSettingsAt("home") }  // Settings → Features → Home
    property string menuFor: ""
    function sectionMenu(id) { menuFor = id; sectionMenuPopup.popup() }
    Menu {
        id: sectionMenuPopup
        objectName: "homeSectionMenu"
        MenuItem {
            objectName: "homeSectionUp"
            text: qsTr("Move up"); icon.name: "up"
            enabled: page.shown.indexOf(page.menuFor) > 0
            onTriggered: page.move(page.menuFor, -1)
        }
        MenuItem {
            objectName: "homeSectionDown"
            text: qsTr("Move down"); icon.name: "down"
            enabled: page.shown.indexOf(page.menuFor) < page.shown.length - 1
            onTriggered: page.move(page.menuFor, 1)
        }
        MenuItem { objectName: "homeSectionHide"; text: qsTr("Hide this section"); icon.name: "close"; onTriggered: page.hide(page.menuFor) }
        MenuSeparator {}
        MenuItem { objectName: "homeCustomize"; text: qsTr("Customize Home…"); icon.name: "settings"; onTriggered: page.customize() }
    }
    MixPreview { id: mixPreview }
    // The right-click menus of Home's own cards (an album card brings its usual menu with it)
    Menu {
        id: cardMenu
        objectName: "homePlaylistMenu"
        property var playlist: ({})
        MenuItem { text: qsTr("Play"); icon.name: "play"; onTriggered: userLib.playPlaylistById(cardMenu.playlist.id, false) }
        MenuItem { text: qsTr("Shuffle"); icon.name: "shuffle"; onTriggered: userLib.playPlaylistById(cardMenu.playlist.id, true) }
        MenuItem {
            text: qsTr("Open"); icon.name: "playlist"
            onTriggered: cardMenu.playlist.id < 0 ? Nav.openLiked() : Nav.openPlaylist(cardMenu.playlist.id)
        }
    }
    Menu {
        id: stationCardMenu
        objectName: "homeStationMenu"
        property int stationId: -1
        MenuItem { text: qsTr("Play"); icon.name: "play"; onTriggered: stations.play(stationCardMenu.stationId) }
        MenuItem { text: qsTr("Play next"); icon.name: "next"; onTriggered: stations.playNext(stationCardMenu.stationId) }
        MenuItem { text: qsTr("Go to Internet radio"); icon.name: "radio"; onTriggered: Nav.openPage("stations") }
    }
    Loader { id: episodeMenuLoader; active: page.hasPodcasts; sourceComponent: Component { EpisodeMenu {} } }

    // A shelf's heading: its title, a line under it, "See all" where there's a page for more, and its menu
    component ShelfHeader: Item {
        id: head
        property string section
        property string subtitle
        property string seeAll  // the page with more of it ("" for none)
        width: parent ? parent.width : 0
        implicitHeight: Math.max(titleBlock.implicitHeight, 34)
        SectionHeader {
            id: titleBlock
            anchors { left: parent.left; right: tools.left; rightMargin: 12; verticalCenter: parent.verticalCenter }
            title: page.titles[head.section]
            subtitle: head.subtitle
        }
        Row {
            id: tools
            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
            spacing: 6
            Text {
                textFormat: Text.PlainText
                anchors.verticalCenter: parent.verticalCenter
                visible: head.seeAll.length > 0 && shell.features[head.seeAll] !== false
                text: qsTr("See all")
                color: seeAllMouse.containsMouse ? Theme.accentHi : Theme.accent
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold
                LinkArea { id: seeAllMouse; name: qsTr("See all: %1").arg(page.titles[head.section]); hoverEnabled: true; onClicked: Nav.openPage(head.seeAll) }
            }
            IconButton {
                objectName: "homeSectionMenu_" + head.section
                icon: "more"
                tip: qsTr("Options for this section")
                onClicked: page.sectionMenu(head.section)
            }
        }
    }

    // A row of cards that scrolls sideways, under its heading
    component Shelf: Column {
        id: shelfBox
        width: parent ? parent.width : 0  // (the Loader's: its slot's width from the start)
        property string section
        property string subtitle
        property string seeAll
        property alias model: row.model
        property alias delegate: row.delegate
        spacing: 14
        ShelfHeader { id: shelfHead; section: shelfBox.section; subtitle: shelfBox.subtitle; seeAll: shelfBox.seeAll }
        Item {
            width: parent.width
            height: 262
            ListView {
                WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
                id: row
                objectName: "homeShelf_" + shelfBox.section
                anchors.fill: parent
                // room around the cards for a hovered cover's lift and glow, which the clip would cut off (#110)
                anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                topMargin: 14; leftMargin: 14; rightMargin: 14
                contentY: -topMargin  // (the cards sit below that room; a sideways list doesn't move them itself)
                orientation: ListView.Horizontal
                spacing: 20
                clip: true
                boundsBehavior: Flickable.StopAtBounds
            }
            ShelfArrows { row: row; anchors.fill: parent }
        }
    }
    component AlbumShelf: Shelf {
        delegate: AlbumCard {
            required property var model
            required property int index
            albumKey: model.album_key
            title: model.album
            subtitle: model.album_artist
            artist: model.album_artist
            artUrl: model.artUrl
            note: model.reason || (model.plays ? Theme.counted(qsTr("%n play(s)", "", model.plays), model.plays) : "")
            selectionSource: ListView.view ? ListView.view.model : null
            rowIndex: index
        }
    }

    Component {
        id: randomSection
        RandomAlbumCard { width: parent ? parent.width : 0; album: page.pick; onReroll: page.reroll() }
    }
    Component {
        id: listeningSection
        ListeningCard { width: parent ? parent.width : 0 }
    }
    Component {
        id: factsSection
        FactsRow {}
    }
    Component {
        id: jumpBackInSection
        AlbumShelf { section: "jumpBackIn"; subtitle: qsTr("Albums you've played lately"); seeAll: "history"; model: userLib.recentPlayed }
    }
    Component {
        id: recentSection
        AlbumShelf { section: "recent"; subtitle: qsTr("New on your shelves"); seeAll: "albums"; model: library.recentAlbums }
    }
    Component {
        id: mostPlayedSection
        AlbumShelf { section: "mostPlayed"; subtitle: qsTr("Your most played albums this month"); seeAll: "stats"; model: userLib.homeTopAlbums }
    }
    Component {
        id: rediscoverSection
        AlbumShelf { section: "rediscover"; subtitle: qsTr("Albums you haven't played in a while, or ever"); seeAll: "discover"; model: userLib.rediscover }
    }
    Component {
        id: onThisDaySection
        AlbumShelf { section: "onThisDay"; subtitle: qsTr("What you were listening to around this date in past years"); seeAll: "discover"; model: userLib.onThisDay }
    }
    Component {
        id: mixesSection
        Shelf {
            section: "mixes"; subtitle: qsTr("Made from your library, new each day"); seeAll: "discover"
            model: discover.mixes
            delegate: MosaicCard {
                required property var modelData
                required property int index
                objectName: "homeMix_" + index
                arts: modelData.arts
                title: modelData.title
                subtitle: modelData.subtitle
                onOpened: discover.mixClick === "play" ? discover.playMix(index, false) : mixPreview.show(index)
                onPlay: discover.playMix(index, false)
                onMenu: mixPreview.show(index)
            }
        }
    }
    Component {
        id: playlistsSection
        Shelf {
            section: "playlists"
            subtitle: shell.features.liked !== false ? qsTr("Liked Songs and the playlists you've added to lately") : qsTr("The playlists you've added to lately")
            model: page.playlists
            delegate: MosaicCard {
                required property var modelData
                objectName: "homePlaylist_" + modelData.id
                arts: modelData.arts
                title: modelData.id < 0 ? qsTr("Liked Songs") : modelData.name
                subtitle: Theme.counted(qsTr("%n song(s)", "", modelData.n), modelData.n)
                fallback: modelData.id < 0 ? "♥" : "♪"
                onOpened: modelData.id < 0 ? Nav.openLiked() : Nav.openPlaylist(modelData.id)
                onPlay: userLib.playPlaylistById(modelData.id, false)
                onMenu: { cardMenu.playlist = modelData; cardMenu.popup() }
            }
        }
    }
    Component {
        id: continueSection
        Shelf {
            section: "continue"; subtitle: qsTr("Podcast episodes you've started"); seeAll: "podcasts"
            model: podcasts.inProgress
            delegate: MosaicCard {
                required property var model
                required property int index
                arts: model.artUrl ? [model.artUrl] : []
                title: model.title
                subtitle: model.podcast + (model.progress > 0 ? "  ·  " + qsTr("%1% heard").arg(Math.round(model.progress * 100)) : "")
                onOpened: Nav.openPodcast(model.podcast_id)
                onPlay: podcasts.play(model.id)
                onMenu: if (episodeMenuLoader.item) episodeMenuLoader.item.showFor(podcasts.inProgress.get(index), true)
            }
        }
    }
    Component {
        id: stationsSection
        Shelf {
            section: "stations"; subtitle: qsTr("Internet radio you've saved"); seeAll: "stations"
            model: stations.model
            delegate: MosaicCard {
                required property var model
                arts: model.artUrl ? [model.artUrl] : []
                title: model.name
                subtitle: [model.country, (model.tags || "").split(",")[0]].filter(function (x) { return x }).join("  ·  ")
                fallback: "📻"
                onOpened: stations.play(model.id)
                onPlay: stations.play(model.id)
                onMenu: { stationCardMenu.stationId = model.id; stationCardMenu.popup() }
            }
        }
    }

    component Fact: GlassPanel {
        property string value
        property string label
        Column {
            anchors { left: parent.left; right: parent.right; leftMargin: 20; rightMargin: 12; verticalCenter: parent.verticalCenter }
            spacing: 4
            Text { width: parent.width; elide: Text.ElideRight; text: value; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(21)) * Theme.displayScale; font.weight: Font.Bold; textFormat: Text.PlainText }
            Text { width: parent.width; elide: Text.ElideRight; text: label; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); textFormat: Text.PlainText }
        }
    }
    // What your collection holds: four across, or two by two when the window is narrow
    component FactsRow: Grid {
        id: factRow
        objectName: "factRow"
        width: parent ? parent.width : 0
        columns: width >= 760 ? 4 : 2
        spacing: 14
        readonly property real tileWidth: Math.max(0, (width - (columns - 1) * spacing) / columns)
        // every tile as tall as the format legend needs, so a wrapped legend stays inside its card
        readonly property real tileHeight: Math.max(96, formatsColumn.implicitHeight + 36)
        readonly property var heat: userLib.home.heatmap || ({})
        // plays over the last seven days (today among them)
        readonly property int week: {
            var days = heat.days || [], end = heat.today !== undefined ? heat.today : days.length - 1, n = 0
            for (var i = Math.max(0, end - 6); i <= end && i < days.length; i++) n += days[i]
            return n
        }
        Fact { objectName: "factWeek"; width: factRow.tileWidth; height: factRow.tileHeight; value: Theme.num(factRow.week); label: qsTr("plays this week") }
        Fact { width: factRow.tileWidth; height: factRow.tileHeight; value: page.facts.bytes ? Theme.fmtBytes(page.facts.bytes) : "–"; label: qsTr("on disk") }
        Fact { width: factRow.tileWidth; height: factRow.tileHeight; value: page.facts.tracks ? Math.round(page.facts.lossless * 100) + "%" : "–"; label: qsTr("lossless") }
        GlassPanel {
            id: formatsTile
            objectName: "formatsTile"
            width: factRow.tileWidth; height: factRow.tileHeight
            readonly property var formats: page.facts.formats || []
            readonly property var swatches: [Theme.accent, Theme.art1, Theme.art2, Theme.accentHi, Theme.textDim]
            Column {
                id: formatsColumn
                anchors { left: parent.left; right: parent.right; margins: 18; verticalCenter: parent.verticalCenter }
                spacing: 10
                Row {
                    id: formatsBar
                    width: parent.width
                    height: 10
                    spacing: 2
                    clip: true
                    Repeater {
                        model: formatsTile.formats
                        Rectangle {
                            required property var modelData
                            required property int index
                            width: Math.max(3, (formatsBar.width - formatsBar.spacing * (formatsTile.formats.length - 1)) * modelData.share)
                            height: 10
                            radius: 5
                            color: formatsTile.swatches[index % 5]
                        }
                    }
                }
                Flow {
                    width: parent.width
                    spacing: 10
                    Repeater {
                        model: formatsTile.formats
                        Row {
                            required property var modelData
                            required property int index
                            spacing: 5
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: formatsTile.swatches[index % 5] }
                            Text { text: modelData.name + " " + Math.round(modelData.share * 100) + "%"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); textFormat: Text.PlainText }
                        }
                    }
                }
            }
        }
    }
}
