import QtQuick
import QtQuick.Controls
import "."

// A smart playlist: its tracks are whatever currently matches its rules.
Item {
    id: page
    objectName: "smartPlaylist"
    property int smartId: -1
    property string playlistName: ""
    readonly property var info: userLib.smartRevision >= 0 ? userLib.smartInfo(smartId) : ({})

    Component.onCompleted: userLib.openSmartPlaylist(smartId)

    ConfirmDialog {
        id: deleteDlg
        objectName: "deleteSmartPlaylistDialog"
        title: "Delete this smart playlist?"
        body: "“" + page.playlistName + "” and its rules go away for good. No songs are touched."
        confirmText: "Delete playlist"
        destructive: true
        onAccepted: { userLib.deleteSmartPlaylist(page.smartId); Nav.goHome() }
    }

    ListView {
        id: list
        anchors.fill: parent
        anchors.leftMargin: 20; anchors.rightMargin: 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: userLib.smartTracks
        ScrollBar.vertical: ScrollBar {}

        header: Item {
            width: list.width
            height: 176
            Column {
                anchors { left: parent.left; leftMargin: 8; right: parent.right; bottom: parent.bottom; bottomMargin: 12 }
                spacing: 8
                Text { text: "SMART PLAYLIST"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold; textFormat: Text.PlainText }
                Text {
                    textFormat: Text.PlainText
                    text: page.playlistName
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.fontSize(30)
                    font.weight: Font.Bold
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width
                    elide: Text.ElideRight
                    text: list.count + " songs · " + page.info.summary
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                }
                Row {
                    spacing: 10
                    PillButton { primary: true; text: "Play"; enabled: list.count > 0; onClicked: userLib.playSmartPlaylist(0, false) }
                    PillButton { text: "Shuffle"; enabled: list.count > 0; onClicked: userLib.playSmartPlaylist(0, true) }
                    PillButton { text: "Edit rules"; onClicked: Nav.editSmartPlaylist(page.smartId, page.playlistName) }
                    PillButton { text: "Export"; enabled: list.count > 0; onClicked: Nav.exportPlaylist("smart", page.playlistName) }
                    PillButton { objectName: "deleteSmartPlaylist"; text: "Delete"; onClicked: deleteDlg.open() }
                }
            }
        }
        footer: Text {
            textFormat: Text.PlainText
            visible: list.count === 0
            width: list.width
            height: 120
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: "No songs match these rules yet."
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(14)
        }
        delegate: TrackRow {
            selectionSource: ListView.view ? ListView.view.model : null
            path: model.path
            audioFormat: model.codec
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
