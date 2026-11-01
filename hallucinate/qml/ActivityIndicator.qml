import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import "."

// What's working in the background, in one place at the foot of the sidebar: a library scan, covers or genres
// being looked up or saved, loudness being measured, podcast episodes downloading. Collapsed it's a ring (#146),
// expanded a line with a bar; either opens a list of everything running, each with its own Stop.
Item {
    id: act
    objectName: "activityIndicator"
    property bool compact: false  // the collapsed rail: a ring
    // [{key, label, fraction (-1 while the total isn't known), stop}], in the order they're shown
    readonly property var jobs: {
        var out = []
        if (library.scanning)
            out.push({ key: "scan", label: library.status || qsTr("Scanning your music"), fraction: library.scanFraction,
                       stop: function () { library.stopScan() } })
        if (metaEditor.coversBusy)
            out.push({ key: "covers", label: "Finding covers: " + Theme.num(metaEditor.coversDone) + " of " + Theme.num(metaEditor.coversTotal) + " albums",
                       fraction: metaEditor.coversTotal > 0 ? metaEditor.coversDone / metaEditor.coversTotal : -1,
                       stop: function () { metaEditor.cancelCovers() } })
        if (metaEditor.genresBusy)
            out.push({ key: "genres", label: "Finding genres: " + Theme.num(metaEditor.genresDone) + " of " + Theme.num(metaEditor.genresTotal) + " albums",
                       fraction: metaEditor.genresTotal > 0 ? metaEditor.genresDone / metaEditor.genresTotal : -1,
                       stop: function () { metaEditor.cancelGenres() } })
        if (metaEditor.genresSaving)
            out.push({ key: "genresSave", label: "Saving genres: " + Theme.num(metaEditor.genresSaved) + " of " + Theme.num(metaEditor.genresToSave) + " albums",
                       fraction: metaEditor.genresToSave > 0 ? metaEditor.genresSaved / metaEditor.genresToSave : -1,
                       stop: function () { metaEditor.stopSavingGenres() } })
        if (replayGain.busy)
            out.push({ key: "loudness", label: "Measuring loudness: " + Theme.num(replayGain.done) + " of " + Theme.num(replayGain.total) + " songs",
                       fraction: replayGain.total > 0 ? replayGain.done / replayGain.total : -1,
                       stop: function () { replayGain.cancel() } })
        if (podcasts.downloadingCount > 0)
            out.push({ key: "downloads", label: "Downloading " + Theme.num(podcasts.downloadingCount) + (podcasts.downloadingCount === 1 ? qsTr(" episode") : qsTr(" episodes")),
                       fraction: podcasts.downloadsFraction, stop: function () { podcasts.cancelAllDownloads() } })
        return out
    }
    readonly property bool active: jobs.length > 0
    readonly property var lead: active ? jobs[0] : ({ label: "", fraction: -1 })
    visible: active
    implicitHeight: compact ? 38 : (jobs.length > 1 ? 34 : 22)

    // collapsed: a ring with the percentage inside (or a turning arc), and how many jobs beside it
    Item {
        id: dial
        visible: act.compact
        readonly property real size: 30
        width: size; height: size
        anchors.centerIn: parent
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Theme.border; strokeWidth: 3; fillColor: "transparent"
                PathAngleArc { centerX: dial.size / 2; centerY: dial.size / 2; radiusX: dial.size / 2 - 2; radiusY: dial.size / 2 - 2; sweepAngle: 360 }
            }
            ShapePath {
                strokeColor: Theme.accent; strokeWidth: 3; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: dial.size / 2; centerY: dial.size / 2; radiusX: dial.size / 2 - 2; radiusY: dial.size / 2 - 2
                    startAngle: act.lead.fraction >= 0 ? -90 : spin.angle
                    sweepAngle: act.lead.fraction >= 0 ? 360 * Math.max(0.02, act.lead.fraction) : 90
                }
            }
        }
        Text {
            textFormat: Text.PlainText
            anchors.centerIn: parent
            visible: act.lead.fraction >= 0
            text: Math.floor(act.lead.fraction * 100)
            color: Theme.accent
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(9)
            font.weight: Font.DemiBold
        }
        Rectangle {  // more than one thing at once
            visible: act.jobs.length > 1
            width: 14; height: 14; radius: 7
            x: parent.width - 8; y: -4
            color: Theme.accent
            Text {
                anchors.centerIn: parent
                textFormat: Text.PlainText
                text: act.jobs.length
                color: Theme.bg
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(9); font.weight: Font.Bold
            }
        }
    }
    QtObject { id: spin; property real angle: -90 }
    NumberAnimation {
        target: spin; property: "angle"; from: -90; to: 270; duration: 1200
        loops: Animation.Infinite
        running: act.active && act.compact && act.lead.fraction < 0 && !Theme.reduceMotion
    }

    // expanded: the first job's line and bar, and "+ 2 more" when there are others
    Column {
        visible: !act.compact
        anchors { left: parent.left; right: parent.right; top: parent.top }
        spacing: 3
        Text {
            textFormat: Text.PlainText
            width: parent.width
            elide: Text.ElideRight
            text: act.lead.label
            color: Theme.accent
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(11)
        }
        Rectangle {
            id: track
            width: parent.width; height: 3; radius: 2
            color: Theme.border
            clip: true
            Rectangle {
                height: parent.height; radius: 2
                color: Theme.accent
                width: act.lead.fraction >= 0 ? track.width * act.lead.fraction : track.width * 0.3
                x: act.lead.fraction >= 0 ? 0 : sweep.x
                Behavior on width { enabled: act.lead.fraction >= 0; NumberAnimation { duration: 150 } }
            }
            QtObject { id: sweep; property real x: 0 }
            SequentialAnimation {
                running: act.active && !act.compact && act.lead.fraction < 0 && !Theme.reduceMotion
                loops: Animation.Infinite
                onRunningChanged: if (!running) sweep.x = 0
                NumberAnimation { target: sweep; property: "x"; from: 0; to: track.width * 0.7; duration: 900; easing.type: Easing.InOutQuad }
                NumberAnimation { target: sweep; property: "x"; from: track.width * 0.7; to: 0; duration: 900; easing.type: Easing.InOutQuad }
            }
        }
        Text {
            textFormat: Text.PlainText
            visible: act.jobs.length > 1
            text: "+ " + (act.jobs.length - 1) + " more"
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(10)
        }
    }

    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: popup.opened ? popup.close() : popup.open()
    }
    ToolTip.visible: act.compact && hover.containsMouse && !popup.opened
    ToolTip.text: Theme.plain(act.jobs.map(j => j.label).join("\n"))
    ToolTip.delay: 300
    activeFocusOnTab: true
    Keys.onReturnPressed: popup.open()
    Keys.onSpacePressed: popup.open()
    Accessible.role: Accessible.Button
    Accessible.name: "Working in the background: " + act.jobs.map(j => j.label).join("; ")
    Accessible.onPressAction: popup.open()

    // everything running, each with its own Stop
    Popup {
        id: popup
        objectName: "activityPopup"
        x: act.compact ? act.width + 8 : 0
        y: act.compact ? -height + act.height : -height - 8
        width: 320
        padding: 16
        background: Rectangle {
            radius: Theme.round(16)
            color: Theme.panel
            Bevel {}
            border.width: 1
            border.color: Theme.stroke
        }
        onAboutToShow: if (!act.active) close()
        Connections { target: act; function onActiveChanged() { if (!act.active) popup.close() } }
        contentItem: Column {
            spacing: 12
            Text {
                textFormat: Text.PlainText
                text: qsTr("In the background")
                color: Theme.text
                font.family: Theme.displayFamily
                font.pixelSize: (Theme.fontSize(14)) * Theme.displayScale
                font.weight: Font.DemiBold
            }
            Repeater {
                model: act.jobs
                Item {
                    required property var modelData
                    objectName: "activityJob_" + modelData.key
                    width: 288
                    height: 40
                    Text {
                        textFormat: Text.PlainText
                        anchors { left: parent.left; right: stopBtn.left; rightMargin: 10; top: parent.top }
                        elide: Text.ElideRight
                        text: modelData.label
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(12)
                    }
                    Rectangle {
                        anchors { left: parent.left; right: stopBtn.left; rightMargin: 10; bottom: parent.bottom; bottomMargin: 8 }
                        height: 3; radius: 2
                        color: Theme.border
                        Rectangle {
                            height: parent.height; radius: 2
                            color: Theme.accent
                            width: parent.width * (modelData.fraction >= 0 ? modelData.fraction : 0.3)
                            opacity: modelData.fraction >= 0 ? 1 : 0.5
                        }
                    }
                    PillButton {
                        id: stopBtn
                        objectName: "activityStop_" + modelData.key
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                        text: qsTr("Stop")
                        onClicked: modelData.stop()
                    }
                }
            }
        }
    }
}
