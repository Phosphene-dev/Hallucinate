import QtQuick
import QtQuick.Controls
import "."

// What Library health's "Find all" turned up for albums without a year, albums without track numbers or songs
// without an artist or album: tick the ones to keep, change any year, artist or album, then save them to the
// files. Nothing is written before Save, and only what's still missing then.
Dialog {
    id: dlg
    objectName: "fixReview"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(760, (parent ? parent.width : 760) - 40)
    height: Math.min(640, (parent ? parent.height : 640) - 60)
    modal: true
    property string kind: metaEditor.fixKind
    title: kind === "year" ? qsTr("Years found") : kind === "numbers" ? qsTr("Track numbers found") : qsTr("Artists and albums found")
    standardButtons: Dialog.Save | Dialog.Cancel
    property int kept: 0
    function recount() { var n = 0; for (var i = 0; i < rows.count; i++) if (rows.get(i).keep) n++; kept = n }
    function setKeep(i, on) { rows.setProperty(i, "keep", on); recount() }
    function sourceText(source, note) {
        if (source === "MusicBrainz") return note ? qsTr("from MusicBrainz: %1").arg(note) : qsTr("from MusicBrainz")
        return dlg.kind === "untagged" ? qsTr("from its folder and file names") : qsTr("from the file and folder names")
    }
    function numbered(tracks) {
        var out = []
        for (var i = 0; i < tracks.length; i++) {
            var t = tracks[i]
            out.push((t.disc_no > 0 ? t.disc_no + "-" : "") + t.track_no + ". " + t.title)
        }
        return out.join("   ")
    }

    // (the proposals as they came; rows holds what you've changed and ticked)
    property var found: []
    ListModel { id: rows }
    onAboutToShow: {
        rows.clear()
        found = metaEditor.fixProposals
        for (var i = 0; i < found.length; i++) {
            var p = found[i]
            rows.append({ at: i, title: p.title || "", artist: p.artist || "", album: p.album || "",
                          year: p.year ? String(p.year) : "", songs: p.songs || 0,
                          fillArtist: !!p.fill_artist, fillAlbum: !!p.fill_album,
                          detail: p.kind === "numbers" ? numbered(p.tracks || []) : "",
                          source: p.source || "", note: p.note || "", keep: true })
        }
        recount()
        keptChanged()
    }
    onKeptChanged: { var save = standardButton(Dialog.Save); if (save) { save.text = qsTr("Save %1").arg(Theme.num(kept)); save.enabled = kept > 0 } }
    onAccepted: {
        var out = []
        for (var i = 0; i < rows.count; i++) {
            var r = rows.get(i)
            if (!r.keep) continue
            var p = found[r.at]
            var item = { kind: p.kind, key: p.key }
            if (p.kind === "year") { if (!/^\d{4}$/.test(r.year.trim())) continue; item.year = r.year.trim() }
            else if (p.kind === "numbers") item.tracks = p.tracks
            else {
                item.paths = p.paths
                item.fill_artist = p.fill_artist && r.artist.trim().length > 0; item.artist = r.artist.trim()
                item.fill_album = p.fill_album && r.album.trim().length > 0; item.album = r.album.trim()
                if (!item.fill_artist && !item.fill_album) continue
            }
            out.push(item)
        }
        metaEditor.saveFixes(out)
        if (out.length) Nav.notify(Theme.counted(qsTr("Saving %n change(s) to your files", "", out.length), out.length))
    }

    Column {
        id: head
        width: dlg.availableWidth
        spacing: 8
        Text {
            textFormat: Text.PlainText
            width: parent.width
            wrapMode: Text.WordWrap
            text: dlg.kind === "year" ? qsTr("Ticked albums get this year written to every song. Change any that look wrong; MusicBrainz's is the earliest release it knows.")
                  : dlg.kind === "numbers" ? qsTr("Ticked albums get these track numbers written to their songs, in the order shown.")
                  : qsTr("Ticked songs get the artist or album guessed from their folders and file names. Only what's missing is filled; change any guess that's wrong, or clear it to leave that tag alone.")
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
        }
        Row {
            spacing: 8
            PillButton { height: 30; text: qsTr("Tick all"); onClicked: { for (var i = 0; i < rows.count; i++) dlg.setKeep(i, true) } }
            PillButton { height: 30; text: qsTr("Untick all"); onClicked: { for (var i = 0; i < rows.count; i++) dlg.setKeep(i, false) } }
            PillButton {
                height: 30; text: qsTr("Discard these")
                onClicked: { metaEditor.clearFixProposals(); dlg.close() }
            }
        }
    }
    ListView {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: list
        objectName: "fixReviewList"
        anchors { left: parent.left; right: parent.right; top: head.bottom; topMargin: 12; bottom: parent.bottom }
        clip: true
        model: rows
        spacing: 2
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        delegate: Item {
            id: row
            required property int index
            required property var model
            width: list.width - 12
            height: Math.max(56, info.height + 14, fields.height + 14)
            StyledCheck {
                id: keepBox
                anchors { left: parent.left; top: parent.top; topMargin: 8 }
                checked: row.model.keep
                onToggled: dlg.setKeep(row.index, checked)
                Accessible.name: qsTr("Save the change for %1").arg(row.model.title || row.model.note)
            }
            Column {
                id: info
                anchors { left: keepBox.right; leftMargin: 6; right: fields.left; rightMargin: 12; top: parent.top; topMargin: 6 }
                spacing: 2
                Text {
                    textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                    visible: dlg.kind !== "untagged"
                    text: row.model.title
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold
                }
                Text {
                    textFormat: Text.PlainText; width: parent.width; elide: Text.ElideMiddle
                    visible: dlg.kind === "untagged"
                    text: row.model.note  // the folder
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold
                }
                Text {
                    textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                    text: [dlg.kind === "untagged" ? "" : row.model.artist,
                           Theme.counted(qsTr("%n song(s)", "", row.model.songs), row.model.songs),
                           dlg.sourceText(row.model.source, dlg.kind === "untagged" ? "" : row.model.note)]
                          .filter(function (x) { return x }).join("  ·  ")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
                }
                Text {
                    textFormat: Text.PlainText; width: parent.width
                    visible: row.model.detail.length > 0
                    wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                    text: row.model.detail
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
                }
            }
            Column {
                id: fields
                anchors { right: parent.right; top: parent.top; topMargin: 6 }
                width: dlg.kind === "numbers" ? 0 : dlg.kind === "year" ? 90 : Math.min(300, row.width * 0.45)
                spacing: 4
                FixField {
                    visible: dlg.kind === "year"
                    objectName: "fixYear"
                    text: row.model.year
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: RegularExpressionValidator { regularExpression: /\d{0,4}/ }
                    onTextEdited: rows.setProperty(row.index, "year", text)
                    Accessible.name: qsTr("Year for %1").arg(row.model.title)
                }
                FixField {
                    visible: dlg.kind === "untagged" && row.model.fillArtist
                    objectName: "fixArtist"
                    label: qsTr("Artist")
                    placeholderText: qsTr("Leave as it is")
                    text: row.model.artist
                    onTextEdited: rows.setProperty(row.index, "artist", text)
                    Accessible.name: qsTr("Artist for the songs in %1").arg(row.model.note)
                }
                FixField {
                    visible: dlg.kind === "untagged" && row.model.fillAlbum
                    objectName: "fixAlbum"
                    label: qsTr("Album")
                    placeholderText: qsTr("Leave as it is")
                    text: row.model.album
                    onTextEdited: rows.setProperty(row.index, "album", text)
                    Accessible.name: qsTr("Album for the songs in %1").arg(row.model.note)
                }
            }
        }
    }

    component FixField: TextField {
        property string label  // shown inside the field, before what you type
        width: parent.width
        selectByMouse: true
        leftPadding: label ? fieldLabel.implicitWidth + 18 : 10
        Text {
            textFormat: Text.PlainText
            id: fieldLabel
            visible: parent.label.length > 0
            anchors { left: parent.left; leftMargin: 10; verticalCenter: parent.verticalCenter }
            text: parent.label
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
        }
        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
        background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: parent.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
    }
}
