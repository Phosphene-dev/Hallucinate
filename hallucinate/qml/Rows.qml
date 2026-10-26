pragma Singleton
import QtQuick

// What every song row needs to know (which song is playing, which are liked, whether to show format badges),
// read from Python once here rather than once per row. Each Python read from the window has to wait for any
// worker thread busy in Python (a rescan, covers, audio processing), and a page of rows makes hundreds of them:
// that was the freeze while typing a search in a big library.
QtObject {
    readonly property bool showTrackInfo: player.showTrackInfo
    readonly property var badges: shell.songBadges
    readonly property bool explicitBadges: badges.explicitBadges === true
    readonly property bool cleanBadges: badges.cleanBadges === true
    readonly property bool hiResBadges: badges.hiResBadges === true
    readonly property bool bitDepth: badges.bitDepth === true
    readonly property bool masterBadge: badges.masterBadge === true
    readonly property var currentId: player.hasTrack ? player.current.id : -1
    readonly property string currentPath: player.hasTrack ? player.current.path : ""
    // path -> true for every liked song; refreshed when likes change
    readonly property var liked: userLib.likesRevision >= 0 ? userLib.likedLookup() : ({})
}
