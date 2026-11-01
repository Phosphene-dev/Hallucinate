import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import "."

// An album as a sleeve: the cover large, lit by its own colours, with liner notes (genre, format, discs, size,
// when it arrived and how you've listened to it) and the tracks split by disc.
Item {
    id: page
    // Ctrl+A with no row focused (main.qml): the page's list
    function selectAll() { Selection.selectAll(list.toString(), list.model, "song") }
    objectName: "album"
    property string albumKey
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
    // Everything on the page follows edits and rescans (a new cover, year or genre), not only the track list
    readonly property var info: page.revision >= 0 ? library.albumInfo(albumKey) : ({})
    readonly property var tracks: page.revision >= 0 ? library.albumTracksModel(albumKey) : null
    readonly property var notes: page.revision >= 0 ? library.albumNotes(albumKey) : ({})
    readonly property var coverColors: page.revision >= 0 ? library.albumPalette(albumKey) : []
    readonly property color glow0: coverColors.length > 0 ? coverColors[0] : Theme.accent
    readonly property color glow1: coverColors.length > 1 ? coverColors[1] : Theme.art1
    readonly property bool multiDisc: (notes.discs || 0) > 1

    function fmtDate(ts) { return ts > 0 ? Theme.date(new Date(ts * 1000), "short") : "" }
    function formatLine() {
        var parts = []
        if ((notes.formats || []).length) parts.push(notes.formats.join(" / "))
        if ((notes.bitDepths || []).length)
            parts.push(notes.bitDepths.map(function (b) { return b === 1 ? "DSD" : b + "-bit" }).join(" / "))  // i18n: keep
        if ((notes.sampleRates || []).length) {
            var r = notes.sampleRates.map(function (x) { return (x / 1000).toFixed(x % 1000 ? 1 : 0) })
            parts.push(r.join(" / ") + " kHz")  // i18n: keep
        }
        if (!notes.lossless && notes.bitrate > 0) parts.push(Math.round(notes.bitrate / 1000) + " kbps")  // i18n: keep
        return parts.join("  ·  ")
    }
    function listening() {
        if (!notes.plays) return qsTr("Not played yet")
        var s = Theme.counted(qsTr("%n play(s)", "", notes.plays), notes.plays)
        if (notes.firstPlayed) s += "  ·  " + qsTr("first %1", "the first time an album was played: a date").arg(fmtDate(notes.firstPlayed))
        if (notes.lastPlayed) s += "  ·  " + qsTr("last %1", "the last time an album was played: a date").arg(fmtDate(notes.lastPlayed))
        return s
    }

    component Note: Column {
        property string label
        property string value
        property var links: []
        property bool composers: false
        visible: value.length > 0
        spacing: 3
        width: Math.min(implicitWidth, 320)
        Text {
            textFormat: Text.PlainText
            text: parent.label.toUpperCase()
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(10)
            font.weight: Font.DemiBold
            font.letterSpacing: 1.2
        }
        Text {
            textFormat: Text.PlainText
            visible: parent.links.length === 0
            text: parent.value
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(13)
            elide: Text.ElideRight
            width: Math.min(implicitWidth, 320)
        }
        GenreLinks {  // genres: each opens its page
            visible: parent.links.length > 0
            names: parent.links
            composers: parent.composers
            pixelSize: Theme.fontSize(13)
            width: Math.min(implicitWidth, 320)
        }
    }

    RoundClip {  // the cover's glow behind the page ends in rounded corners, like the panels around it
        id: listClip
        anchors.fill: parent
        // centred on an ultrawide screen (see Theme.contentMax)
        readonly property real side: Math.max(0, (page.width - Theme.contentMax - 56) / 2)
        anchors.leftMargin: 20 + side; anchors.rightMargin: 8 + side
        ListView {
            WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
            id: list
            anchors.fill: parent
            readonly property real side: listClip.side
            boundsBehavior: Flickable.StopAtBounds
            model: page.tracks
            ScrollBar.vertical: ScrollBar {}

            KeepAtTop { target: list }  // stays at the top when the header changes height
            header: Item {
                width: list.width
                height: sleeve.height + notesPanel.height + 70

                Bloom { tint: page.glow0; x: sleeve.x + sleeve.width / 2 - size / 2; y: sleeve.y + sleeve.height / 2 - size / 2 }
                Bloom { tint: page.glow1; size: 520; x: sleeve.x + sleeve.width * 1.6 - size / 2; y: sleeve.y - size / 3 }

                Item {
                    id: sleeve
                    x: 8; y: 24
                    width: Math.min(300, list.width * 0.32); height: width
                    Repeater {  // soft shadow from stacked outlines (no effects needed)
                        model: 6
                        Rectangle {
                            required property int index
                            anchors { fill: parent; margins: -(index + 1) * 3; topMargin: -(index + 1) * 3 + 8 }
                            radius: 18 + (index + 1) * 3
                            color: "transparent"
                            border.width: 3
                            border.color: Qt.rgba(0, 0, 0, (Theme.light ? 0.06 : 0.12) - index * 0.015)
                        }
                    }
                    Cover {
                        objectName: "albumSleeve"
                        anchors.fill: parent
                        radius: Theme.round(18)
                        source: page.info.artUrl || ""
                        fallback: (page.info.album || "?").charAt(0)
                    }
                }
                Column {
                    anchors { left: sleeve.right; leftMargin: 30; right: parent.right; rightMargin: 20; bottom: sleeve.bottom }
                    spacing: 8
                    Text {
                        textFormat: Text.PlainText
                        text: qsTr("ALBUM")
                        color: Theme.accent
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(11)
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.6
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        text: page.info.album || ""
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: (Theme.fontSize(page.info.album && page.info.album.length > 28 ? 26 : 34)) * Theme.displayScale
                        font.weight: Font.Bold
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                    Row {
                        spacing: 6
                        Text {
                            textFormat: Text.PlainText
                            text: page.info.album_artist || ""
                            width: Math.min(implicitWidth, parent.parent.width * 0.6)  // a long artist list elides
                            elide: Text.ElideRight
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSize(16)
                            font.weight: Font.DemiBold
                            LinkArea {
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                onClicked: function (mouse) {
                                    mouse && mouse.button === Qt.RightButton ? Nav.artistMenu(page.info.album_artist) : Nav.openArtist(page.info.album_artist)
                                }
                            }
                        }
                        Text {
                            textFormat: Text.PlainText
                            text: "·  " + (page.info.year > 0 ? page.info.year + "  ·  " : "")
                                  + Theme.counted(qsTr("%n song(s)", "", page.info.n), page.info.n) + "  ·  " + page.info.durText
                            color: Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSize(14)
                        }
                    }
                    Row {
                        spacing: 10
                        topPadding: 10
                        PillButton {
                            objectName: "playAlbum"
                            primary: true
                            text: qsTr("Play")
                            onClicked: { player.setShuffle(false); player.playList(page.tracks.toList(), 0) }
                        }
                        PillButton {
                            text: qsTr("Shuffle")
                            onClicked: {
                                player.setShuffle(true)
                                player.playList(page.tracks.toList(), Math.floor(Math.random() * page.tracks.count))
                            }
                        }
                        PillButton { text: qsTr("Add to queue"); onClicked: player.enqueueAll(page.tracks.toList()) }
                        PillButton { text: qsTr("Edit"); onClicked: Nav.editAlbum(page.albumKey) }
                        IconButton {
                            objectName: "albumPageMore"
                            anchors.verticalCenter: parent.verticalCenter
                            icon: "more"; size: 18; tip: qsTr("More: playlists, remove from library…")
                            onClicked: Nav.albumMenu([page.albumKey], page.info.album || "", page.info.album_artist || "")
                        }
                    }
                }

                // Liner notes
                GlassPanel {
                    id: notesPanel
                    objectName: "linerNotes"
                    anchors { left: parent.left; right: parent.right; rightMargin: 20; top: sleeve.bottom; topMargin: 26 }
                    height: notesFlow.implicitHeight + 36
                    Flow {
                        id: notesFlow
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 18 }
                        spacing: 32
                        Note {
                            label: shell.allGenresAlbums && (page.notes.genres || []).length > 1 ? qsTr("Genres") : qsTr("Genre")
                            value: links.join(", ")
                            links: (page.notes.genres || []).slice(0, shell.allGenresAlbums ? 8 : 1)
                        }
                        Note {
                            objectName: "albumComposers"
                            label: (page.notes.composers || []).length > 1 ? qsTr("Composers") : qsTr("Composer")
                            value: links.join(", ")
                            links: page.notes.composers || []
                            composers: true
                        }
                        Note { label: qsTr("Format"); value: page.formatLine() + (page.notes.lossless ? "  ·  " + qsTr("lossless") : "") }
                        Note { label: qsTr("Discs"); value: page.multiDisc ? String(page.notes.discs) : "" }
                        Note { label: qsTr("Size"); value: page.notes.bytes ? Theme.fmtBytes(page.notes.bytes) : "" }
                        Note { label: qsTr("Added"); value: page.fmtDate(page.notes.added || 0) }
                        Note { objectName: "albumListening"; label: qsTr("Your listening"); value: page.listening() }
                        Note { label: qsTr("Liked"); value: page.notes.liked ? Theme.counted(qsTr("%n song(s)", "", page.notes.liked), page.notes.liked) : "" }
                    }
                }
            }

            section.property: page.multiDisc ? "disc_no" : ""
            section.delegate: Item {
                readonly property string disc: section
                width: list.width
                height: 46
                Text {
                    textFormat: Text.PlainText
                    x: 12
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 8
                    text: qsTr("Disc %1").arg(parent.disc)
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: (Theme.fontSize(15)) * Theme.displayScale
                    font.weight: Font.DemiBold
                }
            }

            delegate: TrackRow {
                selectionSource: ListView.view ? ListView.view.model : null
                path: model.path
                audioFormat: model.codec
                bitDepth: model.bit_depth || 0
                sampleRate: model.sample_rate || 0
                explicitTag: model.explicit || 0
                audioBitrate: model.bitrate
                rowIndex: index
                context: "album"
                width: ListView.view.width - 12
                number: model.track_no > 0 ? model.track_no : index + 1
                title: model.title
                artist: model.artist
                durText: model.durText
                showArt: false
                showAlbum: false
                current: Rows.currentId === model.id
                onActivated: player.playList(page.tracks.toList(), index)
                onEnqueue: player.enqueue(page.tracks.get(index))
            }
            footer: Item { width: 1; height: 30 }
        }
    }
}
