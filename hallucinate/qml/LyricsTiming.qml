import QtQuick
import "."

// Nudge synced lyrics that run early or late, then save the timing as an .lrc file next to the song.
Row {
    id: timing
    objectName: "lyricsTiming"
    property color tint: Theme.textDim
    spacing: 4
    visible: lyricsCtl.status === "found" && lyricsCtl.synced
    readonly property int offset: lyricsCtl.offset

    IconButton { icon: "minus"; size: 12; tip: "Lyrics later (0.25 s)"; onClicked: lyricsCtl.nudge(-250) }
    Text {
        textFormat: Text.PlainText
        anchors.verticalCenter: parent.verticalCenter
        width: 64
        horizontalAlignment: Text.AlignHCenter
        text: timing.offset === 0 ? "In sync?" : (timing.offset > 0 ? "−" : "+") + (Math.abs(timing.offset) / 1000).toFixed(2) + " s"
        color: timing.tint
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(11)
        MouseArea { anchors.fill: parent; enabled: timing.offset !== 0; cursorShape: Qt.PointingHandCursor; onClicked: lyricsCtl.resetOffset() }
    }
    IconButton { icon: "plus"; size: 12; tip: "Lyrics earlier (0.25 s)"; onClicked: lyricsCtl.nudge(250) }
    Text {
        textFormat: Text.PlainText
        objectName: "saveLyricsTiming"
        anchors.verticalCenter: parent.verticalCenter
        visible: timing.offset !== 0
        leftPadding: 6
        text: "Save"
        color: Theme.accent
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(12)
        font.weight: Font.DemiBold
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Nav.notify(lyricsCtl.saveTiming()) }
    }
}
