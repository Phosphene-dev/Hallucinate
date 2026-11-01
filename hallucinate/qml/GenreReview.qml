import QtQuick
import QtQuick.Controls
import "."

// What "Find all online" turned up for albums without a genre: tick the ones to keep, change any album's genres
// (click the ones found to add or remove them, or type your own), then save them to the files. Nothing is
// written before Save. An album's first genre is its main one.
Dialog {
    id: dlg
    objectName: "genreReview"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(720, (parent ? parent.width : 720) - 40)
    height: Math.min(640, (parent ? parent.height : 640) - 60)
    modal: true
    title: qsTr("Genres found online")
    standardButtons: Dialog.Save | Dialog.Cancel
    property int kept: 0
    function recount() { var n = 0; for (var i = 0; i < rows.count; i++) if (rows.get(i).keep) n++; kept = n }
    function setKeep(i, on) { rows.setProperty(i, "keep", on); recount() }
    function genreList(text) {
        var out = [], parts = String(text || "").split(/\s*[;\/|]\s*/)
        for (var i = 0; i < parts.length; i++) if (parts[i].trim().length && indexIn(out, parts[i].trim()) < 0) out.push(parts[i].trim())
        return out
    }
    function indexIn(list, name) {
        for (var i = 0; i < list.length; i++) if (list[i].toLowerCase() === String(name).toLowerCase()) return i
        return -1
    }
    function toggle(i, name) {
        var list = genreList(rows.get(i).genre), at = indexIn(list, name)
        if (at >= 0) list.splice(at, 1)
        else list.push(name)
        rows.setProperty(i, "genre", list.join("; "))
        setKeep(i, list.length > 0)
    }

    ListModel { id: rows }
    onAboutToShow: {
        rows.clear()
        var found = metaEditor.genreProposals
        for (var i = 0; i < found.length; i++) {
            var p = found[i]
            rows.append({ albumKey: p.album_key, album: p.album, artist: p.artist, genre: p.genre,
                          choices: p.genres.join("\n"), fromArtist: p.source === "artist", songs: p.songs,
                          sources: (p.sources || []).join(", "),
                          keep: p.source !== "artist" })  // an artist's genre is a guess: left for you to tick
        }
        recount()
        keptChanged()
    }
    onKeptChanged: { var save = standardButton(Dialog.Save); if (save) { save.text = qsTr("Save %1").arg(Theme.num(kept)); save.enabled = kept > 0 } }
    onAccepted: {
        var out = []
        for (var i = 0; i < rows.count; i++) {
            var r = rows.get(i)
            if (r.keep && r.genre.trim().length) out.push({ album_key: r.albumKey, genre: r.genre.trim() })
        }
        metaEditor.saveGenres(out)
        Nav.notify(out.length === 1 ? qsTr("Saving 1 album's genre") : Theme.counted(qsTr("Saving genres for %n album(s)", "", out.length), out.length))
    }

    Column {
        id: head
        width: dlg.availableWidth
        spacing: 8
        Text {
            textFormat: Text.PlainText
            width: parent.width
            wrapMode: Text.WordWrap
            text: qsTr("Ticked albums get their genres written to every song; the first is the main one. Click a genre to add or remove it, or type your own (separate several with “;”). Genres marked “the artist's” came from the artist because no source has any for the album, so they start unticked.")
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
        }
        Row {
            spacing: 8
            PillButton { height: 30; text: qsTr("Tick all"); onClicked: { for (var i = 0; i < rows.count; i++) dlg.setKeep(i, true) } }
            PillButton { height: 30; text: qsTr("Untick all"); onClicked: { for (var i = 0; i < rows.count; i++) dlg.setKeep(i, false) } }
            PillButton {
                height: 30; text: qsTr("Discard these")
                onClicked: { metaEditor.clearGenreProposals(); dlg.close() }
            }
        }
    }
    ListView {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: list
        objectName: "genreReviewList"
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
            readonly property var picked: dlg.genreList(row.model.genre)
            onPickedChanged: if (genreBox.text !== row.model.genre) genreBox.text = row.model.genre  // a chip clicked
            width: list.width - 12
            height: Math.max(56, info.height + chips.height + 18)
            StyledCheck {
                id: keepBox
                anchors { left: parent.left; top: parent.top; topMargin: 8 }
                checked: row.model.keep
                onToggled: dlg.setKeep(row.index, checked)
                Accessible.name: qsTr("Save the genres for %1").arg(row.model.album)
            }
            Column {
                id: info
                anchors { left: keepBox.right; leftMargin: 6; right: genreBox.left; rightMargin: 12; top: parent.top; topMargin: 6 }
                spacing: 2
                Text {
                    textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                    text: row.model.album
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold
                }
                Text {
                    textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                    text: [row.model.artist, Theme.counted(qsTr("%n song(s)", "", row.model.songs), row.model.songs),
                           row.model.fromArtist ? qsTr("the artist's genre") : (row.model.sources ? qsTr("from %1").arg(row.model.sources) : "")]
                          .filter(function (x) { return x }).join("  ·  ")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
                }
            }
            TextField {
                id: genreBox
                anchors { right: parent.right; top: parent.top; topMargin: 6 }
                width: Math.min(260, row.width * 0.42)
                selectByMouse: true
                text: row.model.genre
                onTextEdited: rows.setProperty(row.index, "genre", text)
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: genreBox.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                Accessible.name: qsTr("Genres for %1").arg(row.model.album)
            }
            Flow {
                id: chips
                anchors { left: info.left; right: parent.right; top: genreBox.bottom; topMargin: 6 }
                spacing: 4
                visible: row.model.choices.length > 0
                Repeater {
                    model: row.model.choices.length ? row.model.choices.split("\n") : []
                    Chip {
                        required property string modelData
                        implicitHeight: 26
                        text: modelData
                        selected: dlg.indexIn(row.picked, modelData) >= 0
                        onClicked: dlg.toggle(row.index, modelData)
                        Accessible.name: (selected ? qsTr("Remove %1 for %2") : qsTr("Add %1 for %2")).arg(modelData).arg(row.model.album)
                    }
                }
            }
        }
    }
}
