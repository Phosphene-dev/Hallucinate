import QtQuick
import "."

Rectangle {
    id: row
    objectName: "trackRow"
    property int number: 0
    property string title
    property string artist
    property string album
    property string durText
    property url artUrl
    property bool current: false
    property bool showArt: true
    property bool showAlbum: true
    signal activated()
    property string path: ""
    property string context: ""
    property int rowIndex: -1
    property string audioFormat: ""
    property int audioBitrate: 0
    property int bitDepth: 0
    property int sampleRate: 0
    property int explicitTag: 0
    readonly property bool liked: path.length > 0 && Rows.liked[path] === true
    // The list this row belongs to (its model, or an array of tracks): Shift+click and dragging select across it
    property var selectionSource: null
    // in the playlist that's open: a selection made there can be taken out of it
    property string selectionOrigin: context === "playlist" && userLib.currentPlaylist >= 0 ? "playlist:" + userLib.currentPlaylist : ""
    Pick {
        id: pick
        target: row
        kind: "song"
        entry: row.path.length ? { path: row.path, title: row.title } : null
        source: row.selectionSource
        index: row.rowIndex
        origin: row.selectionOrigin
    }
    readonly property bool selected: pick.selected
    signal enqueue()
    // The second line and the album open the song's artist and album (looked up when clicked, as some lists add
    // to the line, like a play count). Off where the line isn't the artist at all.
    property bool linkArtist: true
    readonly property bool linkable: path.length > 0 && !/^https?:\/\//.test(path)
    // Mouse over the row or the keyboard on it: its buttons show
    readonly property bool showButtons: hh.hovered || row.activeFocus

    height: 52
    radius: Theme.radiusSmall
    color: selected ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, hh.hovered ? 0.24 : 0.17)
                    : hh.hovered ? Theme.surface : "transparent"

    HoverHandler { id: hh }
    activeFocusOnTab: true
    ListKeys { id: listKeys; row: row; pick: pick; onMenu: if (row.path.length) Nav.trackMenu(row.path, row.title, row.context, row.rowIndex) }
    // Space, Enter and the moves are the row's while it has the focus (Space would otherwise play/pause)
    Keys.onShortcutOverride: function (event) {
        var plain = (event.modifiers & ~Qt.KeypadModifier) === Qt.NoModifier
        event.accepted = listKeys.handles(event) || listKeys.selects(event)
            || (plain && [Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter].indexOf(event.key) >= 0)
            || (plain && event.key === Qt.Key_Delete && (row.context === "playlist" || row.context === "liked"))
    }
    Keys.onPressed: function (event) {
        if (pick.keys(event)) return
        if (event.key === Qt.Key_Delete && (row.context === "playlist" || row.context === "liked") && row.path.length) {
            Nav.deleteInList(row.context, row.path, row.rowIndex)
            event.accepted = true
            return
        }
        if (listKeys.handles(event)) listKeys.press(event, row.rowIndex)
    }
    Keys.onSpacePressed: row.activated()
    Keys.onReturnPressed: row.activated()
    Keys.onEnterPressed: row.activated()
    Accessible.role: Accessible.ListItem
    Accessible.name: title + (artist.length ? ", " + artist : "") +
                     (Rows.showTrackInfo && audioFormat.length ? ", " + qsTr("%1 audio").arg(audioFormat) : "") +
                     (quality.showExplicit ? qsTr(", explicit") : "") + (quality.showHiRes ? qsTr(", Hi-Res") : "")
    Accessible.onPressAction: row.activated()
    Accessible.selected: row.selected
    Rectangle { anchors.fill: parent; anchors.margins: -2; radius: Theme.radiusSmall; color: "transparent"; border.width: 2; border.color: Theme.accent; visible: row.activeFocus }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressAndHold: if (row.path.length && !PickDrag.pick) Nav.trackMenu(row.path, row.title, row.context, row.rowIndex)
        onPressed: function (mouse) { if (row.path.length) pick.press(this, mouse) }
        onPositionChanged: function (mouse) { pick.move(this, mouse) }
        onReleased: pick.release(this)
        onCanceled: pick.cancel(this)
        onClicked: function (mouse) { row.click(mouse) }
    }
    // A click on the row (or on its artist or album link with Ctrl or Shift held, which select instead). A plain
    // click plays the song and leaves any selection as it is: songs gathered from several pages stay gathered.
    function click(mouse) {
        if (mouse.button === Qt.RightButton) {
            if (row.path.length) Nav.trackMenu(row.path, row.title, row.context, row.rowIndex)
        } else if (row.path.length && pick.click(mouse)) {
            return
        } else {
            row.activated()
        }
    }
    Item {
        id: numCol
        width: 36
        height: parent.height
        visible: row.number > 0
        Text {
            textFormat: Text.PlainText
            anchors.centerIn: parent
            visible: !hh.hovered && !row.current
            text: row.number
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(13)
        }
        Icon {
            anchors.centerIn: parent
            width: 14; height: 14
            visible: hh.hovered || row.current
            name: "play"
            color: row.current ? Theme.accent : Theme.text
        }
    }
    Cover {
        id: art
        visible: row.showArt
        x: numCol.visible ? numCol.width : 8
        anchors.verticalCenter: parent.verticalCenter
        width: 38; height: 38; radius: Theme.radiusSmall
        source: row.artUrl
    }
    Column {
        id: titles
        x: (row.showArt ? art.x + art.width : (numCol.visible ? numCol.width : 8)) + 12
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(80, (row.showAlbum ? (row.width - x - 260) * 0.55 : row.width - x - 190))
        spacing: 2
        Row {
            width: parent.width
            spacing: 6
            Text {
                textFormat: Text.PlainText
                width: Math.min(implicitWidth, parent.width - (quality.visible ? quality.width + parent.spacing : 0))
                text: row.title
                color: row.current ? Theme.accent : Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(14)
                elide: Text.ElideRight
            }
            QualityBadges {
                id: quality
                anchors.verticalCenter: parent.verticalCenter
                explicitTag: row.explicitTag
                bitDepth: row.bitDepth
                sampleRate: row.sampleRate
                size: Math.round(Theme.fontSize(14))
            }
        }
        Row {
            width: parent.width
            spacing: 6
            Text {
                textFormat: Text.PlainText
                objectName: "trackArtistLink"
                width: Math.max(24, parent.width - (audioBadge.visible ? audioBadge.width : 0) - parent.spacing)
                text: Theme.shown(row.artist)
                color: artistLinkArea.containsMouse ? Theme.text : Theme.textDim
                font.underline: artistLinkArea.containsMouse
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(12)
                elide: Text.ElideRight
                LinkArea {
                    id: artistLinkArea
                    // over the words only, not the empty space after them
                    anchors.fill: undefined
                    width: Math.min(parent.implicitWidth, parent.width); height: parent.height
                    enabled: row.linkArtist && row.linkable && row.artist.length > 0
                    hoverEnabled: true
                    name: "Go to the artist"
                    onClicked: function (mouse) {
                        row.followLink(mouse, function () { var i = library.trackInfo(row.path); Nav.openArtist(i.artist || i.album_artist || "") })
                    }
                }
            }
            AudioInfoBadge {
                id: audioBadge
                formatName: row.audioFormat
                bitrate: row.audioBitrate
                // only with something to say: lists that don't know a song's format draw no empty pill
                visible: Rows.showTrackInfo && label.length > 0
            }
        }
    }
    Text {
        textFormat: Text.PlainText
        visible: row.showAlbum && row.width > 700
        anchors.verticalCenter: parent.verticalCenter
        x: titles.x + titles.width + 16
        width: row.width - x - 190
        text: Theme.shown(row.album)
        color: albumLinkArea.containsMouse ? Theme.text : Theme.textDim
        font.underline: albumLinkArea.containsMouse
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(13)
        elide: Text.ElideRight
        LinkArea {
            id: albumLinkArea
            anchors.fill: undefined
            width: Math.min(parent.implicitWidth, parent.width); height: parent.height
            enabled: row.linkable && row.album.length > 0 && row.context !== "album"
            hoverEnabled: true
            name: "Go to the album"
            onClicked: function (mouse) {
                row.followLink(mouse, function () { var k = library.trackInfo(row.path).album_key; if (k) Nav.openAlbum(k) })
            }
        }
    }
    // A link in the row: a plain click follows it; with Ctrl or Shift it selects like a click on the row does
    function followLink(mouse, follow) {
        if (mouse && (mouse.modifiers & (Qt.ControlModifier | Qt.ShiftModifier))) row.click(mouse)
        else follow()
    }
    IconButton {
        id: moreBtn
        anchors { right: dur.left; rightMargin: 2; verticalCenter: parent.verticalCenter }
        icon: "more"; size: 14
        visible: row.path.length > 0
        opacity: row.showButtons ? 1 : 0
        activeFocusOnTab: false  // the Menu key opens the same menu
        onClicked: Nav.trackMenu(row.path, row.title, row.context, row.rowIndex)
    }
    IconButton {
        id: heartBtn
        anchors { right: moreBtn.visible ? moreBtn.left : dur.left; rightMargin: 0; verticalCenter: parent.verticalCenter }
        icon: "heart"; size: 14
        active: row.liked
        visible: row.path.length > 0 && shell.features.liked !== false
        opacity: (row.showButtons || row.liked) ? 1 : 0
        activeFocusOnTab: false
        onClicked: userLib.toggleLike(row.path)
    }
    IconButton {
        id: addBtn
        anchors { right: heartBtn.visible ? heartBtn.left : dur.left; rightMargin: 0; verticalCenter: parent.verticalCenter }
        icon: "plus"; size: 14
        opacity: row.showButtons ? 1 : 0
        activeFocusOnTab: false
        tip: qsTr("Add to queue")
        // says so: with the queue panel closed, nothing else on screen changes
        onClicked: { row.enqueue(); Nav.notify(qsTr("“%1” added to the queue").arg(row.title)) }
    }
    Text {
        textFormat: Text.PlainText
        id: dur
        anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
        text: row.durText
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(13)
    }
}
