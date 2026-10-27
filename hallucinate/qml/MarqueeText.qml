import QtQuick
import "."

// One line of text that, when it's too long for its room, glides to its end and back while the music plays
// (#112), instead of ending in "…". Settings → Appearance → "Long song titles": while playing (the default), only
// when pointed at, or never; reduced motion keeps it still. It starts over from the beginning with each new
// text, and goes back to the start, elided, when it stops.
//     MarqueeText { width: 200; text: player.current.title; active: player.playing; font.pixelSize: 14 }
Item {
    id: m
    property string text
    property color color: Theme.text
    property alias font: still.font
    property bool active: true      // whether "while playing" applies now (the player is playing)
    readonly property string mode: shell.ui.marquee || "playing"
    readonly property bool overflows: moving.implicitWidth > width + 1
    readonly property bool scrolling: overflows && width > 20 && !Theme.reduceMotion && mode !== "off"
                                      && ((mode === "playing" && active) || hover.hovered)
    readonly property real travel: Math.max(0, moving.implicitWidth - width)
    property real offset: 0
    implicitWidth: still.implicitWidth
    implicitHeight: still.implicitHeight
    clip: scrolling

    Text {
        id: still
        anchors.fill: parent
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText  // song titles are never markup
        text: m.text
        color: m.color
        elide: Text.ElideRight
        visible: !m.scrolling
    }
    Text {
        id: moving
        objectName: "marqueeMoving"
        x: -m.offset
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText  // song titles are never markup
        text: m.text
        color: m.color
        font: still.font
        visible: m.scrolling
    }
    SequentialAnimation {
        id: glide
        running: m.scrolling
        loops: Animation.Infinite
        PauseAnimation { duration: 1800 }
        NumberAnimation { target: m; property: "offset"; to: m.travel; duration: Math.max(600, m.travel * 1000 / 32); easing.type: Easing.InOutSine }
        PauseAnimation { duration: 1400 }
        NumberAnimation { target: m; property: "offset"; to: 0; duration: Math.max(600, m.travel * 1000 / 32); easing.type: Easing.InOutSine }
    }
    onScrollingChanged: if (!scrolling) offset = 0
    onTextChanged: { offset = 0; if (glide.running) glide.restart() }
    HoverHandler { id: hover; acceptedDevices: PointerDevice.Mouse }
}
