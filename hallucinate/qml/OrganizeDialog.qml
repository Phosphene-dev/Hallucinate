import QtQuick
import QtQuick.Controls
import "."

// Organize files: move songs into folders and names made from their tags ("Album Artist/Album/01 Title"),
// inside the music folder each is already in. A preview shows every move first; nothing moves before "Move", a
// file is never moved over another, and the last organize can be undone. Opened from Library health or an
// album's menu (just those albums).
Dialog {
    id: dlg
    objectName: "organizeDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(820, (parent ? parent.width : 820) - 40)
    height: Math.min(680, (parent ? parent.height : 680) - 60)
    modal: true
    title: albumKeys.length ? qsTr("Organize these albums' files") : qsTr("Organize your music files")
    property var albumKeys: []
    readonly property var presetNames: ["artist_album", "artist_year_album", "artist_album_flat", "artist_album_artist_title"]
    readonly property var plan: metaEditor.organizePlan
    property string pattern: shell.uiValue("organizePattern", metaEditor.organizePresets["artist_album"])
    function show(keys) { albumKeys = keys || []; open() }
    function preview() { metaEditor.previewOrganize(pattern.trim(), albumKeys) }
    onOpened: preview()
    onPatternChanged: if (opened) previewTimer.restart()
    Timer { id: previewTimer; interval: 400; onTriggered: dlg.preview() }

    footer: Row {
        spacing: 10
        padding: 16
        layoutDirection: Qt.RightToLeft
        PillButton {
            objectName: "organizeMove"
            primary: true
            text: metaEditor.organizeBusy ? qsTr("Stop") : Theme.counted(qsTr("Move %n song(s)", "", dlg.plan.count || 0), dlg.plan.count || 0)
            // (not while the library is scanning: it would see the files go and come back half way)
            enabled: metaEditor.organizeBusy || ((dlg.plan.count || 0) > 0 && !metaEditor.organizePreviewing && !library.scanning)
            onClicked: {
                if (metaEditor.organizeBusy) { metaEditor.stopOrganizing(); return }
                shell.setUiValue("organizePattern", dlg.pattern.trim())
                metaEditor.organize()
            }
        }
        PillButton { text: qsTr("Close"); enabled: !metaEditor.organizeBusy; onClicked: dlg.close() }
        PillButton {
            objectName: "organizeUndo"
            visible: metaEditor.organizeCanUndo && !metaEditor.organizeBusy
            text: qsTr("Undo the last organize")
            onClicked: metaEditor.undoOrganize()
        }
    }

    Column {
        id: head
        width: dlg.availableWidth
        spacing: 10
        Text {
            textFormat: Text.PlainText
            width: parent.width
            wrapMode: Text.WordWrap
            text: qsTr("Songs are moved into folders and names made from their tags, inside the music folder each is in now. Their likes, plays, ratings and playlists go with them, and so do lyrics files and the folder's cover. A file is never moved over another (it gets “(2)” instead), and the last organize can be undone.")
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
        }
        Flow {
            width: parent.width
            spacing: 6
            Repeater {
                model: dlg.presetNames
                Chip {
                    required property string modelData
                    text: metaEditor.organizePresets[modelData].replace(/\{disc\}/g, "")
                    selected: dlg.pattern === metaEditor.organizePresets[modelData]
                    onClicked: dlg.pattern = metaEditor.organizePresets[modelData]
                }
            }
        }
        TextField {
            id: patternField
            objectName: "organizePattern"
            width: parent.width
            selectByMouse: true
            text: dlg.pattern
            onTextEdited: dlg.pattern = text
            color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: patternField.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
            Accessible.name: qsTr("Folder and file name pattern")
        }
        Text {
            textFormat: Text.PlainText
            width: parent.width
            wrapMode: Text.WordWrap
            text: qsTr("Parts: {albumartist} {artist} {album} {year} {disc} {track} {title} {genre}; “/” starts a folder. {disc} is “2-” on albums with more than one disc.")
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
        }
        Text {
            objectName: "organizeSummary"
            textFormat: Text.PlainText
            width: parent.width
            wrapMode: Text.WordWrap
            text: library.scanning && !metaEditor.organizeBusy ? qsTr("Waiting for the library scan to finish…")
                  : metaEditor.organizeBusy ? qsTr("Moving: %1 of %2").arg(Theme.num(metaEditor.organizeDone)).arg(Theme.num(metaEditor.organizeTotal))
                  : metaEditor.organizePreviewing ? qsTr("Working out where everything goes…")
                  : dlg.plan.error ? dlg.plan.error
                  : [Theme.counted(qsTr("%n song(s) to move", "", dlg.plan.count || 0), dlg.plan.count || 0),
                     dlg.plan.same ? Theme.counted(qsTr("%n already in place", "", dlg.plan.same), dlg.plan.same) : "",
                     dlg.plan.skipped ? Theme.counted(qsTr("%n left where they are (CUE sheets, music servers)", "", dlg.plan.skipped), dlg.plan.skipped) : ""]
                    .filter(function (x) { return x }).join("  ·  ")
            color: dlg.plan.error ? Theme.error : Theme.text
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold
        }
    }
    ListView {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: list
        objectName: "organizeList"
        anchors { left: parent.left; right: parent.right; top: head.bottom; topMargin: 10; bottom: parent.bottom }
        clip: true
        model: dlg.plan.moves || []
        spacing: 2
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        delegate: Column {
            required property var modelData
            width: list.width - 12
            spacing: 1
            Text {
                textFormat: Text.PlainText; width: parent.width; elide: Text.ElideMiddle
                text: modelData.to
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Text {
                textFormat: Text.PlainText; width: parent.width; elide: Text.ElideMiddle
                text: qsTr("from %1").arg(modelData.from)
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
            }
        }
        footer: Text {
            textFormat: Text.PlainText
            visible: (dlg.plan.count || 0) > (dlg.plan.moves || []).length
            topPadding: 6
            text: qsTr("…and %1 more").arg(Theme.num((dlg.plan.count || 0) - (dlg.plan.moves || []).length))
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
        }
    }
}
