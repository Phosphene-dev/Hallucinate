import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import "."

// A week, month or year of listening summed up. The top card holds the highlights and can be saved as an image.
Item {
    id: page
    objectName: "recap"
    property string kind: "month"
    readonly property var rc: userLib.recap || ({})
    readonly property var summary: rc.summary || ({})
    readonly property bool empty: !rc.loading && (summary.plays || 0) === 0
    readonly property var tint: [Theme.art0, Theme.art1, Theme.art2]
    property string savedTo: ""

    Component.onCompleted: userLib.loadRecap(kind)
    onKindChanged: userLib.loadRecap(kind)

    function hoursText(seconds) {
        if (seconds >= 3600 * 1.5) return { n: Math.round(seconds / 3600), u: "hours" }
        return { n: Math.round(seconds / 60), u: "minutes" }
    }
    function plural(n, one, many) { return n + " " + (n === 1 ? one : many) }
    function peakHour() {
        var h = rc.hours || [], best = -1, at = 0
        for (var i = 0; i < h.length; i++) if (h[i] > best) { best = h[i]; at = i }
        if (best <= 0) return ""
        var d = new Date(2000, 0, 1, at, 0)
        return Qt.formatTime(d, "h ap").replace(":00", "")
    }
    function weekdayName(i) { return ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"][i] }
    function peakWeekday() {
        var w = rc.weekdays || [], best = -1, at = 0
        for (var i = 0; i < w.length; i++) if (w[i] > best) { best = w[i]; at = i }
        return best > 0 ? weekdayName(at) : ""
    }
    function saveImage() {
        shareCard.grabToImage(function (result) {
            page.savedTo = userLib.saveRecapImage(result.image) || "-"
            savedTimer.restart()
        }, Qt.size(shareCard.width * 2, shareCard.height * 2))
    }
    Timer { id: savedTimer; interval: 12000; onTriggered: page.savedTo = "" }

    // A soft glow inside the card. It is drawn as the card's own rounded shape, filled with a radial gradient
    // centred at (cx, cy), so it can't spill past the rounded corners (clip only cuts to the square bounds).
    component Bloom: Shape {
        id: bloom
        visible: !Theme.retro  // a retro theme's card is a plain screen
        property color tint
        property real size: 600
        property real cx
        property real cy
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeWidth: 0; strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: bloom.cx; centerY: bloom.cy; centerRadius: bloom.size / 2
                focalX: bloom.cx; focalY: bloom.cy
                GradientStop { position: 0; color: Qt.rgba(bloom.tint.r, bloom.tint.g, bloom.tint.b, 0.45) }
                GradientStop { position: 1; color: Qt.rgba(bloom.tint.r, bloom.tint.g, bloom.tint.b, 0) }
            }
            PathRectangle { x: 0; y: 0; width: bloom.width; height: bloom.height; radius: shareCard.radius }
        }
    }

    component Ranked: Row {
        property int rank
        property string label
        property string sub
        property url art
        property bool round: false
        property real labelRoom: 190  // the names' column: narrower when the card is
        spacing: 12
        Text {
            textFormat: Text.PlainText
            anchors.verticalCenter: parent.verticalCenter
            width: 18
            text: parent.rank
            color: Qt.rgba(1, 1, 1, 0.55)
            font.family: Theme.displayFamily
            font.pixelSize: (Theme.fontSize(15)) * Theme.displayScale
            font.weight: Font.Bold
        }
        Cover {
            width: 44; height: 44
            radius: parent.round ? 22 : 8
            source: parent.art
            fallback: (parent.label || "?").charAt(0)
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(60, Math.min(190, parent.labelRoom))
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: parent.parent.label
                color: "white"
                elide: Text.ElideRight
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(14)
                font.weight: Font.DemiBold
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                text: parent.parent.sub
                color: Qt.rgba(1, 1, 1, 0.65)
                elide: Text.ElideRight
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(12)
            }
        }
    }

    component Bars: Column {
        id: bars
        property var values: []
        property var labels: []
        property string title
        property string note
        property real barHeight: 80
        readonly property real maxValue: Math.max(1, ...values)
        spacing: 10
        Text {
            textFormat: Text.PlainText
            text: bars.title
            color: Theme.text
            font.family: Theme.displayFamily
            font.pixelSize: (Theme.fontSize(15)) * Theme.displayScale
            font.weight: Font.DemiBold
        }
        Text {
            textFormat: Text.PlainText
            visible: bars.note.length > 0
            text: bars.note
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(12)
        }
        Row {
            spacing: 4
            Repeater {
                model: bars.values.length
                Column {
                    required property int index
                    spacing: 4
                    Item {
                        width: Math.max(8, (bars.width - 4 * (bars.values.length - 1)) / bars.values.length)
                        height: bars.barHeight
                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: Math.max(3, bars.barHeight * bars.values[index] / bars.maxValue)
                            radius: Math.min(4, width / 2)
                            color: bars.values[index] ? Theme.accent : Theme.stroke
                            opacity: bars.values[index] ? 0.4 + 0.6 * bars.values[index] / bars.maxValue : 1
                        }
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: Math.max(8, (bars.width - 4 * (bars.values.length - 1)) / bars.values.length)
                        horizontalAlignment: Text.AlignHCenter
                        text: bars.labels[index] || ""
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(9)
                    }
                }
            }
        }
    }

    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: fl
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: col
            x: Theme.contentX(fl.width); y: 22
            width: Theme.contentWidth(fl.width)
            spacing: 22

            // Title, period kind and navigation
            Flow {  // wraps in a narrow window
                width: col.width
                spacing: 16
                Text {
                    textFormat: Text.PlainText
                    height: 36
                    verticalAlignment: Text.AlignVCenter
                    text: "Recap"
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale
                    font.weight: Font.Bold
                }
                Row {
                    spacing: 6
                    Repeater {
                        model: [{ id: "week", t: "Week" }, { id: "month", t: "Month" }, { id: "year", t: "Year" }]
                        Chip {
                            required property var modelData
                            objectName: "recapKind_" + modelData.id
                            text: modelData.t
                            selected: page.kind === modelData.id
                            onClicked: page.kind = modelData.id
                        }
                    }
                }
                Row {
                    spacing: 2
                    IconButton { objectName: "recapPrev"; icon: "prev"; size: 14; tip: "Earlier"; onClicked: userLib.stepRecap(-1) }
                    Text {
                        textFormat: Text.PlainText
                        anchors.verticalCenter: parent.verticalCenter
                        width: 170
                        horizontalAlignment: Text.AlignHCenter
                        text: page.rc.title || ""
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(14)
                        font.weight: Font.DemiBold
                    }
                    IconButton {
                        objectName: "recapNext"
                        icon: "next"; size: 14; tip: "Later"
                        enabled: !!page.rc.hasNext
                        onClicked: userLib.stepRecap(1)
                    }
                }
            }

            // The card: highlights, also saved as an image
            Rectangle {
                id: shareCard
                objectName: "recapCard"
                width: col.width
                height: 380
                radius: Theme.round(26)
                clip: true
                // a retro theme's card: a blue screen in a light theme, a dark panel in a dark one (white text reads on both)
                color: Theme.retro ? (Theme.light ? Theme.accent : "#0d0e10") : "#120c1c"
                Bevel {}
                Bloom { tint: page.tint[0]; cx: 120; cy: 40 }
                Bloom { tint: page.tint[1]; size: 520; cx: shareCard.width - 120; cy: 320 }
                Bloom { tint: page.tint[2]; size: 420; cx: shareCard.width * 0.35 + 210; cy: 390 }

                Column {
                    id: hero
                    x: 30; y: 28
                    width: shareCard.width * 0.42
                    spacing: 6
                    Text {
                        textFormat: Text.PlainText
                        text: (page.rc.title || "").toUpperCase()
                        color: Qt.rgba(1, 1, 1, 0.75)
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(11)
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.6
                    }
                    Text {
                        textFormat: Text.PlainText
                        objectName: "recapTime"
                        text: page.empty ? "—" : page.hoursText(page.summary.seconds || 0).n
                        color: "white"
                        font.family: Theme.displayFamily
                        font.pixelSize: (Theme.fontSize(76)) * Theme.displayScale
                        font.weight: Font.Bold
                    }
                    Text {
                        textFormat: Text.PlainText
                        text: page.empty ? "Nothing played yet" : page.hoursText(page.summary.seconds || 0).u + " of music"
                        color: "white"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(17)
                    }
                    Text {
                        textFormat: Text.PlainText
                        visible: page.rc.change !== null && page.rc.change !== undefined && !page.empty
                        text: (page.rc.change >= 0 ? "▲ " : "▼ ") + Math.abs(Math.round((page.rc.change || 0) * 100)) + "% vs the "
                              + (page.kind === "week" ? "week" : page.kind === "month" ? "month" : "year") + " before"
                        color: page.rc.change >= 0 ? "#b9f5c8" : "#f5c2b9"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(12)
                        topPadding: 4
                    }
                    Item { width: 1; height: 16 }
                    Grid {
                        columns: 2
                        columnSpacing: 26
                        rowSpacing: 12
                        Repeater {
                            model: [
                                [page.summary.plays || 0, "plays"], [page.summary.songs || 0, "songs"],
                                [page.summary.artists || 0, "artists"], [page.summary.days || 0, "days listening"]
                            ]
                            Column {
                                required property var modelData
                                Text {
                                    textFormat: Text.PlainText
                                    text: modelData[0]
                                    color: "white"
                                    font.family: Theme.displayFamily
                                    font.pixelSize: (Theme.fontSize(20)) * Theme.displayScale
                                    font.weight: Font.Bold
                                }
                                Text {
                                    textFormat: Text.PlainText
                                    text: modelData[1]
                                    color: Qt.rgba(1, 1, 1, 0.65)
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSize(11)
                                }
                            }
                        }
                    }
                }
                Row {
                    x: hero.x + hero.width + 10; y: 34
                    spacing: 24
                    visible: !page.empty
                    Column {
                        spacing: 10
                        Text { text: "Top artists"; color: Qt.rgba(1, 1, 1, 0.75); font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold; textFormat: Text.PlainText }
                        Repeater {
                            model: (page.rc.topArtists || []).slice(0, 5)
                            Ranked {
                                required property var modelData
                                required property int index
                                rank: index + 1; label: modelData.name; round: true
                                labelRoom: shareCard.width - hero.x - hero.width - 10 - 18 - 44 - 24 - 24
                                sub: page.plural(modelData.plays, "play", "plays"); art: modelData.artUrl || ""
                            }
                        }
                    }
                    Column {
                        spacing: 10
                        visible: shareCard.width > 980
                        Text { text: "Top songs"; color: Qt.rgba(1, 1, 1, 0.75); font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold; textFormat: Text.PlainText }
                        Repeater {
                            model: (page.rc.topSongs || []).slice(0, 5)
                            Ranked {
                                required property var modelData
                                required property int index
                                rank: index + 1; label: modelData.title
                                sub: modelData.artist + "  ·  " + page.plural(modelData.plays, "play", "plays"); art: modelData.artUrl || ""
                            }
                        }
                    }
                }
                Row {
                    anchors { right: parent.right; rightMargin: 22; bottom: parent.bottom; bottomMargin: 16 }
                    spacing: 6
                    Image { anchors.verticalCenter: parent.verticalCenter; source: "../assets/hallucinate.png"; sourceSize: Qt.size(32, 32); width: 16; height: 16; smooth: true }
                    Text { text: "Hallucinate"; color: Qt.rgba(1, 1, 1, 0.6); font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(11)) * Theme.displayScale; textFormat: Text.PlainText }
                }
            }

            Row {
                spacing: 12
                PillButton { objectName: "saveRecap"; text: "Save as image"; enabled: !page.empty; onClicked: page.saveImage() }
                Text {
                    textFormat: Text.PlainText
                    anchors.verticalCenter: parent.verticalCenter
                    visible: page.savedTo.length > 0
                    text: page.savedTo === "-" ? "Couldn't save the image" : "Saved to " + page.savedTo
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(12)
                }
                PillButton {
                    objectName: "showRecapImage"
                    visible: page.savedTo.length > 1
                    text: "Show in folder"
                    onClicked: library.showInFolder(page.savedTo)
                }
            }

            // Albums and songs in full
            Row {
                width: col.width
                spacing: 26
                visible: !page.empty
                Column {
                    width: (col.width - 26) / 2
                    spacing: 12
                    SectionHeader { title: "Top albums" }
                    Flow {
                        width: parent.width
                        spacing: 14
                        Repeater {
                            model: page.rc.topAlbums || []
                            AlbumCard {
                                required property var modelData
                                cardWidth: Math.min(150, (parent.width - 28) / 3)
                                albumKey: modelData.album_key || ""
                                title: modelData.album
                                subtitle: page.plural(modelData.plays, "play", "plays")
                                artUrl: modelData.artUrl || ""
                            }
                        }
                    }
                }
                Column {
                    width: (col.width - 26) / 2
                    spacing: 4
                    SectionHeader { title: "Top songs" }
                    Item { width: 1; height: 8 }
                    Repeater {
                        model: page.rc.topSongs || []
                        TrackRow {
                            selectionSource: page.rc.topSongs || []
                            required property var modelData
                            required property int index
                            rowIndex: index
                            width: parent.width
                            number: index + 1
                            path: modelData.path || ""
                            title: modelData.title
                            artist: modelData.artist + "  ·  " + page.plural(modelData.plays, "play", "plays")
                            showAlbum: false
                            durText: modelData.durText || ""
                            artUrl: modelData.artUrl || ""
                            audioFormat: modelData.codec || modelData.fmt || ""
                            bitDepth: modelData.bit_depth || 0
                            sampleRate: modelData.sample_rate || 0
                            explicitTag: modelData.explicit || 0
                            audioBitrate: modelData.bitrate || 0
                            onActivated: userLib.playRecapSong(index)
                        }
                    }
                }
            }

            // When you listened
            GlassPanel {
                width: col.width
                height: patterns.implicitHeight + 40
                visible: !page.empty
                Row {
                    id: patterns
                    x: 22; y: 20
                    spacing: 40
                    Bars {
                        width: page.kind === "year" ? (col.width - 44 - 80) * 0.4 : (col.width - 44 - 40) * 0.62
                        title: "Time of day"
                        note: page.peakHour() ? "Most often around " + page.peakHour() : ""
                        values: page.rc.hours || []
                        labels: (page.rc.hours || []).map((v, i) => i % 6 === 0 ? String(i) : "")
                    }
                    Bars {
                        width: page.kind === "year" ? (col.width - 44 - 80) * 0.22 : (col.width - 44 - 40) * 0.38
                        title: "Day of the week"
                        note: page.peakWeekday() ? "Busiest on " + page.peakWeekday() : ""
                        values: page.rc.weekdays || []
                        labels: ["M", "T", "W", "T", "F", "S", "S"]
                    }
                    Bars {
                        visible: page.kind === "year"
                        width: (col.width - 44 - 80) * 0.38
                        title: "Month by month"
                        note: ""
                        values: (page.rc.months || []).map(m => m.seconds)
                        labels: ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
                    }
                }
            }

            // Little facts
            Flow {
                width: col.width
                spacing: 14
                visible: !page.empty
                Repeater {
                    model: [
                        { t: "New artists", v: page.rc.discoveryCount || 0,
                          s: (page.rc.discoveries || []).slice(0, 3).map(d => d.name).join(", ") },
                        { t: "Longest streak", v: page.plural(page.rc.streak || 0, "day", "days"), s: "in a row" },
                        { t: "Busiest day", v: page.rc.busiestDay ? Qt.formatDate(new Date(page.rc.busiestDay.day + "T12:00:00"), "ddd d MMM") : "—",
                          s: page.rc.busiestDay ? page.plural(page.rc.busiestDay.plays, "play", "plays") : "" },
                        { t: "Top genres", v: (page.rc.genres || []).slice(0, 1).join("") || "—", s: (page.rc.genres || []).slice(1).join(", ") },
                        { t: "Albums added", v: page.rc.albumsAdded || 0, s: "to your library" }
                    ]
                    GlassPanel {
                        required property var modelData
                        width: Math.max(180, (col.width - 4 * 14) / 5)
                        height: 104
                        Column {
                            x: 18; y: 16
                            width: parent.width - 36
                            spacing: 4
                            Text { text: modelData.t; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); font.weight: Font.DemiBold; textFormat: Text.PlainText }
                            Text {
                                textFormat: Text.PlainText
                                width: parent.width
                                text: modelData.v
                                color: Theme.text
                                elide: Text.ElideRight
                                font.family: Theme.displayFamily
                                font.pixelSize: (Theme.fontSize(20)) * Theme.displayScale
                                font.weight: Font.Bold
                            }
                            Text {
                                textFormat: Text.PlainText
                                width: parent.width
                                text: modelData.s
                                color: Theme.textDim
                                elide: Text.ElideRight
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(11)
                            }
                        }
                    }
                }
            }
        }
    }
}
