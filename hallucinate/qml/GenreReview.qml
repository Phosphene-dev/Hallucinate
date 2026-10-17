import QtQuick
import QtQuick.Controls
import "."

// What "Find all online" turned up for albums without a genre: tick the ones to keep, change any genre (or pick
// another MusicBrainz suggested), then save them to the files. Nothing is written before Save.
Dialog {
    id: dlg
    objectName: "genreReview"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(720, (parent ? parent.width : 720) - 40)
    height: Math.min(640, (parent ? parent.height : 640) - 60)
    modal: true
    title: "Genres found on MusicBrainz"
    standardButtons: Dialog.Save | Dialog.Cancel
    property int kept: 0
    function recount() { var n = 0; for (var i = 0; i < rows.count; i++) if (rows.get(i).keep) n++; kept = n }
    function setKeep(i, on) { rows.setProperty(i, "keep", on); recount() }

    ListModel { id: rows }
    onAboutToShow: {
        rows.clear()
        var found = metaEditor.genreProposals
        for (var i = 0; i < found.length; i++) {
            var p = found[i]
            rows.append({ albumKey: p.album_key, album: p.album, artist: p.artist, genre: p.genre,
                          choices: p.genres.join("\n"), fromArtist: p.source === "artist", songs: p.songs,
                          keep: p.source !== "artist" })  // an artist's genre is a guess: left for you to tick
        }
        recount()
        keptChanged()
    }
    onKeptChanged: { var save = standardButton(Dialog.Save); if (save) { save.text = "Save " + kept; save.enabled = kept > 0 } }
    onAccepted: {
        var out = []
        for (var i = 0; i < rows.count; i++) {
            var r = rows.get(i)
            if (r.keep && r.genre.trim().length) out.push({ album_key: r.albumKey, genre: r.genre.trim() })
        }
        metaEditor.saveGenres(out)
        Nav.notify(out.length === 1 ? "Saving 1 album's genre" : "Saving genres for " + out.length + " albums")
    }

    Column {
        id: head
        width: dlg.availableWidth
        spacing: 8
        Text {
            textFormat: Text.PlainText
            width: parent.width
            wrapMode: Text.WordWrap
            text: "Ticked albums get their genre written to every song. Genres marked “the artist's” came from the artist "
                  + "because MusicBrainz has none for the album, so they start unticked. Click a genre to change it."
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
        }
        Row {
            spacing: 8
            PillButton { height: 30; text: "Tick all"; onClicked: { for (var i = 0; i < rows.count; i++) dlg.setKeep(i, true) } }
            PillButton { height: 30; text: "Untick all"; onClicked: { for (var i = 0; i < rows.count; i++) dlg.setKeep(i, false) } }
            PillButton {
                height: 30; text: "Discard these"
                onClicked: { metaEditor.clearGenreProposals(); dlg.close() }
            }
        }
    }
    ListView {
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
            width: list.width - 12
            height: 52
            StyledCheck {
                id: keepBox
                anchors { left: parent.left; verticalCenter: parent.verticalCenter }
                checked: row.model.keep
                onToggled: dlg.setKeep(row.index, checked)
                Accessible.name: "Save the genre for " + row.model.album
            }
            Column {
                anchors { left: keepBox.right; leftMargin: 6; right: genreBox.left; rightMargin: 12; verticalCenter: parent.verticalCenter }
                spacing: 2
                Text {
                    textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                    text: row.model.album
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold
                }
                Text {
                    textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                    text: [row.model.artist, row.model.songs === 1 ? "1 song" : row.model.songs + " songs",
                           row.model.fromArtist ? "the artist's genre" : ""].filter(function (x) { return x }).join("  ·  ")
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
                }
            }
            ComboBox {
                id: genreBox
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                width: Math.min(220, row.width * 0.38)
                editable: true
                model: row.model.choices.split("\n")
                Component.onCompleted: editText = row.model.genre
                onEditTextChanged: if (editText !== row.model.genre) rows.setProperty(row.index, "genre", editText)
                onActivated: function (i) { rows.setProperty(row.index, "genre", model[i]); dlg.setKeep(row.index, true) }
                Accessible.name: "Genre for " + row.model.album
            }
        }
    }
}
