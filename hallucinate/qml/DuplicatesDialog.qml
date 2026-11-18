import QtQuick
import QtQuick.Controls
import "."

// Library health's probable duplicates, reviewed: each set shows its copies, the best one picked to stay (lossless
// first, then the higher bitrate); click another to keep that one instead, or untick a set that's on purpose (a song
// on an album and on a compilation). Merging gives the copy kept the others' likes, plays, ratings, listens and
// playlist places, then takes them out of the library or moves their files to the trash.
Dialog {
    id: dlg
    objectName: "mergeDuplicatesDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(820, (parent ? parent.width : 820) - 40)
    height: Math.min(680, (parent ? parent.height : 680) - 60)
    modal: true
    title: qsTr("Merge duplicates")
    property bool loading: false
    property var groups: []  // [{copies: [...]}], as library.loadDuplicateGroups found them
    property bool trash: shell.uiValue("duplicatesTrash", "0") === "1"
    property int merging: 0  // sets ticked
    property int dropping: 0  // copies that would go
    ListModel { id: rows }

    function show() { open() }
    function recount() {
        var m = 0, d = 0
        for (var i = 0; i < rows.count; i++) if (rows.get(i).merge) { m++; d += dlg.groups[rows.get(i).at].copies.length - 1 }
        merging = m; dropping = d
    }
    function copyText(c) {
        var bits = [c.format || "?"]
        if (c.bits > 0 && c.sampleRate > 0) bits.push(c.bits + "/" + Theme.num(Math.round(c.sampleRate / 100) / 10))
        else if (c.bitrate > 0) bits.push(qsTr("%1 kbps").arg(Theme.num(c.bitrate)))
        if (c.liked) bits.push("♥")
        if (c.plays > 0) bits.push(Theme.counted(qsTr("%n play(s)", "", c.plays), c.plays))
        if (c.remote) bits.push(qsTr("on a music server"))
        if (c.cue) bits.push(qsTr("in a CUE sheet: stays in the library either way"))
        return bits.join("  ·  ")
    }
    onOpened: { loading = true; rows.clear(); groups = []; recount(); library.loadDuplicateGroups() }
    Connections {
        target: library
        function onDuplicateGroupsLoaded(found) {
            if (!dlg.opened) return
            dlg.groups = found
            rows.clear()
            for (var i = 0; i < found.length; i++) {
                var first = found[i].copies[0]
                rows.append({ at: i, title: first.title, artist: first.artist, keep: 0, merge: true })
            }
            dlg.loading = false
            dlg.recount()
        }
    }

    footer: Row {
        spacing: 10
        padding: 16
        layoutDirection: Qt.RightToLeft
        PillButton {
            objectName: "duplicatesMerge"
            primary: true
            enabled: dlg.merging > 0 && !dlg.loading
            text: Theme.counted(qsTr("Merge %n set(s)", "", dlg.merging), dlg.merging)
            onClicked: {
                var out = []
                for (var i = 0; i < rows.count; i++) {
                    var r = rows.get(i)
                    if (!r.merge) continue
                    var copies = dlg.groups[r.at].copies, drop = []
                    for (var j = 0; j < copies.length; j++) if (j !== r.keep) drop.push(copies[j].path)
                    out.push({ keep: copies[r.keep].path, drop: drop })
                }
                shell.setUiValue("duplicatesTrash", dlg.trash ? "1" : "0")
                library.mergeDuplicates(out, dlg.trash)
                dlg.close()
            }
        }
        PillButton { text: qsTr("Close"); onClicked: dlg.close() }
    }

    Column {
        id: head
        width: dlg.availableWidth
        spacing: 10
        Text {
            textFormat: Text.PlainText
            width: parent.width
            wrapMode: Text.WordWrap
            text: qsTr("The same title, artist and length more than once. Of each set, the copy marked ● stays: click another copy to keep that one instead, and untick a set that's on purpose (a song on both an album and a compilation). The copy kept gets the others' likes, plays, ratings, listens and playlist places.")
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
        }
        Row {
            spacing: 8
            Text {
                textFormat: Text.PlainText
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr("The other copies:")
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Chip {
                objectName: "duplicatesHide"
                text: qsTr("Leave the library (files stay)")
                selected: !dlg.trash
                onClicked: dlg.trash = false
            }
            Chip {
                objectName: "duplicatesTrash"
                text: qsTr("Go to the trash")
                selected: dlg.trash
                onClicked: dlg.trash = true
            }
        }
        Text {
            objectName: "duplicatesSummary"
            textFormat: Text.PlainText
            width: parent.width
            wrapMode: Text.WordWrap
            text: dlg.loading ? qsTr("Finding duplicates…")
                  : rows.count === 0 ? qsTr("No probable duplicates")
                  : Theme.counted(qsTr("%n copies to merge away", "", dlg.dropping), dlg.dropping)
                    + (dlg.trash ? "  ·  " + qsTr("a song on a music server only leaves the library") : "")
            color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold
        }
    }
    ListView {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: list
        objectName: "duplicatesList"
        anchors { left: parent.left; right: parent.right; top: head.bottom; topMargin: 10; bottom: parent.bottom }
        clip: true
        model: rows
        spacing: 8
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        delegate: Item {
            id: set
            required property int index
            required property var model
            readonly property var copies: dlg.groups[set.model.at] ? dlg.groups[set.model.at].copies : []
            width: list.width - 12
            height: setCol.height + 8
            StyledCheck {
                id: mergeBox
                anchors { left: parent.left; top: parent.top; topMargin: 2 }
                checked: set.model.merge
                onToggled: { rows.setProperty(set.index, "merge", checked); dlg.recount() }
                Accessible.name: qsTr("Merge the copies of %1").arg(set.model.title)
            }
            Column {
                id: setCol
                anchors { left: mergeBox.right; leftMargin: 6; right: parent.right }
                spacing: 2
                opacity: set.model.merge ? 1 : 0.5
                Text {
                    textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                    text: set.model.artist ? set.model.title + "  —  " + set.model.artist : set.model.title
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold
                }
                Repeater {
                    model: set.copies
                    delegate: Rectangle {
                        id: copy
                        required property int index
                        required property var modelData
                        readonly property bool kept: set.model.keep === copy.index
                        objectName: "dupCopy" + set.index + "_" + copy.index + (kept ? "_kept" : "")
                        width: setCol.width
                        height: copyCol.height + 8
                        radius: Theme.radiusSmall
                        color: kept ? Theme.hoverTint : (pickArea.containsMouse ? Theme.glassHover : "transparent")
                        Text {
                            textFormat: Text.PlainText
                            id: dot
                            x: 8; y: 4
                            text: copy.kept ? "●" : "○"
                            color: copy.kept ? Theme.accent : Theme.textDim
                            font.pixelSize: Theme.fontSize(13)
                        }
                        Column {
                            id: copyCol
                            anchors { left: dot.right; leftMargin: 8; right: parent.right; rightMargin: 8; top: parent.top; topMargin: 4 }
                            Text {
                                textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                                text: (copy.kept ? qsTr("Stays") : qsTr("Goes")) + "  ·  " + dlg.copyText(copy.modelData)
                                color: copy.kept ? Theme.text : Theme.textDim
                                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                            }
                            Text {
                                textFormat: Text.PlainText; width: parent.width; elide: Text.ElideMiddle
                                text: copy.modelData.path
                                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
                            }
                        }
                        MouseArea {
                            id: pickArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: rows.setProperty(set.index, "keep", copy.index)
                        }
                        Accessible.role: Accessible.RadioButton
                        Accessible.name: qsTr("Keep this copy: %1").arg(copy.modelData.path)
                        Accessible.checked: copy.kept
                    }
                }
            }
        }
    }
}
