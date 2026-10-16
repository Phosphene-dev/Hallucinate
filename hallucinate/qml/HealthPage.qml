import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import "."

// Library health: a score, then each kind of problem with what it means and a fix next to every item.
Item {
    id: page
    objectName: "health"
    readonly property var report: library.health || ({})
    readonly property var checks: report.checks || []
    readonly property int score: report.score !== undefined ? report.score : 100
    property string expanded: ""
    Component.onCompleted: library.checkHealth()

    function fixLabel(kind, id) {
        if (kind === "folder") return "Remove"
        if (id === "covers") return "Find cover"
        if (id === "genre") return "Find genre"
        if (id === "replaygain") return "Analyse"
        if (kind === "album") return "Edit album"
        return "Edit tags"
    }
    function fix(check, item) {
        if (check.kind === "folder") library.removeFolder(item.path)
        else if (check.id === "covers") metaEditor.fetchCover(item.album_key, item.album_artist || "", item.album || "", false)
        else if (check.id === "replaygain") replayGain.analyseAlbum(item.album_key)
        else if (check.id === "genre") Nav.findAlbumGenre(item.album_key)
        else if (check.kind === "album") Nav.editAlbum(item.album_key)
        else Nav.editTags(item.path)
    }
    Connections {
        target: metaEditor
        function onChanged() { library.checkHealth() }
    }
    Connections {
        target: metaEditor
        function onGenresFinished(text) {
            Nav.notify(text)
            if (metaEditor.genreProposals.length) genreReview.open()
        }
    }
    GenreReview { id: genreReview }
    Connections {
        target: replayGain
        function onFinished() { library.checkHealth() }
    }
    Connections {
        target: library
        function onReloaded() { library.checkHealth() }  // e.g. after songs or albums were removed from a list here
    }
    // Every listed item acts like it does elsewhere: click opens the album (or plays the song), right-click
    // brings up its usual menu.
    function activate(check, item) {
        if (check.kind === "album") Nav.openAlbum(item.album_key)
        else if (check.kind === "track") userLib.playPaths([item.path])
    }
    function menuFor(check, item) {
        if (check.kind === "album") Nav.albumMenu([item.album_key], item.album || "", item.album_artist || "")
        else if (check.kind === "track") Nav.trackMenu(item.path, item.title || "", "health", -1)
        else { folderMenu.path = item.path; folderMenu.popup() }
    }
    Menu {
        id: folderMenu
        objectName: "healthFolderMenu"
        property string path: ""
        MenuItem { text: "Copy path"; icon.name: "folder"; onTriggered: shell.copyText(folderMenu.path) }
        MenuSeparator {}
        MenuItem {
            text: "Remove from the library"; icon.name: "remove"; icon.color: Theme.error
            onTriggered: library.removeFolder(folderMenu.path)
        }
    }
    ConfirmDialog {
        id: extraDlg
        objectName: "removeExtraCopiesDialog"
        title: "Keep only the best copies?"
        confirmText: "Remove " + what
        body: "Of each set of probable duplicates, the best copy stays: lossless first, then the higher bitrate. "
              + "The other " + what + " are taken out of the library; the files stay on your disk, and Settings → "
              + "Library can bring them back. Check the list first if some are on purpose, like a song on both an album "
              + "and a compilation: right-click one to keep or remove it on its own."
        onAccepted: library.removeExtraCopies()
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.height + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: content
            x: 28; y: 22
            width: parent.width - 56
            spacing: 18

            Row {
                spacing: 22
                // score ring
                Item {
                    width: 96; height: 96
                    Shape {
                        anchors.fill: parent
                        preferredRendererType: Shape.CurveRenderer
                        ShapePath {
                            strokeColor: Theme.stroke; strokeWidth: 8; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                            PathAngleArc { centerX: 48; centerY: 48; radiusX: 42; radiusY: 42; startAngle: 0; sweepAngle: 360 }
                        }
                        ShapePath {
                            strokeColor: page.score >= 85 ? Theme.accent : page.score >= 60 ? "#e8b25a" : Theme.error
                            strokeWidth: 8; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                            PathAngleArc { centerX: 48; centerY: 48; radiusX: 42; radiusY: 42; startAngle: -90; sweepAngle: 3.6 * page.score }
                        }
                    }
                    Text {
                        textFormat: Text.PlainText
                        objectName: "healthScore"
                        anchors.centerIn: parent
                        text: page.score
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.fontSize(26)
                        font.weight: Font.Bold
                    }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Text {
                        textFormat: Text.PlainText
                        text: "Library health"
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.fontSize(25)
                        font.weight: Font.Bold
                    }
                    Text {
                        textFormat: Text.PlainText
                        objectName: "healthSummary"
                        text: page.report.loading && !page.checks.length ? "Checking your library…"
                            : (page.report.issues || 0) === 0 ? "Nothing to fix. Your library is in great shape."
                            : page.report.issues + (page.report.issues === 1 ? " thing" : " things") + " worth a look across "
                              + (page.report.albums || 0) + " albums and " + (page.report.tracks || 0) + " songs"
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(14)
                    }
                    PillButton {
                        text: page.report.loading ? "Checking…" : "Check again"
                        enabled: !page.report.loading
                        onClicked: library.checkHealth()
                    }
                }
            }

            Repeater {
                model: page.checks
                GlassPanel {
                    id: card
                    required property var modelData
                    readonly property bool open: page.expanded === modelData.id && modelData.count > 0
                    width: content.width
                    height: cardCol.implicitHeight + 32
                    opacity: modelData.count > 0 ? 1 : 0.6
                    Column {
                        id: cardCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
                        spacing: 10
                        Item {
                            width: parent.width
                            height: Math.max(head.implicitHeight, 34)
                            Rectangle {
                                id: dot
                                anchors.verticalCenter: parent.verticalCenter
                                width: 10; height: 10; radius: 5
                                color: card.modelData.count === 0 ? Theme.accent
                                    : card.modelData.id === "folders" ? Theme.error : "#e8b25a"
                            }
                            Column {
                                id: head
                                anchors { left: dot.right; leftMargin: 14; right: countText.left; rightMargin: 12; verticalCenter: parent.verticalCenter }
                                spacing: 2
                                Text {
                                    textFormat: Text.PlainText
                                    text: card.modelData.title
                                    color: Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSize(15)
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    textFormat: Text.PlainText
                                    width: parent.width
                                    text: card.modelData.detail
                                    color: Theme.textDim
                                    wrapMode: Text.Wrap
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSize(12)
                                }
                            }
                            Text {
                                textFormat: Text.PlainText
                                id: countText
                                anchors { right: chevron.left; rightMargin: 10; verticalCenter: parent.verticalCenter }
                                text: card.modelData.count === 0 ? "All good" : card.modelData.count
                                color: card.modelData.count === 0 ? Theme.accent : Theme.text
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.fontSize(card.modelData.count === 0 ? 13 : 18)
                                font.weight: Font.DemiBold
                            }
                            Icon {
                                id: chevron
                                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                                width: 16; height: 16
                                visible: card.modelData.count > 0
                                name: "down"
                                rotation: card.open ? 180 : 0
                                color: Theme.textDim
                                Behavior on rotation { NumberAnimation { duration: 160 } }
                            }
                            MouseArea {
                                anchors.fill: parent
                                enabled: card.modelData.count > 0
                                cursorShape: Qt.PointingHandCursor
                                Accessible.role: Accessible.Button
                                Accessible.name: card.modelData.title + ": " + countText.text
                                Accessible.description: card.modelData.detail
                                Accessible.onPressAction: page.expanded = card.open ? "" : card.modelData.id
                                onClicked: page.expanded = card.open ? "" : card.modelData.id
                            }
                        }
                        Row {
                            visible: card.modelData.id === "covers" && (card.modelData.count > 0 || metaEditor.coversBusy)
                            spacing: 12
                            leftPadding: 24
                            PillButton {
                                objectName: "findAllCovers"
                                primary: !metaEditor.coversBusy
                                height: 32
                                text: metaEditor.coversBusy ? "Stop" : "Find all online"
                                enabled: metaEditor.coversBusy || !shell.offlineMode
                                onClicked: metaEditor.coversBusy ? metaEditor.cancelCovers() : metaEditor.fetchMissingCovers()
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.min(implicitWidth, card.width - 220)
                                elide: Text.ElideRight
                                text: metaEditor.coversBusy
                                      ? "Looked up " + metaEditor.coversDone + " of " + metaEditor.coversTotal + " albums  ·  "
                                        + metaEditor.coversFound + " found" + (metaEditor.coversCurrent ? "  ·  " + metaEditor.coversCurrent : "")
                                      : "Searches MusicBrainz and the Cover Art Archive, about one album a second."
                                color: Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(12)
                            }
                        }
                        Row {
                            visible: card.modelData.id === "genre" && (card.modelData.count > 0 || metaEditor.genresBusy
                                                                        || metaEditor.genreProposals.length > 0)
                            spacing: 12
                            leftPadding: 24
                            PillButton {
                                objectName: "findAllGenres"
                                primary: !metaEditor.genresBusy && !metaEditor.genreProposals.length
                                height: 32
                                text: metaEditor.genresBusy ? "Stop" : "Find all online"
                                enabled: metaEditor.genresBusy || !shell.offlineMode
                                onClicked: metaEditor.genresBusy ? metaEditor.cancelGenres() : metaEditor.findMissingGenres()
                            }
                            PillButton {
                                objectName: "reviewGenres"
                                visible: !metaEditor.genresBusy && metaEditor.genreProposals.length > 0
                                primary: true
                                height: 32
                                text: "Review " + metaEditor.genreProposals.length + " found…"
                                onClicked: genreReview.open()
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.min(implicitWidth, card.width - 360)
                                elide: Text.ElideRight
                                text: metaEditor.genresBusy
                                      ? "Looked up " + metaEditor.genresDone + " of " + metaEditor.genresTotal + " albums  ·  "
                                        + metaEditor.genresFound + " found" + (metaEditor.genresCurrent ? "  ·  " + metaEditor.genresCurrent : "")
                                      : "Asks MusicBrainz, a couple of seconds an album. You check what it finds before anything is saved."
                                color: Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(12)
                            }
                        }
                        Row {
                            visible: card.modelData.id === "duplicates" && (card.modelData.extra || 0) > 0
                            spacing: 12
                            leftPadding: 24
                            PillButton {
                                objectName: "removeExtraCopies"
                                primary: true
                                height: 32
                                text: "Keep the best copies"
                                onClicked: {
                                    var n = card.modelData.extra
                                    extraDlg.what = n + (n === 1 ? " copy" : " copies")
                                    extraDlg.open()
                                }
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.min(implicitWidth, card.width - 260)
                                elide: Text.ElideRight
                                text: "Takes the " + card.modelData.extra + " extra " + (card.modelData.extra === 1 ? "copy" : "copies")
                                      + " out of the library and keeps the best of each. Right-click a song for more."
                                color: Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(12)
                            }
                        }
                        Row {
                            visible: card.modelData.id === "replaygain" && (card.modelData.count > 0 || replayGain.busy)
                            spacing: 12
                            leftPadding: 24
                            PillButton {
                                objectName: "analyseAll"
                                primary: !replayGain.busy
                                height: 32
                                text: replayGain.busy ? "Stop" : "Analyse all"
                                onClicked: replayGain.busy ? replayGain.cancel() : replayGain.analyseMissing()
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors.verticalCenter: parent.verticalCenter
                                visible: replayGain.busy
                                text: "Measured " + replayGain.done + " of " + replayGain.total + " songs"
                                      + (replayGain.failed ? "  ·  " + replayGain.failed + " couldn't be read" : "")
                                color: Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(12)
                            }
                        }
                        Column {
                            visible: card.open
                            width: parent.width
                            spacing: 2
                            Repeater {
                                model: card.open ? card.modelData.items : []
                                Rectangle {
                                    id: itemRow
                                    required property var modelData
                                    width: cardCol.width
                                    height: 48
                                    radius: 10
                                    color: rowHover.hovered ? Theme.glassHover : "transparent"
                                    HoverHandler { id: rowHover }
                                    MouseArea {
                                        anchors.fill: parent
                                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                                        cursorShape: card.modelData.kind === "folder" ? Qt.ArrowCursor : Qt.PointingHandCursor
                                        Accessible.role: Accessible.Button
                                        Accessible.name: (card.modelData.kind === "folder" ? itemRow.modelData.path
                                            : card.modelData.kind === "album" ? itemRow.modelData.album : itemRow.modelData.title) || ""
                                        Accessible.onPressAction: page.activate(card.modelData, itemRow.modelData)
                                        onPressAndHold: page.menuFor(card.modelData, itemRow.modelData)
                                        onClicked: function (mouse) {
                                            if (mouse.button === Qt.RightButton) page.menuFor(card.modelData, itemRow.modelData)
                                            else page.activate(card.modelData, itemRow.modelData)
                                        }
                                    }
                                    Cover {
                                        id: thumb
                                        visible: card.modelData.kind !== "folder"
                                        x: 6; anchors.verticalCenter: parent.verticalCenter
                                        width: 36; height: 36; radius: 8
                                        source: itemRow.modelData.artUrl || ""
                                        fallback: ((itemRow.modelData.album || itemRow.modelData.title || "?") + "").charAt(0)
                                    }
                                    Column {
                                        anchors { left: thumb.visible ? thumb.right : parent.left; leftMargin: 12; right: fixButton.left; rightMargin: 12; verticalCenter: parent.verticalCenter }
                                        Text {
                                            textFormat: Text.PlainText
                                            width: parent.width
                                            text: card.modelData.kind === "folder" ? itemRow.modelData.path
                                                : card.modelData.kind === "album" ? itemRow.modelData.album : itemRow.modelData.title
                                            color: Theme.text
                                            elide: Text.ElideMiddle
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.fontSize(13)
                                        }
                                        Text {
                                            textFormat: Text.PlainText
                                            width: parent.width
                                            visible: card.modelData.kind !== "folder"
                                            text: card.modelData.kind === "album"
                                                ? itemRow.modelData.album_artist + (itemRow.modelData.parts ? "  ·  " + itemRow.modelData.parts + " parts" : "")
                                                : itemRow.modelData.artist + "  ·  " + itemRow.modelData.album
                                                  + (card.modelData.id === "bitrate" ? "  ·  " + Math.round(itemRow.modelData.bitrate / 1000) + " kbps" : "")
                                                  + (card.modelData.id === "duplicates" ? "  ·  " + itemRow.modelData.path : "")
                                            color: Theme.textDim
                                            elide: Text.ElideMiddle
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.fontSize(11)
                                        }
                                    }
                                    PillButton {
                                        id: fixButton
                                        objectName: "healthFix_" + card.modelData.id
                                        anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                                        height: 32
                                        text: page.fixLabel(card.modelData.kind, card.modelData.id)
                                        enabled: !(card.modelData.id === "covers" && metaEditor.busy)
                                                 && !(card.modelData.id === "replaygain" && replayGain.busy)
                                        onClicked: page.fix(card.modelData, itemRow.modelData)
                                    }
                                }
                            }
                            Text {
                                textFormat: Text.PlainText
                                visible: card.modelData.count > card.modelData.items.length
                                text: "Showing the first " + card.modelData.items.length + " of " + card.modelData.count
                                color: Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSize(12)
                                topPadding: 6
                            }
                        }
                    }
                }
            }
        }
    }
}
