import QtQuick
import QtQuick.Controls
import "."

// A smart playlist: its tracks are whatever currently matches its rules.
Item {
    id: page
    // Ctrl+A with no row focused (main.qml): the page's list
    function selectAll() { Selection.selectAll(list.toString(), list.model, "song") }
    objectName: "smartPlaylist"
    property int smartId: -1
    property string playlistName: ""
    readonly property var info: userLib.smartRevision >= 0 ? userLib.smartInfo(smartId) : ({})

    Component.onCompleted: userLib.openSmartPlaylist(smartId)
    // gone from view: it needn't be evaluated again after every play and like
    Component.onDestruction: userLib.closeSmartPlaylist(smartId)

    ConfirmDialog {
        id: deleteDlg
        objectName: "deleteSmartPlaylistDialog"
        title: qsTr("Delete this smart playlist?")
        body: "“" + page.playlistName + "” and its rules go away for good. No songs are touched."
        confirmText: qsTr("Delete playlist")
        destructive: true
        onAccepted: { var id = page.smartId; userLib.deleteSmartPlaylist(id); Nav.goHome(); Nav.routeGone("smart", id) }
    }

    ListView {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: list
        anchors.fill: parent
        anchors.leftMargin: 20; anchors.rightMargin: 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: userLib.smartTracks
        ScrollBar.vertical: ScrollBar {}

        KeepAtTop { target: list }  // stays at the top when the header changes height
        header: Item {
            width: list.width
            height: 176
            Column {
                anchors { left: parent.left; leftMargin: 8; right: parent.right; bottom: parent.bottom; bottomMargin: 12 }
                spacing: 8
                Text { text: qsTr("SMART PLAYLIST"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold; textFormat: Text.PlainText }
                Text {
                    textFormat: Text.PlainText
                    text: page.playlistName
                    width: Math.min(implicitWidth, parent.width - 16)
                    elide: Text.ElideRight
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: (Theme.fontSize(30)) * Theme.displayScale
                    font.weight: Font.Bold
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    elide: Text.ElideRight
                    objectName: "smartCount"
                    text: Theme.num(list.count) + (list.count === 1 ? qsTr(" song") : qsTr(" songs")) + " · " + page.info.summary
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                }
                Row {
                    spacing: 10
                    PillButton { primary: true; text: qsTr("Play"); enabled: list.count > 0; onClicked: userLib.playSmartPlaylist(0, false) }
                    PillButton { text: qsTr("Shuffle"); enabled: list.count > 0; onClicked: userLib.playSmartPlaylist(0, true) }
                    PillButton { text: qsTr("Edit rules"); onClicked: Nav.editSmartPlaylist(page.smartId, page.playlistName) }
                    PillButton { text: qsTr("Export"); enabled: list.count > 0; onClicked: Nav.exportPlaylist("smart", page.playlistName) }
                    PillButton { objectName: "deleteSmartPlaylist"; text: qsTr("Delete"); onClicked: deleteDlg.open() }
                }
            }
        }
        footer: Item {
            width: list.width
            height: list.count === 0 ? 300 : 0
            EmptyState {
                anchors.centerIn: parent
                visible: list.count === 0
                icon: "smartlist"
                title: qsTr("Nothing matches yet")
                hint: qsTr("Songs appear here as soon as they match the rules. It updates as you play, like and add music.")
                actionText: qsTr("Edit rules")
                onAction: Nav.editSmartPlaylist(page.smartId, page.playlistName)
            }
        }
        delegate: TrackRow {
            selectionSource: ListView.view ? ListView.view.model : null
            path: model.path
            audioFormat: model.codec
            bitDepth: model.bit_depth || 0
            sampleRate: model.sample_rate || 0
            explicitTag: model.explicit || 0
            audioBitrate: model.bitrate
            rowIndex: index
            context: "smart"
            width: ListView.view.width - 12
            number: index + 1
            title: model.title
            artist: model.artist
            album: model.album
            durText: model.durText
            artUrl: model.artUrl
            current: Rows.currentPath === model.path
            onActivated: userLib.playSmartPlaylist(index, false)
            onEnqueue: player.enqueue(userLib.smartTracks.get(index))
        }
    }
}
