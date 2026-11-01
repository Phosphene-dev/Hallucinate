import QtQuick
import QtQuick.Controls
import "."

// A song's small badges, beside its title: E for explicit lyrics (from the file's tags), Hi-Res for lossless
// audio of 24 bits or more (1 bit is DSD), and the bit depth itself when asked for. Each can be switched off
// in Settings → Appearance; with nothing to show it takes no room.
Row {
    id: badges
    property int explicitTag: 0      // 1 explicit, 2 clean, 0 not known
    property int bitDepth: 0
    property int sampleRate: 0
    property bool light: false       // white, over Now Playing's dark backdrop
    property real size: 16
    readonly property bool showExplicit: Rows.explicitBadges && explicitTag === 1
    readonly property bool showClean: Rows.cleanBadges && explicitTag === 2
    readonly property bool hiRes: bitDepth >= 24 || bitDepth === 1
    readonly property bool showHiRes: Rows.hiResBadges && hiRes
    readonly property bool showDepth: Rows.bitDepth && bitDepth > 0
    readonly property bool master: showHiRes && Rows.masterBadge  // a gold M instead of the "Hi-Res" pill
    readonly property bool pill: (showHiRes && !master) || showDepth
    readonly property color gold: light ? "#f5cf5b" : (Theme.light ? "#b07d00" : "#e2b53e")
    readonly property string depthText: bitDepth === 1 ? qsTr("DSD")
        : bitDepth + "-bit" + (sampleRate > 0 ? " · " + (sampleRate / 1000).toFixed(sampleRate % 1000 ? 1 : 0) + " kHz" : "")
    readonly property color ink: light ? Qt.rgba(1, 1, 1, 0.85) : Theme.textDim
    spacing: 4
    visible: showExplicit || showClean || master || pill

    Rectangle {
        objectName: "explicitBadge"
        visible: badges.showExplicit
        anchors.verticalCenter: parent.verticalCenter
        width: badges.size; height: badges.size
        radius: Theme.round(3)
        color: badges.ink
        Text {
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: "E"
            color: badges.light ? "black" : Theme.bg
            font.family: Theme.fontFamily
            font.pixelSize: Math.round(badges.size * 0.66)
            font.weight: Font.Bold
        }
        Accessible.role: Accessible.StaticText
        Accessible.name: "Explicit"
        HoverHandler { id: eHover }
        ToolTip.visible: eHover.hovered
        ToolTip.text: qsTr("Explicit")
    }
    Rectangle {
        objectName: "cleanBadge"
        visible: badges.showClean
        anchors.verticalCenter: parent.verticalCenter
        width: badges.size; height: badges.size
        radius: Theme.round(3)
        color: "transparent"
        border.width: 1
        border.color: badges.ink
        Text {
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: "C"
            color: badges.ink
            font.family: Theme.fontFamily
            font.pixelSize: Math.round(badges.size * 0.66)
            font.weight: Font.Bold
        }
        Accessible.role: Accessible.StaticText
        Accessible.name: "Clean version"
        HoverHandler { id: cHover }
        ToolTip.visible: cHover.hovered
        ToolTip.text: qsTr("Clean version")
    }
    Rectangle {
        objectName: "masterBadge"
        visible: badges.master
        anchors.verticalCenter: parent.verticalCenter
        width: badges.size; height: badges.size
        radius: Theme.round(3)
        color: "transparent"
        border.width: 1
        border.color: badges.gold
        Text {
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: "M"
            color: badges.gold
            font.family: Theme.fontFamily
            font.pixelSize: Math.round(badges.size * 0.66)
            font.weight: Font.Bold
        }
        Accessible.role: Accessible.StaticText
        Accessible.name: "Master (Hi-Res), " + (badges.bitDepth === 1 ? qsTr("DSD") : badges.bitDepth + "-bit")
        HoverHandler { id: mHover }
        ToolTip.visible: mHover.hovered
        ToolTip.text: "Master (Hi-Res) · " + (badges.bitDepth === 1 ? qsTr("DSD (1-bit)") : badges.depthText)
    }
    Rectangle {
        objectName: "hiResBadge"
        visible: badges.pill
        anchors.verticalCenter: parent.verticalCenter
        width: depthLabel.implicitWidth + 10; height: badges.size
        radius: Theme.round(height / 2)
        readonly property bool hiResLook: badges.showHiRes && !badges.master
        color: hiResLook ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, badges.light ? 0.35 : 0.16)
                                : "transparent"
        border.width: 1
        border.color: hiResLook ? Theme.accent : (badges.light ? Qt.rgba(1, 1, 1, 0.4) : Theme.border)
        Text {
            textFormat: Text.PlainText
            id: depthLabel
            anchors.centerIn: parent
            text: parent.hiResLook ? (badges.showDepth ? "Hi-Res " + badges.depthText : qsTr("Hi-Res")) : badges.depthText
            color: parent.hiResLook ? (badges.light ? "white" : Theme.accent) : badges.ink
            font.family: Theme.fontFamily
            font.pixelSize: Math.round(badges.size * 0.6)
            font.weight: Font.DemiBold
        }
        Accessible.role: Accessible.StaticText
        Accessible.name: (hiResLook ? qsTr("Hi-Res audio, ") : "") + (badges.bitDepth === 1 ? qsTr("DSD") : badges.bitDepth + "-bit")
        HoverHandler { id: dHover }
        ToolTip.visible: dHover.hovered
        ToolTip.text: (hiResLook ? qsTr("Hi-Res: ") : "") + (badges.bitDepth === 1 ? qsTr("DSD (1-bit)") : badges.depthText)
    }
}
