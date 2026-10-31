import QtQuick
import QtQuick.Controls
import "."

// Add the song to a playlist, playback speed and sleep timer.
Menu {
    id: playback  // not "menu": the playlist items' own `menu` (their submenu) would hide it
    readonly property bool song: player.hasTrack && !(player.current.kind || "").length && (player.current.path || "").length > 0
    Menu {
        id: plSub
        objectName: "nowPlayingPlaylistMenu"
        title: "Add to playlist"
        icon.name: "playlist"
        // which playlists already hold these songs: ticked, and a click takes them out (issue 101)
        property var held: ({})
        property var heldPaths: []
        onAboutToShow: {
            heldPaths = [player.current.path]
            held = userLib.playlistCounts(heldPaths)
            for (var i = 0; i < count; i++) { var it = itemAt(i); if (it && it.have !== undefined) it.checked = it.full }
        }
        enabled: playback.song
        MenuItem { text: "New playlist…"; icon.name: "plus"; onTriggered: Nav.newPlaylistWith([player.current.path]) }
        MenuSeparator {}
        Instantiator {
            model: userLib.playlists
            delegate: MenuItem {
                required property int id
                required property string name
                readonly property int have: plSub.held[String(id)] || 0
                readonly property bool full: have > 0 && have >= plSub.heldPaths.length
                checkable: true
                text: Theme.plain(name) + (have > 0 && !full ? "  (" + Theme.num(have) + " of " + Theme.num(plSub.heldPaths.length) + ")" : "")
                onTriggered: full ? Nav.removeFromPlaylistId(id, name, [player.current.path], "“" + (player.current.title || "This song") + "”")
                                  : Nav.addToPlaylist(id, name, [player.current.path], "“" + (player.current.title || "This song") + "”")
            }
            onObjectAdded: (i, o) => plSub.addItem(o)
            onObjectRemoved: (i, o) => plSub.removeItem(o)
        }
    }
    MenuItem {
        objectName: "nowPlayingSpectrum"
        text: "Spectrum analyzer…"
        icon.name: "wave"
        enabled: playback.song && !/^(subsonic|jellyfin):\/\//.test(player.current.path || "")
        onTriggered: Nav.openSpectrum(player.current.path)
    }
    MenuSeparator {}
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
                text: Theme.num(modelData) + " minutes"
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
