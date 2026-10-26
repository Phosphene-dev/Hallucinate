import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import "."

// An artist: their picture lit by its own colours, how you've listened to them, their most played songs, the
// discography by year, records they appear on, and every song.
Item {
    id: page
    objectName: "artist"
    property string artistName
    // Pages kept underneath for Back catch up when they're shown again: refreshing them all on every rescan
    // would make each reload wait on queries for pages nobody is looking at.
    readonly property bool shown: StackView.status === StackView.Active || StackView.status === StackView.Activating
                                  || StackView.view === null
    property int revision: 0  // bumped to read the page again
    property int seenRevision: -1  // the library's revision the page last read
    function catchUp() {
        if (seenRevision !== library.detailRevision) { seenRevision = library.detailRevision; revision++ }
    }
    Component.onCompleted: seenRevision = library.detailRevision
    Connections {
        target: library
        function onDetailChanged() { if (page.shown) page.catchUp() }
    }
    onShownChanged: if (shown) catchUp()
    readonly property var info: page.revision >= 0 ? library.artistInfo(artistName) : ({})
    readonly property var profile: page.revision >= 0 ? library.artistProfile(artistName) : ({})
    readonly property var coverColors: page.revision >= 0 ? library.artistPalette(artistName) : []
    readonly property var tracksModel: page.revision >= 0 ? library.artistTracksModel(artistName) : null
    readonly property color glow0: coverColors.length > 0 ? coverColors[0] : Theme.accent
    readonly property color glow1: coverColors.length > 1 ? coverColors[1] : Theme.art1
    readonly property var months: profile.months || []
    readonly property int monthMax: Math.max(1, ...months.map(m => m.plays))
    property bool allSongs: false

    function fmtDate(ts) { return ts > 0 ? Qt.formatDate(new Date(ts * 1000), "d MMM yyyy") : "" }
    function plural(n, one, many) { return n + " " + (n === 1 ? one : many) }
    function yearsActive() {
        var a = profile.firstYear || 0, b = profile.lastYear || 0
        return a && b ? (a === b ? String(a) : a + "–" + b) : ""
    }

    component Bloom: Shape {
        readonly property bool decoration: true  // a glow, meant to spill past edges
        id: bloom
        property color tint
        property real size: 680
        width: size; height: size
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeWidth: 0; strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: bloom.size / 2; centerY: bloom.size / 2; centerRadius: bloom.size / 2
                focalX: bloom.size / 2; focalY: bloom.size / 2
                GradientStop { position: 0; color: Qt.rgba(bloom.tint.r, bloom.tint.g, bloom.tint.b, Theme.light ? 0.22 : 0.32) }
                GradientStop { position: 1; color: Qt.rgba(bloom.tint.r, bloom.tint.g, bloom.tint.b, 0) }
            }
            PathRectangle { x: 0; y: 0; width: bloom.size; height: bloom.size }
        }
    }

    component Stat: Column {
        property string value
        property string label
        spacing: 2
        Text {
            textFormat: Text.PlainText
            text: parent.value
            color: Theme.text
            font.family: Theme.displayFamily
            font.pixelSize: (Theme.fontSize(20)) * Theme.displayScale
            font.weight: Font.Bold
        }
        Text {
            textFormat: Text.PlainText
            text: parent.label
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(11)
        }
    }

    RoundClip {  // the photo's glow behind the page ends in rounded corners, like the panels around it
        anchors.fill: parent
        Flickable {
            id: fl
            objectName: "artistFlick"
            anchors.fill: parent
            contentWidth: width
            contentHeight: col.height + 40
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}

            Bloom { tint: page.glow0; x: Theme.contentX(fl.width) + 110 - size / 2; y: 24 + 110 - size / 2 }
            Bloom { tint: page.glow1; size: 520; x: fl.width * 0.55 - size / 2; y: -size / 3 }

            Column {
                id: col
                x: Theme.contentX(fl.width); y: 24
                width: Theme.contentWidth(fl.width)
                spacing: 26

                // Header
                Row {
                    spacing: 30
                    Item {
                        width: 220; height: 220
                        Repeater {
                            model: 6
                            Rectangle {
                                required property int index
                                anchors { fill: parent; margins: -(index + 1) * 3; topMargin: -(index + 1) * 3 + 8 }
                                radius: width / 2
                                color: "transparent"
                                border.width: 3
                                border.color: Qt.rgba(0, 0, 0, (Theme.light ? 0.06 : 0.12) - index * 0.015)
                            }
                        }
                        Cover {
                            objectName: "artistPicture"
                            anchors.fill: parent
                            radius: width / 2
                            source: page.info.artUrl || ""
                            fallback: (page.artistName || "?").charAt(0)
                        }
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        width: col.width - 250
                        spacing: 8
                        Text {
                            textFormat: Text.PlainText
                            text: "ARTIST"
                            color: Theme.accent
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSize(11)
                            font.weight: Font.DemiBold
                            font.letterSpacing: 1.6
                        }
                        Text {
                            textFormat: Text.PlainText
                            width: parent.width
                            text: page.artistName
                            color: Theme.text
                            font.family: Theme.displayFamily
                            font.pixelSize: (Theme.fontSize(page.artistName.length > 24 ? 28 : 38)) * Theme.displayScale
                            font.weight: Font.Bold
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                        Text {
                            textFormat: Text.PlainText
                            objectName: "artistFacts"
                            width: parent.width
                            text: [page.plural(page.profile.albums || 0, "album", "albums"),
                                   page.plural(page.profile.tracks || 0, "song", "songs"),
                                   page.profile.seconds ? Theme.fmtHours(page.profile.seconds) : "",
                                   page.yearsActive()].filter(s => s).join("  ·  ")
                            color: Theme.textDim
                            wrapMode: Text.Wrap
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSize(14)
                        }
                        GenreLinks {
                            objectName: "artistGenres"
                            width: parent.width
                            names: (page.profile.genres || []).slice(0, shell.allGenresAlbums ? 3 : 1)
                            color: Theme.textDim
                        }
                        Flow {  // wraps beside a big photo in a narrow window
                            width: parent.width
                            spacing: 10
                            topPadding: 10
                            PillButton { primary: true; text: "Play all"; onClicked: library.playArtist(page.artistName, false) }
                            PillButton {
                                text: "Shuffle"
                                onClicked: { player.setShuffle(true); library.playArtist(page.artistName, true) }
                            }
                            PillButton {
                                objectName: "artistRadio"
                                text: "Radio"
                                onClicked: library.startArtistRadio(page.artistName)
                            }
                            IconButton {
                                id: artistMoreButton
                                objectName: "artistPageMore"
                                height: 38
                                icon: "more"; size: 18; tip: "More: play next, add to a playlist, remove…"
                                onClicked: Nav.artistMenu(page.artistName)
                            }
                        }
                    }
                }

                // About them: your own bio if you've written one, else one looked up online
                GlassPanel {
                    id: about
                    objectName: "artistAbout"
                    width: col.width
                    height: aboutCol.implicitHeight + 36
                    property int bioRevision: 0
                    readonly property var bio: about.bioRevision >= 0 && page.artistName ? artistBios.bio(page.artistName) : ({})
                    property bool editing: false
                    property bool expanded: false
                    function startEditing() { bioEdit.text = about.bio.text || ""; about.editing = true; bioEdit.forceActiveFocus() }
                    Connections {
                        target: artistBios
                        function onChanged(key) { about.bioRevision++ }
                    }
                    Component.onCompleted: if (page.artistName) artistBios.ensure(page.artistName)
                    Column {
                        id: aboutCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 18 }
                        spacing: 10
                        Flow {
                            width: parent.width
                            spacing: 10
                            Text {
                                textFormat: Text.PlainText
                                height: 32; verticalAlignment: Text.AlignVCenter
                                text: "About"
                                color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(18)) * Theme.displayScale; font.weight: Font.DemiBold
                            }
                            Text {
                                textFormat: Text.PlainText
                                objectName: "bioSource"
                                height: 32; verticalAlignment: Text.AlignVCenter
                                visible: text.length > 0 && !about.editing
                                text: about.bio.own ? "written by you" : (about.bio.source ? "from " + about.bio.source : "")
                                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                                font.underline: !about.bio.own && sourceMouse.containsMouse
                                MouseArea {
                                    id: sourceMouse
                                    anchors.fill: parent
                                    enabled: !about.bio.own && /^https?:\/\//.test(about.bio.url || "")
                                    hoverEnabled: true
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: Qt.openUrlExternally(about.bio.url)
                                }
                            }
                            IconButton {
                                id: bioMenuButton
                                objectName: "bioMenuButton"
                                visible: !about.editing
                                height: 32
                                icon: "more"; size: 16; tip: "Bio options: write your own, look up again, choose the source"
                                onClicked: bioMenu.popup(bioMenuButton, 0, bioMenuButton.height + 4)
                            }
                            Menu {
                                id: bioMenu
                                objectName: "bioMenu"
                                MenuItem {
                                    objectName: "editBio"
                                    text: about.bio.own ? "Edit your bio" : "Write your own"
                                    icon.name: "edit"
                                    onTriggered: about.startEditing()
                                }
                                MenuItem {
                                    objectName: "refreshBio"
                                    visible: !about.bio.own
                                    height: visible ? implicitHeight : 0
                                    enabled: !shell.offlineMode && !about.bio.busy
                                    text: about.bio.text ? "Look up again" : "Look one up"
                                    icon.name: "search"
                                    onTriggered: artistBios.refresh(page.artistName)
                                }
                                MenuItem {
                                    objectName: "clearBioMenu"
                                    visible: about.bio.own === true
                                    height: visible ? implicitHeight : 0
                                    text: "Remove yours, use the one found online"
                                    icon.name: "remove"
                                    onTriggered: { artistBios.setOwn(page.artistName, ""); artistBios.ensure(page.artistName) }
                                }
                                Menu {
                                    id: bioSourceMenu
                                    objectName: "bioPick"
                                    title: "Bio from"
                                    icon.name: "artist"
                                    Repeater {
                                        model: [["", "Usual sources"], ["Wikipedia", "Wikipedia"],
                                                ["Last.fm", "Last.fm" + (sources.lastfmAvailable ? "" : " (not set up)")],
                                                ["Discogs", "Discogs" + (sources.discogsConnected ? "" : " (not set up)")]]
                                        MenuItem {
                                            required property var modelData
                                            text: modelData[1]
                                            checkable: true
                                            checked: (about.bio.picked || "") === modelData[0]
                                            enabled: modelData[0] === "" || modelData[0] === "Wikipedia"
                                                     || (modelData[0] === "Last.fm" ? sources.lastfmAvailable : sources.discogsConnected)
                                            onTriggered: artistBios.pick(page.artistName, modelData[0])
                                        }
                                    }
                                }
                            }
                        }
                        Text {
                            textFormat: Text.PlainText
                            objectName: "bioText"
                            width: parent.width
                            TapHandler {  // right-click the bio for the same options as ⋯
                                acceptedButtons: Qt.RightButton
                                onTapped: bioMenu.popup()
                            }
                            visible: !about.editing
                            text: about.bio.text ? about.bio.text
                                  : about.bio.busy ? "Looking for a bio…"
                                  : shell.offlineMode ? "No bio yet. Offline mode is on, so none can be looked up."
                                  : "No bio yet. Write your own, or look one up, from the ⋯ menu."
                            color: about.bio.text ? Theme.text : Theme.textDim
                            wrapMode: Text.Wrap
                            maximumLineCount: about.expanded ? 400 : 6
                            elide: Text.ElideRight
                            lineHeight: 1.15
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                        }
                        PillButton {
                            objectName: "bioMore"
                            visible: !about.editing && (about.bio.text || "").length > 0 && (about.expanded || bioMeasure.lineCount > 6)
                            height: 30
                            text: about.expanded ? "Show less" : "Show more"
                            onClicked: about.expanded = !about.expanded
                        }
                        Text {  // the whole bio laid out unseen, to tell whether "Show more" has anything to show
                            id: bioMeasure
                            visible: false
                            width: parent.width
                            textFormat: Text.PlainText
                            text: about.bio.text || ""
                            wrapMode: Text.Wrap
                            lineHeight: 1.15
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                        }
                        ScrollView {
                            visible: about.editing
                            width: parent.width
                            height: Math.min(320, Math.max(140, bioEdit.implicitHeight))
                            TextArea {
                                id: bioEdit
                                objectName: "bioEdit"
                                wrapMode: TextArea.Wrap
                                selectByMouse: true
                                placeholderText: "Write about " + page.artistName
                                placeholderTextColor: Theme.textDim
                                color: Theme.text
                                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                                background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: bioEdit.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                                Accessible.name: "Bio for " + page.artistName
                                Keys.onEscapePressed: about.editing = false
                            }
                        }
                        Flow {
                            visible: about.editing
                            width: parent.width
                            spacing: 10
                            PillButton {
                                objectName: "saveBio"
                                primary: true; height: 32; text: "Save"
                                onClicked: { artistBios.setOwn(page.artistName, bioEdit.text); about.editing = false }
                            }
                            PillButton { height: 32; text: "Cancel"; onClicked: about.editing = false }
                            PillButton {
                                objectName: "clearBio"
                                visible: about.bio.own
                                height: 32
                                text: "Remove mine, use the one found online"
                                onClicked: { artistBios.setOwn(page.artistName, ""); about.editing = false; artistBios.ensure(page.artistName) }
                            }
                        }
                    }
                }

                // Your listening
                GlassPanel {
                    objectName: "artistListening"
                    width: col.width
                    height: 128
                    Row {
                        anchors { left: parent.left; leftMargin: 22; verticalCenter: parent.verticalCenter }
                        spacing: parent.width < 640 ? 16 : 36  // closer together in a narrow page, so the last one fits
                        Stat {
                            value: page.profile.plays ? page.profile.plays : "—"
                            label: page.profile.plays === 1 ? "play" : "plays"
                        }
                        Stat {
                            value: page.profile.listenSeconds ? (page.profile.listenSeconds >= 3600 ? Theme.fmtHours(page.profile.listenSeconds)
                                                                 : Math.round(page.profile.listenSeconds / 60) + " min") : "—"
                            label: "listened"
                        }
                        Stat {
                            visible: (page.profile.rank || 0) > 0
                            value: "#" + page.profile.rank
                            label: "among your artists"
                        }
                        Stat {
                            visible: (page.profile.firstPlayed || 0) > 0
                            value: page.fmtDate(page.profile.firstPlayed)
                            label: "first listen"
                        }
                    }
                    // plays per month, last 12 months
                    Row {
                        anchors { right: parent.right; rightMargin: 22; bottom: parent.bottom; bottomMargin: 26 }
                        spacing: 4
                        Repeater {
                            model: page.months
                            Column {
                                required property var modelData
                                spacing: 4
                                Item {
                                    width: 12; height: 56
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    width: 12
                                    height: Math.max(3, 56 * modelData.plays / page.monthMax)
                                    radius: 3
                                    color: modelData.plays ? Theme.accent : Theme.stroke
                                    opacity: modelData.plays ? 0.45 + 0.55 * modelData.plays / page.monthMax : 1
                                    HoverHandler { id: barHover }
                                    ToolTip.visible: barHover.hovered
                                    ToolTip.text: Qt.formatDate(new Date(modelData.month + "-15"), "MMMM yyyy") + ": "
                                                  + page.plural(modelData.plays, "play", "plays")
                                }
                                }
                                Text {
                                    textFormat: Text.PlainText
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: Qt.formatDate(new Date(modelData.month + "-15"), "MMM").charAt(0)
                                    color: Theme.textDim
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSize(9)
                                }
                            }
                        }
                    }
                }

                // Most played
                Column {
                    width: col.width
                    spacing: 4
                    visible: (page.profile.topTracks || []).length > 0
                    SectionHeader { title: page.profile.plays ? "Most played" : "Songs to start with" }
                    Item { width: 1; height: 6 }
                    Repeater {
                        model: page.profile.topTracks || []
                        TrackRow {
                            selectionSource: page.profile.topTracks || []
                            required property var modelData
                            required property int index
                            rowIndex: index
                            context: "artist"
                            width: col.width
                            number: index + 1
                            path: modelData.path
                            title: modelData.title
                            artist: modelData.plays ? page.plural(modelData.plays, "play", "plays") : modelData.album
                            linkArtist: false  // the line holds plays, not the artist
                            album: modelData.album
                            showAlbum: false
                            durText: modelData.durText
                            artUrl: modelData.artUrl || ""
                            audioFormat: modelData.codec || modelData.fmt || ""
                            bitDepth: modelData.bit_depth || 0
                            sampleRate: modelData.sample_rate || 0
                            explicitTag: modelData.explicit || 0
                            audioBitrate: modelData.bitrate || 0
                            current: Rows.currentPath === modelData.path
                            onActivated: player.playList(page.profile.topTracks, index)
                            onEnqueue: player.enqueue(modelData)
                        }
                    }
                }

                // Discography by year
                Column {
                    width: col.width
                    spacing: 14
                    visible: (page.profile.discography || []).length > 0
                    SectionHeader { title: "Discography"; subtitle: page.yearsActive() }
                    Repeater {
                        model: page.profile.discography || []
                        Item {
                            id: yearRow
                            required property var modelData
                            width: col.width
                            height: yearFlow.height + 8
                            Rectangle { x: 6; width: 2; height: parent.height; color: Theme.stroke }
                            Rectangle {
                                x: 1; y: 8; width: 12; height: 12; radius: Theme.round(6)
                                color: Theme.accent
                                border.width: 3; border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.3)
                            }
                            Text {
                                textFormat: Text.PlainText
                                x: 24; y: 3
                                text: yearRow.modelData.year > 0 ? yearRow.modelData.year : "—"
                                color: Theme.text
                                font.family: Theme.displayFamily
                                font.pixelSize: (Theme.fontSize(15)) * Theme.displayScale
                                font.weight: Font.DemiBold
                            }
                            Flow {
                                id: yearFlow
                                x: 90
                                width: parent.width - x
                                spacing: 18
                                Repeater {
                                    model: yearRow.modelData.albums
                                    AlbumCard {
                                        required property var modelData
                                        cardWidth: 160
                                        albumKey: modelData.album_key
                                        title: modelData.album
                                        artist: page.artistName
                                        subtitle: modelData.n + (modelData.n === 1 ? " song" : " songs") + "  ·  " + modelData.durText
                                        artUrl: modelData.artUrl
                                    }
                                }
                            }
                        }
                    }
                }

                // On other people's records
                Column {
                    width: col.width
                    spacing: 12
                    visible: (page.profile.appearsOn || []).length > 0
                    SectionHeader { title: "Appears on" }
                    Flow {
                        width: col.width
                        spacing: 18
                        Repeater {
                            model: page.profile.appearsOn || []
                            AlbumCard {
                                required property var modelData
                                cardWidth: 160
                                albumKey: modelData.album_key
                                title: modelData.album
                                artist: modelData.album_artist || ""  // someone else's record: its menu goes to them
                                subtitle: (modelData.year > 0 ? modelData.year + "  ·  " : "") + modelData.album_artist
                                artUrl: modelData.artUrl
                            }
                        }
                    }
                }

                // Similar artists (Last.fm): those you have, to go to or mix with this one; the rest to discover
                Column {
                    id: similarBox
                    objectName: "similarArtists"
                    width: col.width
                    spacing: 12
                    property int revision: 0
                    readonly property var found: revision >= 0 && page.artistName ? similarArtists.similar(page.artistName) : ({})
                    readonly property var have: found.have || []
                    readonly property var discover: found.discover || []
                    visible: found.on === true && (found.busy || have.length > 0 || discover.length > 0)
                    Connections {
                        target: similarArtists
                        function onChanged(key) { similarBox.revision++ }
                    }
                    Connections {
                        target: library
                        function onChanged() { similarBox.revision++ }  // you may have some of them now
                    }
                    Component.onCompleted: if (page.artistName) similarArtists.ensure(page.artistName)
                    Row {
                        spacing: 14
                        SectionHeader {
                            title: "Similar artists"
                            subtitle: similarBox.found.busy ? "Asking Last.fm…" : "From Last.fm"
                        }
                        Text {
                            textFormat: Text.PlainText
                            objectName: "similarMix"
                            visible: similarBox.have.length > 0
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Play a mix"
                            color: Theme.accent
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSize(13)
                            font.weight: Font.DemiBold
                            LinkArea {
                                name: "Play a mix of " + page.artistName + " and similar artists you have"
                                onClicked: library.playArtistMix([page.artistName].concat(similarBox.have.map(function (a) { return a.name })))
                            }
                        }
                    }
                    Flow {
                        objectName: "similarHave"
                        visible: similarBox.have.length > 0
                        width: col.width
                        spacing: 18
                        Repeater {
                            model: similarBox.have.slice(0, 12)
                            ArtistCard {
                                required property var modelData
                                cardWidth: 130
                                name: modelData.name
                                subtitle: modelData.albums + (modelData.albums === 1 ? " album" : " albums")
                                artUrl: modelData.artUrl || ""
                            }
                        }
                    }
                    Text {
                        textFormat: Text.PlainText
                        visible: similarBox.discover.length > 0
                        text: similarBox.have.length ? "Not in your library" : "None of them are in your library yet"
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(12.5)
                    }
                    Flow {
                        objectName: "similarDiscover"
                        visible: similarBox.discover.length > 0
                        width: col.width
                        spacing: 8
                        Repeater {
                            model: similarBox.discover
                            Chip {
                                required property var modelData
                                text: modelData.name
                                onClicked: Qt.openUrlExternally(modelData.url)
                                Accessible.name: modelData.name + ", opens on Last.fm"
                            }
                        }
                    }
                }

                // Every song
                Column {
                    width: col.width
                    spacing: 4
                    Row {
                        spacing: 14
                        SectionHeader { title: "All songs" }
                        Text {
                            textFormat: Text.PlainText
                            anchors.verticalCenter: parent.verticalCenter
                            text: page.allSongs ? "Hide" : "Show " + page.tracksModel.count
                            color: Theme.accent
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSize(13)
                            font.weight: Font.DemiBold
                            LinkArea {
                                name: page.allSongs ? "Hide all songs" : "Show all " + page.tracksModel.count + " songs"
                                onClicked: page.allSongs = !page.allSongs
                            }
                        }
                    }
                    Repeater {
                        model: page.allSongs ? page.tracksModel : null
                        TrackRow {
                            selectionSource: page.allSongs ? page.tracksModel : null
                            path: model.path
                            audioFormat: model.codec
                            bitDepth: model.bit_depth || 0
                            sampleRate: model.sample_rate || 0
                            explicitTag: model.explicit || 0
                            audioBitrate: model.bitrate
                            rowIndex: index
                            context: "artist"
                            width: col.width
                            title: model.title
                            artist: model.artist
                            album: model.album
                            durText: model.durText
                            artUrl: model.artUrl
                            current: Rows.currentId === model.id
                            onActivated: player.playList(page.tracksModel.toList(), index)
                            onEnqueue: player.enqueue(page.tracksModel.get(index))
                        }
                    }
                }
            }
        }
    }
}
