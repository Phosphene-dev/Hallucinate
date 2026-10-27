import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "."

Dialog {
    id: dlg
    property var paths: []
    property string albumKey: ""
    property bool albumMode: false
    property bool manyMode: false   // songs picked in a list (they may come from different albums)
    property var mixed: []          // fields whose value differs between those songs
    property var original: ({})
    property string artUrl: ""
    property string message: ""
    property var mbResults: []     // MusicBrainz releases found for this album
    property string mbStatus: ""
    property var trackTags: []     // per-song titles and numbers from the chosen release
    property var genreChoices: []  // genres found online, best first
    property string genreText: ""  // the Genre field as it stands (for the chips)
    // Several genres are one text, the main one first: "IDM; Ambient; Electronic"
    function genreList(text) {
        var out = [], seen = {}
        var parts = String(text || "").split(/\s*[;\/|]\s*/)
        for (var i = 0; i < parts.length; i++) {
            var name = parts[i].trim(), key = name.toLowerCase()
            if (name.length && !seen[key]) { seen[key] = true; out.push(name) }
        }
        return out
    }
    function hasGenre(name) {
        var list = genreList(genreText)
        for (var i = 0; i < list.length; i++) if (list[i].toLowerCase() === name.toLowerCase()) return true
        return false
    }
    function toggleGenre(name) {
        var list = genreList(fieldValue("genre")), out = [], found = false
        for (var i = 0; i < list.length; i++) {
            if (list[i].toLowerCase() === name.toLowerCase()) found = true
            else out.push(list[i])
        }
        if (!found) out.push(name)
        setField("genre", out.join("; "), true)
    }
    property string genreStatus: ""

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    width: Math.min(560, parent ? parent.width - 40 : 560)
    title: albumMode ? "Edit album" : manyMode ? "Edit " + Theme.num(paths.length) + " songs" : "Edit tags"
    standardButtons: Dialog.Save | Dialog.Cancel

    readonly property var keys: albumMode || manyMode
        ? ["album", "album_artist", "artist", "year", "genre", "composer", "work"]
        : ["title", "artist", "album", "album_artist", "track_no", "disc_no", "year", "genre",
           "composer", "work", "movement", "bpm", "music_key"]
    readonly property var labels: ({ title: "Title", artist: "Artist", album: "Album", album_artist: "Album artist",
                                     track_no: "Track #", disc_no: "Disc #", year: "Year", genre: "Genre",
                                     composer: "Composer", work: "Work", movement: "Movement", bpm: "Tempo (BPM)",
                                     music_key: "Key" })
    // fields most songs leave empty: under "More fields" until wanted (or one of them has a value)
    readonly property var extraKeys: ["composer", "work", "movement", "bpm", "music_key"]
    property bool moreShown: false

    function editTrack(path) {
        var info = metaEditor.trackInfo(path)
        if (!info.path) return
        albumMode = false; manyMode = false; mixed = []; albumKey = info.album_key; paths = [path]; load(info); open()
    }
    function editTracks(list) {
        if (list.length === 1) { editTrack(list[0]); return }
        var infos = []
        for (var i = 0; i < list.length; i++) {
            var info = metaEditor.trackInfo(list[i])
            if (info.path) infos.push(info)
        }
        if (!infos.length) return
        albumMode = false; manyMode = true
        paths = infos.map(function (t) { return t.path })
        // a field shared by every song shows its value; one that differs starts empty and is left alone
        var shared = Object.assign({}, infos[0]), differ = []
        var fields = dlg.keys
        for (var k = 0; k < fields.length; k++) {
            for (var j = 1; j < infos.length; j++) {
                if (String(infos[j][fields[k]] || "") !== String(infos[0][fields[k]] || "")) {
                    differ.push(fields[k]); shared[fields[k]] = ""
                    break
                }
            }
        }
        mixed = differ
        albumKey = infos.every(function (t) { return t.album_key === infos[0].album_key }) ? infos[0].album_key : ""
        load(shared); open()
    }
    function editAlbum(key) {
        var tracks = library.albumTracks(key)
        if (!tracks.length) return
        albumMode = true; manyMode = false; mixed = []; albumKey = key
        paths = tracks.map(function (t) { return t.path })
        load(tracks[0]); open()
    }
    function load(info) {
        mbResults = []; mbStatus = ""; trackTags = []; genreChoices = []; genreStatus = ""
        original = info
        artUrl = info.artUrl || ""
        message = ""
        moreShown = false
        for (var i = 0; i < rep.count; i++) {
            var f = rep.itemAt(i)
            var v = info[f.key]
            f.value = (v === undefined || v === null || v === 0) ? "" : String(v)
            if (f.value.length && extraKeys.indexOf(f.key) >= 0) moreShown = true
        }
    }
    onAccepted: {
        var changes = {}
        for (var i = 0; i < rep.count; i++) {
            var f = rep.itemAt(i)
            var old = original[f.key]
            old = (old === undefined || old === null || old === 0) ? "" : String(old)
            if (f.value !== old) changes[f.key] = f.value
        }
        if (Object.keys(changes).length) metaEditor.saveTags(paths, changes)
        if (trackTagsBox.checked && trackTags.length) metaEditor.saveTrackTags(trackTags)
    }
    function fieldValue(key) {
        for (var i = 0; i < rep.count; i++) if (rep.itemAt(i).key === key) return rep.itemAt(i).value
        return String(original[key] || "")
    }
    function findGenre() {
        genreChoices = []
        genreStatus = "Looking it up…"
        metaEditor.findGenre(fieldValue("album_artist") || fieldValue("artist"), fieldValue("album"))
    }
    function setField(key, value, evenEmpty) {
        for (var i = 0; i < rep.count; i++) if (rep.itemAt(i).key === key && (value || evenEmpty)) rep.itemAt(i).value = String(value)
    }

    Connections {
        target: metaEditor
        function onLookupResults(found, why) { dlg.mbResults = found; dlg.mbStatus = why }
        function onReleaseReady(r) {
            if (r.error) { dlg.mbStatus = r.error; return }
            dlg.setField("album", r.fields.album)
            dlg.setField("album_artist", r.fields.album_artist)
            dlg.setField("year", r.fields.year)
            dlg.setField("genre", r.fields.genre)
            dlg.trackTags = r.tracks
            dlg.mbResults = []
            dlg.mbStatus = r.matched ? "Filled in from MusicBrainz. Check the fields, then Save."
                : "Filled in the album from MusicBrainz. Its " + Theme.num(r.releaseTracks) + " tracks don't match this album's "
                  + Theme.num(r.songs) + " songs, so song titles are left as they are."
        }
        function onGenreFound(r) {
            if (!dlg.opened) return
            if (r.error) { dlg.genreStatus = r.error; return }
            dlg.setField("genre", r.genre)
            dlg.genreChoices = r.genres
            var from = (r.sources || ["MusicBrainz"]).join(", ")
            dlg.genreStatus = r.source === "artist"
                ? "No source has a genre for this album, so this is the artist's (from MusicBrainz). Click genres below to add or remove them, or type your own, then Save."
                : "From " + from + ". The first genre is the main one. Click genres below to add or remove them, or type your own, then Save."
        }
        function onCoverResult(ok, msg) { dlg.message = msg; if (ok) dlg.artUrl = library.albumInfo(dlg.albumKey).artUrl || "" }
        function onFailed(msg) { dlg.message = msg }
    }

    FileDialog {
        id: imagePicker
        title: "Choose cover image"
        nameFilters: ["Images (*.png *.jpg *.jpeg)"]
        onAccepted: metaEditor.setCoverFromFile(dlg.albumKey, selectedFile.toString(), embedBox.checked)
    }

    contentItem: ColumnLayout {
        spacing: 10
        Text {
            textFormat: Text.PlainText
            visible: dlg.albumMode || dlg.manyMode
            Layout.fillWidth: true
            text: Theme.num(dlg.paths.length) + " tracks. Only changed fields are written to every track."
                + (dlg.manyMode && dlg.mixed.length ? " Empty fields marked “mixed” differ between them and stay as they are." : "")
            color: Theme.textDim
            wrapMode: Text.WordWrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(12)
        }
        Repeater {
            id: rep
            model: dlg.keys
            RowLayout {
                id: rowItem
                required property string modelData
                property string key: modelData
                property alias value: field.text
                Layout.fillWidth: true
                visible: dlg.moreShown || dlg.extraKeys.indexOf(key) < 0
                Text { Layout.preferredWidth: 96; text: dlg.labels[rowItem.key]; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); textFormat: Text.PlainText }
                TextField {
                    id: field
                    Layout.fillWidth: true
                    selectByMouse: true
                    onAccepted: dlg.accept()  // Enter saves, as in the other dialogs
                    onTextChanged: if (rowItem.key === "genre") dlg.genreText = text
                    Accessible.name: dlg.labels[rowItem.key]
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(14)
                    placeholderText: dlg.mixed.indexOf(rowItem.key) >= 0 ? "mixed"
                                     : rowItem.key === "music_key" ? "Am, F#, 8A…" : rowItem.key === "bpm" ? "120" : ""
                    validator: rowItem.key === "bpm" ? bpmValidator : null
                    placeholderTextColor: Theme.textDim
                    background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: field.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                }
                PillButton {
                    objectName: "findGenre"
                    visible: rowItem.key === "genre"
                    height: 32
                    text: "Find online"
                    enabled: !shell.offlineMode && dlg.fieldValue("album").length > 0
                    onClicked: dlg.findGenre()
                    Accessible.name: "Find the genre online"
                }
            }
        }
        IntValidator { id: bpmValidator; bottom: 0; top: 400 }
        Text {
            textFormat: Text.PlainText
            objectName: "moreTagFields"
            visible: !dlg.moreShown
            text: dlg.albumMode || dlg.manyMode ? "More fields: composer, work" : "More fields: composer, work, movement, tempo, key"
            color: Theme.accent
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12.5); font.weight: Font.DemiBold
            LinkArea { onClicked: dlg.moreShown = true }
        }
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: dlg.genreStatus.length > 0
            text: dlg.genreStatus
            wrapMode: Text.WordWrap
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
        }
        Flow {
            Layout.fillWidth: true
            visible: dlg.genreChoices.length > 0
            spacing: 6
            Repeater {
                model: dlg.genreChoices
                Chip {
                    required property string modelData
                    text: modelData
                    selected: dlg.hasGenre(modelData)
                    onClicked: dlg.toggleGenre(modelData)
                    Accessible.name: (selected ? "Remove " : "Add ") + modelData
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: dlg.albumMode
            spacing: 10
            PillButton {
                objectName: "lookupMusicBrainz"
                text: "Look up on MusicBrainz"
                enabled: !shell.offlineMode
                onClicked: {
                    dlg.mbStatus = "Searching MusicBrainz…"
                    var artist = "", album = ""
                    for (var i = 0; i < rep.count; i++) {
                        if (rep.itemAt(i).key === "album") album = rep.itemAt(i).value
                        if (rep.itemAt(i).key === "album_artist") artist = rep.itemAt(i).value
                    }
                    metaEditor.lookupAlbum(artist, album)
                }
            }
            Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                visible: text.length > 0
                text: dlg.mbStatus
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
        Repeater {
            model: dlg.mbResults
            Rectangle {
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: 48
                radius: Theme.radiusSmall
                color: pick.containsMouse ? Theme.glassHover : Theme.surface
                Column {
                    anchors { left: parent.left; leftMargin: 12; right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                    Text { textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight; text: modelData.title + " · " + modelData.artist; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold }
                    Text {
                        textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                        text: [modelData.year, modelData.country, modelData.format, Theme.num(modelData.tracks) + " tracks", modelData.label].filter(function (x) { return x }).join("  ·  ")
                        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
                    }
                }
                MouseArea {
                    id: pick
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { dlg.mbStatus = "Fetching the release…"; metaEditor.chooseRelease(modelData.id, dlg.albumKey) }
                    Accessible.role: Accessible.Button
                    Accessible.name: "Use " + modelData.title + " by " + modelData.artist + " " + modelData.year
                    Accessible.onPressAction: metaEditor.chooseRelease(modelData.id, dlg.albumKey)
                }
            }
        }
        StyledCheck {
            id: trackTagsBox
            objectName: "mbTrackTitles"
            visible: dlg.trackTags.length > 0
            checked: true
            text: "Also set each song's title and number from MusicBrainz (" + Theme.num(dlg.trackTags.length) + " songs)"
        }
        RowLayout {
            Layout.fillWidth: true
            visible: dlg.albumKey.length > 0  // covers belong to one album
            spacing: 12
            Cover { Layout.preferredWidth: 72; Layout.preferredHeight: 72; radius: Theme.radiusSmall; source: dlg.artUrl }
            ColumnLayout {
                spacing: 6
                RowLayout {
                    spacing: 8
                    PillButton { text: "Choose cover…"; onClicked: imagePicker.open() }
                    PillButton {
                        text: metaEditor.busy ? "Working…" : "Find cover online"
                        enabled: !metaEditor.busy && !shell.offlineMode
                        onClicked: metaEditor.fetchCover(dlg.albumKey, dlg.original.album_artist || dlg.original.artist || "", dlg.original.album || "", embedBox.checked)
                    }
                }
                StyledCheck {
                    id: embedBox
                    text: "Also embed in the audio files"
                    checked: metaEditor.embedCovers
                    onToggled: metaEditor.setEmbedCovers(checked)  // remembered for next time
                }
            }
        }
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: dlg.message.length > 0
            text: dlg.message
            color: Theme.textDim
            wrapMode: Text.WordWrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(12)
        }
    }
}
