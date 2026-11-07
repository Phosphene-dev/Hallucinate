import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// A daily mix's songs, to look through before playing it, or to play from one of them on (Discover and Home)
Dialog {
    id: mixPreview
    objectName: "mixPreview"
    function show(i) {
        index = i
        mix = discover.mixes[i] || ({})
        songs = discover.mixSongs(i)
        open()
    }
    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    padding: 18
    property int index: -1
    property var mix: ({})
    property var songs: []
    width: Math.min(620, (parent ? parent.width : 800) - 60)
    height: Math.min(640, (parent ? parent.height : 700) - 60)
    title: mix.title || ""
    contentItem: ColumnLayout {
        spacing: 12
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: (mixPreview.mix.subtitle ? mixPreview.mix.subtitle + "  ·  " : "")
                  + qsTr("%1 songs  ·  %2 min").arg(mixPreview.songs.length).arg(mixPreview.mix.minutes || 0)
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
        }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            PillButton {
                objectName: "mixPreviewPlay"
                text: qsTr("Play"); primary: true
                onClicked: { discover.playMix(mixPreview.index, false); mixPreview.close() }
            }
            PillButton {
                text: qsTr("Shuffle")
                onClicked: { discover.playMix(mixPreview.index, true); mixPreview.close() }
            }
            PillButton {
                text: qsTr("Add to queue")
                onClicked: {
                    discover.queueMix(mixPreview.index)
                    Nav.notify(qsTr("“%1” added to the queue").arg(mixPreview.mix.title))
                }
            }
            PillButton {
                text: qsTr("Save as a playlist")
                onClicked: {
                    var id = discover.saveMix(mixPreview.index)
                    if (id >= 0) Nav.notifyAction(qsTr("Saved as a playlist: it stays as it is when the mix changes"),
                                                  qsTr("Open"), function () { mixPreview.close(); Nav.openPlaylist(id) })
                }
            }
        }
        ListView {
            id: mixSongList
            objectName: "mixPreviewSongs"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            model: mixPreview.songs
            delegate: TrackRow {
                required property var modelData
                required property int index
                width: mixSongList.width - 12
                selectionSource: mixPreview.songs
                rowIndex: index
                number: index + 1
                path: modelData.path || ""
                title: modelData.title || ""
                artist: modelData.artist || ""
                album: modelData.album || ""
                durText: modelData.durText || ""
                artUrl: modelData.artUrl || ""
                audioFormat: modelData.codec || ""
                audioBitrate: modelData.bitrate || 0
                bitDepth: modelData.bit_depth || 0
                sampleRate: modelData.sample_rate || 0
                explicitTag: modelData.explicit || 0
                onActivated: { discover.playMixFrom(mixPreview.index, index); mixPreview.close() }
                onEnqueue: player.enqueue(modelData)
            }
        }
    }
}
