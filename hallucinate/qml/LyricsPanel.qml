import QtQuick
import QtQuick.Controls
import "."

Rectangle {
    id: panel
    color: Theme.glass
    Bevel {}
    radius: Theme.round(24)
    border.width: 1
    border.color: Theme.stroke
    clip: true

    Text {
        textFormat: Text.PlainText
        id: head
        x: 24; y: 18
        text: "Lyrics"
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: (Theme.fontSize(15)) * Theme.displayScale
        font.weight: Font.DemiBold
    }
    Text {
        textFormat: Text.PlainText
        anchors { right: parent.right; rightMargin: 24; baseline: head.baseline }
        visible: lyricsCtl.source.length > 0
        text: lyricsCtl.source
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(11)
    }
    Column {
        anchors.centerIn: parent
        width: parent.width - 48
        spacing: 12
        visible: lyricsCtl.status !== "found"
        Text {
            textFormat: Text.PlainText
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: ({ idle: "Nothing playing", loading: "Looking for lyrics…", none: "No lyrics found for this track",
                     offline: "Couldn’t reach LRCLIB — check your connection",
                     offlinemode: "Offline mode is on, so lyrics can’t be looked up" })[lyricsCtl.status] || ""
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(14)
        }
        PillButton {
            objectName: "lyricsSearchAgain"
            anchors.horizontalCenter: parent.horizontalCenter
            height: 32
            // LRCLIB had nothing last time (or couldn't be reached): look again now, not in a month
            visible: lyricsCtl.onlineLookup && (lyricsCtl.status === "none" || lyricsCtl.status === "offline")
            text: "Search again"
            onClicked: lyricsCtl.searchAgain()
        }
    }

    LyricsTiming {
        id: timingRow
        anchors { right: parent.right; rightMargin: 16; bottom: parent.bottom; bottomMargin: 12 }
    }

    ListView {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: synced
        // Kept clear of the panel's rounded corners: lines scroll in under a margin, not against the edge
        anchors { top: head.bottom; topMargin: 10; left: parent.left; right: parent.right; bottom: parent.bottom
                  bottomMargin: timingRow.visible ? timingRow.height + 16 : 14 }
        topMargin: 8
        bottomMargin: 16
        leftMargin: 24  // a ListView puts its rows at x 0 whatever they say: the margin goes here
        rightMargin: 24
        visible: lyricsCtl.status === "found" && lyricsCtl.synced
        clip: true
        model: lyricsCtl.lines
        spacing: 6
        boundsBehavior: Flickable.StopAtBounds
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: height * 0.35
        preferredHighlightEnd: height * 0.55
        currentIndex: Math.max(0, lyricsCtl.currentLine)
        highlightMoveDuration: 250
        ScrollBar.vertical: ScrollBar {}
        delegate: Text {
            textFormat: Text.PlainText
            required property var modelData
            required property int index
            width: synced.width - synced.leftMargin - synced.rightMargin
            text: modelData.text.length ? modelData.text : "♪"
            wrapMode: Text.WordWrap
            color: index === lyricsCtl.currentLine ? Theme.text : Theme.textDim
            opacity: index === lyricsCtl.currentLine ? 1 : 0.7
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(index === lyricsCtl.currentLine ? 17 : 15)
            font.weight: index === lyricsCtl.currentLine ? Font.DemiBold : Font.Normal
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: player.seek(Math.max(0, modelData.t - lyricsCtl.offset)) }
        }
    }
    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        anchors { top: head.bottom; topMargin: 10; left: parent.left; right: parent.right; bottom: parent.bottom
                  bottomMargin: 14 }
        visible: lyricsCtl.status === "found" && !lyricsCtl.synced
        clip: true
        topMargin: 8
        contentHeight: plainText.implicitHeight + 24
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        Text {
            textFormat: Text.PlainText
            id: plainText
            x: 26
            width: parent.width - 52
            text: lyricsCtl.plain
            wrapMode: Text.WordWrap
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(15)
            lineHeight: 1.25
        }
    }
}
