import QtQuick
import QtQuick.Controls
import "."

Item {
    id: badge
    property string formatName: ""
    property int bitrate: 0
    readonly property string bitrateText: bitrate > 0 ? qsTr("~%1 kb/s").arg(Theme.num(Math.round(bitrate / 1000))) : ""
    readonly property string label: {
        var format = formatName.trim().toUpperCase()
        if (bitrateText.length)
            return (format.length ? format + " · " : "") + bitrateText
        return format
    }
    readonly property string spokenLabel: {
        var format = formatName.trim().toUpperCase()
        if (bitrate > 0)
            return (format.length ? qsTr("%1 audio, approximately %2 kilobits per second").arg(format)
                                  : qsTr("Audio, approximately %1 kilobits per second")).arg(Theme.num(Math.round(bitrate / 1000)))
        return format.length ? qsTr("%1 audio, bitrate unavailable").arg(format) : qsTr("Audio bitrate unavailable")
    }
    implicitWidth: labelText.implicitWidth + 14
    implicitHeight: 18
    width: implicitWidth
    height: implicitHeight
    visible: label.length > 0
    Accessible.role: Accessible.StaticText
    Accessible.name: spokenLabel

    Rectangle {
        anchors.fill: parent
        radius: Theme.round(height / 2)
        color: Theme.surface
        border.width: 1
        border.color: Theme.border
    }
    Text {
        textFormat: Text.PlainText
        id: labelText
        anchors.centerIn: parent
        text: badge.label
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(10)
    }
    HoverHandler { id: hover }
    ToolTip.visible: hover.hovered
    ToolTip.text: spokenLabel
}
