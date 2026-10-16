import QtQuick
import QtQuick.Controls
import "."

Item {
    id: page
    objectName: "playlist"
    property bool liked: false
    property int playlistId: -1
    property string playlistName: ""
    readonly property var tracksModel: liked ? userLib.likedTracks : userLib.playlistTracks

    Component.onCompleted: if (!liked) userLib.openPlaylist(playlistId)
    function syncName() {
        for (var i = 0; i < userLib.playlists.count; i++)
            if (userLib.playlists.get(i).id === page.playlistId) page.playlistName = userLib.playlists.get(i).name
    }
    // renamed elsewhere (the sidebar's menu): keep the heading in step
    Connections {
        target: userLib.playlists
        enabled: !page.liked
        function onModelReset() { page.syncName() }
        function onDataChanged() { page.syncName() }
        function onRowsInserted() { page.syncName() }
    }

    Dialog {
        id: renameDlg
        anchors.centerIn: parent
        modal: true
        title: "Rename playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: if (nameField.text.trim().length) { userLib.renamePlaylist(page.playlistId, nameField.text.trim()); page.playlistName = nameField.text.trim() }
        TextField { id: nameField; width: 280; text: page.playlistName; selectByMouse: true; onAccepted: renameDlg.accept() }
    }
    ConfirmDialog {
        id: deleteDlg
        objectName: "deletePlaylistDialog"
        title: "Delete this playlist?"
        body: "“" + page.playlistName + "” goes away for good. The songs in it stay in your library."
        confirmText: "Delete playlist"
        destructive: true
        onAccepted: { userLib.deletePlaylist(page.playlistId); Nav.goHome() }
    }

    ListView {
        id: list
        anchors.fill: parent
        anchors.leftMargin: 20; anchors.rightMargin: 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: page.tracksModel
        ScrollBar.vertical: ScrollBar {}

        header: Item {
            width: list.width
            height: 150
            Column {
                anchors { left: parent.left; leftMargin: 8; bottom: parent.bottom; bottomMargin: 12 }
                spacing: 8
                Text { text: page.liked ? "COLLECTION" : "PLAYLIST"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold; textFormat: Text.PlainText }
                Text {
                    textFormat: Text.PlainText
                    text: page.liked ? "Liked Songs" : page.playlistName
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.fontSize(30)
                    font.weight: Font.Bold
                }
                Text { text: list.count + " songs"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                Row {
                    spacing: 10
                    PillButton { primary: true; text: "Play"; enabled: list.count > 0; onClicked: page.liked ? userLib.playLiked(0) : userLib.playPlaylist(0, false) }
                    PillButton { text: "Shuffle"; enabled: list.count > 0; onClicked: page.liked ? (player.setShuffle(true), userLib.playLiked(Math.floor(Math.random() * list.count))) : userLib.playPlaylist(0, true) }
                    PillButton { objectName: "exportPlaylist"; text: "Export"; enabled: list.count > 0; onClicked: Nav.exportPlaylist(page.liked ? "liked" : "playlist", page.liked ? "Liked Songs" : page.playlistName) }
                    PillButton { visible: !page.liked; text: "Rename"; onClicked: { nameField.text = page.playlistName; renameDlg.open() } }
                    PillButton { visible: !page.liked; objectName: "deletePlaylist"; text: "Delete"; onClicked: deleteDlg.open() }
                }
            }
        }
        footer: Item {
            width: list.width
            height: list.count === 0 ? 300 : 0
            EmptyState {
                anchors.centerIn: parent
                visible: list.count === 0
                icon: page.liked ? "heart" : "playlist"
                title: page.liked ? "No liked songs yet" : "This playlist is empty"
                hint: page.liked ? "Tap the heart on any song and it's kept here."
                                 : "Use “…” on a song, or select a few and choose Add to playlist."
            }
        }
        delegate: TrackRow {
            selectionSource: ListView.view ? ListView.view.model : null
            path: model.path
            audioFormat: model.codec
            audioBitrate: model.bitrate
            rowIndex: index
            context: page.liked ? "liked" : "playlist"
            width: ListView.view.width - 12
            number: index + 1
            title: model.title
            artist: model.artist
            album: model.album
            durText: model.durText
            artUrl: model.artUrl
            current: Rows.currentId === model.id
            onActivated: page.liked ? userLib.playLiked(index) : userLib.playPlaylist(index, false)
            onEnqueue: player.enqueue(page.tracksModel.get(index))
        }
    }
}
