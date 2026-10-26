import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "."

// The spectrum analyzer (#96): a song's spectrogram in a window of its own, as Spek shows it. "Save image" keeps a
// copy in Pictures/Hallucinate. Opened from a song's menu, or the player's ⋯ menu for what's playing.
Window {
    id: win
    objectName: "spectrumWindow"
    title: spectrograms.title ? "Spectrum analyzer – " + spectrograms.title : "Spectrum analyzer"
    width: 1100; height: 620
    minimumWidth: 520; minimumHeight: 340
    color: "#0b0b10"  // the image's own background, so it sits in the window without a seam
    flags: Qt.Window

    function analyse(path) {
        savedNote.text = ""
        spectrograms.open(path)
        win.show()
        win.raise()
        win.requestActivate()
    }
    onClosing: spectrograms.cancel()

    Image {
        id: picture
        objectName: "spectrumImage"
        anchors { left: parent.left; right: parent.right; top: parent.top; bottom: bar.top; margins: 10 }
        source: spectrograms.imageUrl
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        asynchronous: true
        cache: false
    }
    Column {
        anchors.centerIn: picture
        spacing: 12
        visible: spectrograms.busy || spectrograms.error.length > 0
        BusyIndicator { anchors.horizontalCenter: parent.horizontalCenter; running: spectrograms.busy; visible: running }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            textFormat: Text.PlainText
            text: spectrograms.busy ? "Analysing " + (spectrograms.title || "the song") + "…" : spectrograms.error
            color: "#c9c6d6"
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(14)
        }
    }
    Rectangle {
        id: bar
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 58
        color: Theme.panel
        Row {
            anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
            spacing: 10
            PillButton {
                objectName: "spectrumSave"
                primary: true
                text: "Save image"
                enabled: spectrograms.imageUrl.length > 0 && !spectrograms.busy
                onClicked: savedNote.text = spectrograms.save() ? "Saved to " + spectrograms.saved : "Couldn't save the image"
            }
            PillButton {
                visible: spectrograms.saved.length > 0
                text: "Show in folder"
                onClicked: library.showInFolder(spectrograms.saved)
            }
            Text {
                id: savedNote
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(12)
                elide: Text.ElideMiddle
                width: Math.max(0, win.width - 480)
            }
        }
        PillButton {
            anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
            text: "Close"
            onClicked: win.close()
        }
    }
    Shortcut { sequence: "Escape"; onActivated: win.close() }
}
