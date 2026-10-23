import QtQuick
import QtQuick.Controls
import "."

// One composer: their works (each with its movements, in order), the songs of theirs that aren't part of a work,
// the albums they're on and who performs them. Songs crediting several composers count for each.
Item {
    id: page
    objectName: "composer"
    property string composerName
    property int revision: 0
    property int seenRevision: -1
    readonly property bool shown: StackView.status === StackView.Active || StackView.status === StackView.Activating
                                  || StackView.view === null
    function catchUp() {
        if (seenRevision !== library.detailRevision) { seenRevision = library.detailRevision; revision++ }
    }
    Component.onCompleted: seenRevision = library.detailRevision
    Connections {
        target: library
        function onDetailChanged() { if (page.shown) page.catchUp() }
    }
    onShownChanged: if (shown) catchUp()
    readonly property var info: page.revision >= 0 && composerName ? library.composerPage(composerName) : ({})
    readonly property var works: info.works || []
    readonly property var others: info.others || []
    readonly property var albumList: info.albumList || []
    // where each work's first song sits in the composer's whole list (Play all's order), for playing from a row
    readonly property var workStart: {
        var out = [], n = 0
        for (var i = 0; i < works.length; i++) { out.push(n); n += works[i].songs.length }
        out.push(n)
        return out
    }
    function plural(n, one, many) { return n + " " + (n === 1 ? one : many) }
    // a movement as it's usually written: "III. Allegro", else the song's own title
    function movementTitle(t) {
        if (!t.movement) return t.title
        return (t.movement_no > 0 ? page.roman(t.movement_no) + ". " : "") + t.movement
    }
    function roman(n) {
        var r = "", vals = [[10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]]
        if (n > 39) return String(n)
        for (var i = 0; i < vals.length; i++) while (n >= vals[i][0]) { r += vals[i][1]; n -= vals[i][0] }
        return r
    }
    CollectionMenu { id: composerMenu; objectName: "composerMenu" }

    Flickable {
        id: fl
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: col
            x: Theme.contentX(fl.width); y: 24
            width: Theme.contentWidth(fl.width)
            spacing: 26

            Row {
                spacing: 26
                Item {
                    width: 180; height: 180
                    Repeater {
                        model: Math.min(3, page.albumList.length)
                        Cover {
                            required property int index
                            width: 150; height: 150
                            x: index * 15; y: index * 15
                            z: -index
                            opacity: 1 - index * 0.25
                            radius: Theme.radius
                            source: page.albumList[index].artUrl || ""
                            fallback: page.composerName.charAt(0)
                        }
                    }
                    Cover {
                        visible: page.albumList.length === 0
                        width: 150; height: 150
                        radius: Theme.radius
                        fallback: page.composerName.charAt(0) || "♪"
                    }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    width: col.width - 210
                    spacing: 8
                    Text {
                        textFormat: Text.PlainText
                        text: "COMPOSER"
                        color: Theme.accent
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(11)
                        font.weight: Font.Bold
                        font.letterSpacing: 1.5
                    }
                    Text {
                        textFormat: Text.PlainText
                        objectName: "composerTitle"
                        width: parent.width
                        text: page.info.name || page.composerName
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.fontSize(36)
                        font.weight: Font.Bold
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                    Text {
                        textFormat: Text.PlainText
                        objectName: "composerFacts"
                        width: parent.width
                        text: [page.works.length ? page.plural(page.works.length, "work", "works") : "",
                               page.plural(page.info.tracks || 0, "song", "songs"),
                               page.plural(page.albumList.length, "album", "albums"),
                               page.info.seconds ? Theme.fmtHours(page.info.seconds) : ""].filter(s => s).join("  ·  ")
                        color: Theme.textDim
                        wrapMode: Text.Wrap
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(14)
                    }
                    Flow {
                        width: parent.width
                        spacing: 10
                        topPadding: 10
                        PillButton {
                            primary: true; text: "Play all"
                            enabled: (page.info.tracks || 0) > 0
                            onClicked: library.playComposer(page.composerName, false)
                        }
                        PillButton {
                            text: "Shuffle"
                            enabled: (page.info.tracks || 0) > 0
                            onClicked: { player.setShuffle(true); library.playComposer(page.composerName, true) }
                        }
                        IconButton {
                            objectName: "composerPageMore"
                            height: 38
                            enabled: (page.info.tracks || 0) > 0
                            icon: "more"; size: 18; tip: "More: play next, add to the queue or a playlist"
                            onClicked: composerMenu.showComposer(page.composerName)
                        }
                    }
                }
            }

            // Who plays them
            Column {
                width: col.width
                spacing: 10
                visible: (page.info.performers || []).length > 0
                SectionHeader { title: "Performed by" }
                Flow {
                    width: col.width
                    spacing: 8
                    Repeater {
                        model: page.info.performers || []
                        Chip {
                            required property var modelData
                            text: modelData.name
                            onClicked: Nav.openArtist(modelData.name)
                            Accessible.name: "Artist: " + modelData.name
                        }
                    }
                }
            }

            // Works, each with its movements
            Column {
                objectName: "composerWorks"
                width: col.width
                spacing: 18
                visible: page.works.length > 0
                SectionHeader { title: "Works" }
                Repeater {
                    model: page.works
                    Column {
                        id: workBlock
                        required property var modelData
                        required property int index
                        width: col.width
                        spacing: 2
                        Row {
                            spacing: 12
                            bottomPadding: 6
                            Text {
                                textFormat: Text.PlainText
                                width: Math.min(implicitWidth, col.width - 160)
                                elide: Text.ElideRight
                                text: workBlock.modelData.work
                                color: Theme.text
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.fontSize(17)
                                font.weight: Font.DemiBold
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors.baseline: parent.children[0].baseline
                                text: page.plural(workBlock.modelData.songs.length, "movement", "movements")
                                      + (workBlock.modelData.seconds >= 60 ? "  ·  " + Theme.fmtHours(workBlock.modelData.seconds) : "")
                                color: Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(12.5)
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors.baseline: parent.children[0].baseline
                                text: "Play"
                                color: Theme.accent
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(12.5)
                                font.weight: Font.DemiBold
                                LinkArea {
                                    name: "Play " + workBlock.modelData.work
                                    onClicked: userLib.playPaths(workBlock.modelData.songs.map(function (t) { return t.path }))
                                }
                            }
                        }
                        Repeater {
                            model: workBlock.modelData.songs
                            TrackRow {
                                required property var modelData
                                required property int index
                                selectionSource: workBlock.modelData.songs
                                path: modelData.path
                                audioFormat: modelData.codec || ""
                                audioBitrate: modelData.bitrate || 0
                                rowIndex: index
                                width: col.width
                                showArt: false
                                title: page.movementTitle(modelData)
                                artist: modelData.artist || ""
                                album: modelData.album || ""
                                durText: modelData.durText || ""
                                current: Rows.currentId === modelData.id
                                onActivated: library.playComposerSongs(page.composerName, page.workStart[workBlock.index] + index)
                                onEnqueue: player.enqueue(modelData)
                            }
                        }
                    }
                }
            }

            // Songs that aren't part of a work
            Column {
                objectName: "composerSongs"
                width: col.width
                spacing: 4
                visible: page.others.length > 0
                SectionHeader { title: page.works.length ? "Other songs" : "Songs" }
                Item { width: 1; height: 6 }
                Repeater {
                    model: page.others
                    TrackRow {
                        required property var modelData
                        required property int index
                        selectionSource: page.others
                        path: modelData.path
                        audioFormat: modelData.codec || ""
                        audioBitrate: modelData.bitrate || 0
                        rowIndex: index
                        width: col.width
                        title: modelData.title || ""
                        artist: modelData.artist || ""
                        album: modelData.album || ""
                        durText: modelData.durText || ""
                        artUrl: modelData.artUrl || ""
                        current: Rows.currentId === modelData.id
                        onActivated: library.playComposerSongs(page.composerName, page.workStart[page.works.length] + index)
                        onEnqueue: player.enqueue(modelData)
                    }
                }
            }

            Column {
                width: col.width
                spacing: 14
                visible: page.albumList.length > 0
                SectionHeader { title: "Albums" }
                Flow {
                    width: col.width
                    spacing: 18
                    Repeater {
                        model: page.albumList.slice(0, 48)
                        AlbumCard {
                            required property var modelData
                            cardWidth: 160
                            albumKey: modelData.album_key
                            title: modelData.album
                            artist: modelData.album_artist
                            subtitle: (modelData.year > 0 ? modelData.year + "  ·  " : "") + modelData.album_artist
                            artUrl: modelData.artUrl
                        }
                    }
                }
            }
        }
    }

    EmptyState {
        anchors.centerIn: parent
        visible: page.info.tracks === 0
        icon: "note"
        title: "Nothing by " + page.composerName
        hint: "None of your songs credit this composer any more."
    }
}
