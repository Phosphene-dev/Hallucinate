import QtQuick
import QtQuick.Controls
import "."

// Playback speed and sleep timer.
Menu {
    id: menu
    Menu {
        id: speedMenu
        icon.name: "wave"
        readonly property bool episode: player.hasTrack && player.current.kind === "episode"
        // podcasts keep a speed of their own, and go up to 3×
        title: (episode ? "Podcast speed" : "Playback speed") + (player.speed !== 1 ? " (" + player.speed + "×)" : "")
        Repeater {
            model: speedMenu.episode ? [0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3] : [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2]
            MenuItem {
                required property real modelData
                text: modelData + "×"
                checkable: true
                checked: Math.abs(player.speed - modelData) < 0.001
                onTriggered: player.setSpeed(modelData)
            }
        }
    }
    Menu {
        icon.name: "history"
        title: "Sleep timer" + (player.sleepRemaining >= 0 ? " (" + Math.ceil(player.sleepRemaining / 60) + " min)" : player.sleepAfterTrack ? " (end of track)" : player.sleepAfterAlbum ? " (end of album)" : "")
        MenuItem { text: "Off"; onTriggered: player.setSleepMinutes(0) }
        MenuItem {
            objectName: "sleepMore"
            visible: player.sleepRemaining >= 0  // a timer is running: give it longer without starting over
            height: visible ? implicitHeight : 0
            text: "+15 minutes"
            onTriggered: player.addSleepMinutes(15)
        }
        Repeater {
            model: [5, 10, 15, 30, 45, 60, 90]
            MenuItem {
                required property int modelData
                text: modelData + " minutes"
                onTriggered: player.setSleepMinutes(modelData)
            }
        }
        MenuItem { text: "End of current track"; onTriggered: player.setSleepAfterTrack(true) }
        MenuItem {
            objectName: "sleepAfterAlbum"
            visible: player.hasTrack && !!player.current.album_key
            height: visible ? implicitHeight : 0
            text: "End of this album"
            onTriggered: player.setSleepAfterAlbum(true)
        }
    }
}
