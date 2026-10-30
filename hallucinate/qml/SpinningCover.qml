import QtQuick
import "."

// Turns the cover it's put in like a record while the music plays (#135; Settings → Appearance → "Covers in the
// player": still, or a spinning record). Put inside a Cover, which it makes round:
//     Cover { radius: SpinningCover.round ? width / 2 : 14 ...  SpinningCover {} }
// It stops where it is on pause, keeps still with Reduce motion, and lies flat again when switched off.
Item {
    id: spin
    readonly property bool on: shell.ui.spinningArt === "1"
    readonly property Item disc: parent
    anchors.fill: parent
    visible: on
    // the record's look: a spindle hole and a few grooves over the picture
    Repeater {
        model: 2
        Rectangle {
            required property int index
            anchors.centerIn: parent
            width: spin.width * (index ? 0.62 : 0.86); height: width; radius: width / 2
            color: "transparent"
            border.width: 1; border.color: Qt.rgba(0, 0, 0, 0.28)
        }
    }
    Rectangle {
        anchors.centerIn: parent
        width: Math.max(6, spin.width * 0.16); height: width; radius: width / 2
        color: Theme.bg
        border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.25)
    }
    RotationAnimator {
        target: spin.disc
        from: 0; to: 360
        duration: 3600  // a calm half speed, as Now Playing's record turns
        loops: Animation.Infinite
        running: spin.on && spin.disc !== null && spin.disc.visible
        paused: running && (!player.playing || Theme.reduceMotion)
    }
    // (after the animator has let go: straightened at once, it could still write its last angle back)
    onOnChanged: if (!on) Qt.callLater(function () { if (spin.disc) spin.disc.rotation = 0 })
}
