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

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    width: Math.min(560, parent ? parent.width - 40 : 560)
    title: albumMode ? "Edit album" : manyMode ? "Edit " + paths.length + " songs" : "Edit tags"
    standardButtons: Dialog.Save | Dialog.Cancel
    background: Rectangle { radius: Theme.radius; color: Theme.panel; border.color: Theme.border }

    readonly property var keys: albumMode || manyMode
        ? ["album", "album_artist", "artist", "year", "genre"]
        : ["title", "artist", "album", "album_artist", "track_no", "disc_no", "year", "genre"]
    readonly property var labels: ({ title: "Title", artist: "Artist", album: "Album", album_artist: "Album artist",
                                     track_no: "Track #", disc_no: "Disc #", year: "Year", genre: "Genre" })

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
        var fields = ["album", "album_artist", "artist", "year", "genre"]
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
        original = info
        artUrl = info.artUrl || ""
        message = ""
        for (var i = 0; i < rep.count; i++) {
            var f = rep.itemAt(i)
            var v = info[f.key]
            f.value = (v === undefined || v === null || v === 0) ? "" : String(v)
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
    }

    Connections {
        target: metaEditor
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
            text: dlg.paths.length + " tracks. Only changed fields are written to every track."
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
                Text { Layout.preferredWidth: 96; text: dlg.labels[rowItem.key]; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); textFormat: Text.PlainText }
                TextField {
                    id: field
                    Layout.fillWidth: true
                    selectByMouse: true
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(14)
                    placeholderText: dlg.mixed.indexOf(rowItem.key) >= 0 ? "mixed" : ""
                    placeholderTextColor: Theme.textDim
                    background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: field.activeFocus ? Theme.accent : Theme.border }
                }
            }
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
                StyledCheck { id: embedBox; text: "Also embed in the audio files" }
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
