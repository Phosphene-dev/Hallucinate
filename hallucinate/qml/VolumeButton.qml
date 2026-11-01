import QtQuick
import QtQuick.Controls
import "."

// The volume icon. Scroll over it to turn the volume up or down; a middle click mutes. A plain click mutes too
// where a slider sits beside it (the player bar); elsewhere (Now Playing, a tight bar) it opens a slider in a
// popup above it.
Item {
    id: vb
    property bool popupSlider: false
    property bool light: false        // white, over Now Playing's dark backdrop
    property real iconSize: 18
    readonly property alias popupOpen: pop.opened
    implicitWidth: iconSize + 12
    implicitHeight: iconSize + 12

    function nudge(steps) { player.nudgeVolume(steps) }  // one notch of the wheel: the volume step

    Accessible.role: Accessible.Button
    Accessible.name: vb.popupSlider ? qsTr("Volume %1%").arg(Math.round(player.volume * 100)) : (player.muted ? qsTr("Unmute") : qsTr("Mute"))
    Accessible.description: qsTr("Scroll to change the volume; middle-click to mute")
    Accessible.onPressAction: vb.popupSlider ? pop.open() : player.toggleMute()

    Rectangle {  // hover and open state, as IconButton has
        anchors.fill: parent
        radius: Theme.round(height / 2)
        color: vb.light ? Qt.rgba(1, 1, 1, area.containsMouse || pop.opened ? 0.14 : 0)
                        : (area.containsMouse || pop.opened ? Theme.glassHover : "transparent")
    }
    Icon {
        id: icon
        anchors.centerIn: parent
        width: vb.iconSize; height: vb.iconSize; name: "volume"
        color: vb.light ? "white" : (area.containsMouse ? Theme.text : Theme.textDim)
        opacity: player.muted ? 0.45 : 1
        Rectangle {  // struck through while muted
            visible: player.muted
            anchors.centerIn: parent
            width: parent.width * 1.2; height: 2; radius: 1
            rotation: -45
            color: vb.light ? "white" : Theme.textDim
        }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        anchors.margins: vb.popupSlider ? 0 : -6
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        onClicked: function (mouse) {
            if (mouse.button === Qt.MiddleButton || !vb.popupSlider) player.toggleMute()
            else if (pop.opened) pop.close()
            else pop.open()
        }
        onWheel: function (wheel) {
            var d = wheel.angleDelta.y !== 0 ? wheel.angleDelta.y / 120 : wheel.pixelDelta.y / 40
            if (d !== 0) vb.nudge(d)
        }
        ToolTip.visible: containsMouse && !pop.opened
        ToolTip.delay: 400
        ToolTip.text: player.muted ? qsTr("Muted — scroll to change, middle-click to unmute")
                                   : qsTr("Volume %1% — scroll to change, middle-click to mute").arg(Math.round(player.volume * 100))
    }

    Popup {
        id: pop
        objectName: "volumePopup"
        width: 56
        height: 190
        x: (vb.width - width) / 2
        y: -height - 10
        padding: 10
        margins: 10
        background: Rectangle {
            radius: Theme.round(18)
            color: Theme.glassStrong
            Bevel {}
            border.width: 1
            border.color: Theme.stroke
        }
        contentItem: Column {
            spacing: 6
            Text {
                textFormat: Text.PlainText
                anchors.horizontalCenter: parent.horizontalCenter
                text: player.muted ? qsTr("Muted") : Math.round(player.volume * 100) + "%"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(11)
                font.weight: Font.DemiBold
            }
            Slider {
                id: vslider
                objectName: "volumePopupSlider"
                anchors.horizontalCenter: parent.horizontalCenter
                orientation: Qt.Vertical
                height: pop.availableHeight - 24
                width: 24
                padding: 0
                from: 0; to: player.maxVolume
                value: player.volume
                onMoved: {
                    player.setVolume(value)
                    if (player.muted && value > 0) player.toggleMute()
                }
                Accessible.name: qsTr("Volume")
                background: Rectangle {
                    x: vslider.leftPadding + vslider.availableWidth / 2 - width / 2
                    y: vslider.topPadding
                    width: Theme.retro ? 6 : 4
                    height: vslider.availableHeight
                    radius: Theme.retro ? 0 : 2
                    color: Theme.surfaceHi
                    Rectangle {  // filled from the bottom up
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: (1 - vslider.visualPosition) * parent.height
                        radius: parent.radius
                        color: Theme.accent
                    }
                    Bevel { sunken: true }
                }
                handle: Rectangle {
                    x: vslider.leftPadding + vslider.availableWidth / 2 - width / 2
                    y: vslider.topPadding + vslider.visualPosition * (vslider.availableHeight - height)
                    width: Theme.retro ? 18 : 14; height: Theme.retro ? 10 : 14
                    radius: Theme.retro ? 0 : width / 2
                    color: Theme.retro ? Theme.panel : Theme.text
                    Bevel {}
                }
                WheelHandler {  // the wheel over the slider moves it in the same steps as over the icon
                    onWheel: event => vb.nudge(event.angleDelta.y !== 0 ? event.angleDelta.y / 120 : event.pixelDelta.y / 40)
                }
            }
        }
    }
}
