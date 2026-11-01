import QtQuick
import "."

// A line under an online service in Settings while offline mode is on: why it can't connect or send, and
// where to turn it off. (Last.fm only greyed its Connect button, which looked like the app was broken.)
Text {
    property string what
    objectName: "offlineNote"
    textFormat: Text.PlainText
    width: parent ? parent.width : 0
    wrapMode: Text.WordWrap
    text: qsTr("Offline mode is on: %1 can't connect, and listens wait to be sent until it's off (Settings → Online & privacy).").arg(what)
    color: Theme.accent
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSize(12)
}
