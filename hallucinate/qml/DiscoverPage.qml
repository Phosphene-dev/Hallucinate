import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Discover: music from your own library to find again. Every shelf can be hidden from its own menu (or in
// Settings → Discover), and a hidden shelf isn't even read.
Item {
    id: page
    objectName: "discover"
    Component.onCompleted: { discover.open(); if (online) onlineDiscover.open() }
    Component.onDestruction: if (online) onlineDiscover.stopPreview()

    readonly property bool online: typeof onlineDiscover !== "undefined"
    // the online shelves and the wishlist are switched on and off as features of their own (off unless chosen)
    readonly property var ownSwitches: ["discoverNewReleases", "discoverSimilar", "discoverWishlist"]
    function shelfOn(name) { return ownSwitches.indexOf(name) >= 0 ? shell.features[name] === true : shell.features[name] !== false }
    function setShelf(name, on) { if (ownSwitches.indexOf(name) >= 0) shell.setFeature(name, on); else discover.setShelf(name, on) }
    function hideShelf(name, title) {
        page.setShelf(name, false)
        Nav.notifyAction(qsTr("“%1” hidden. Settings → Discover brings it back").arg(title), qsTr("Undo"),
                         function () { page.setShelf(name, true) })
    }
    readonly property bool onlineShown: online && ((shelfOn("discoverNewReleases") && onlineDiscover.newReleases.length > 0)
                                                   || (shelfOn("discoverSimilar") && onlineDiscover.similarArtists.length > 0)
                                                   || (shelfOn("discoverWishlist") && onlineDiscover.wishlist.length > 0))

    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: col
            objectName: "discoverColumn"
            x: Theme.contentX(parent.width)
            y: 22
            width: Theme.contentWidth(parent.width)
            spacing: 30

            RowLayout {
                width: parent.width
                spacing: 12
                Column {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        textFormat: Text.PlainText
                        text: qsTr("Discover")
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale
                        font.weight: Font.Bold
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: shell.features.discoverNewReleases === true || shell.features.discoverSimilar === true
                              ? qsTr("Music in your own library to find again, worked out on this computer from what you play. The online shelves you turned on send only artist names.")
                              : qsTr("Music in your own library to find again. Worked out on this computer from what you play; nothing is sent anywhere.")
                        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                    }
                }
                IconButton {
                    objectName: "discoverSettings"
                    icon: "settings"
                    tip: qsTr("Discover settings")
                    onClicked: Nav.openSettingsAt("discover")
                }
            }

            EmptyState {
                objectName: "discoverEmpty"
                visible: discover.empty && !discover.loading && !page.onlineShown
                width: parent.width
                icon: "discover"
                title: qsTr("Nothing to suggest yet")
                hint: qsTr("Play some music and come back: suggestions come from what you listen to. Hidden shelves can be brought back in Settings → Discover.")
                actionText: qsTr("Discover settings")
                onAction: Nav.openSettingsAt("discover")
            }

            // --- daily mixes ---------------------------------------------------------------------------
            Column {
                objectName: "mixesShelf"
                visible: page.shelfOn("discoverMixes") && discover.mixes.length > 0
                width: parent.width
                spacing: 14
                ShelfHeader {
                    shelf: "discoverMixes"
                    title: qsTr("Daily mixes")
                    subtitle: qsTr("Made fresh each day from what you play, with a few songs you haven't yet")
                }
                Flow {
                    width: parent.width
                    spacing: 18
                    Repeater {
                        model: discover.mixes
                        MixCard {}
                    }
                }
            }

            // --- new releases (online, off unless chosen) -------------------------------------------------
            Column {
                objectName: "newReleasesShelf"
                visible: page.online && page.shelfOn("discoverNewReleases")
                width: parent.width
                spacing: 14
                ShelfHeader {
                    shelf: "discoverNewReleases"
                    title: qsTr("New releases")
                    subtitle: qsTr("Out lately from artists you play, and not in your library (from MusicBrainz)")
                    online: true
                }
                OnlineNote { busyWith: "releases"; count: onlineDiscover.newReleases.length
                             emptyText: qsTr("Nothing new from the artists you play in the last %1 days.").arg(onlineDiscover.window) }
                Item {
                    visible: onlineDiscover.newReleases.length > 0
                    width: parent.width
                    height: 262
                    ListView {
                        WheelScroll {}
                        id: releaseRow
                        anchors.fill: parent
                        anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                        topMargin: 14; leftMargin: 14; rightMargin: 14
                        contentY: -topMargin
                        orientation: ListView.Horizontal
                        spacing: 20
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        model: onlineDiscover.newReleases
                        delegate: ReleaseCard {}
                    }
                    ShelfArrows { row: releaseRow; anchors.fill: parent }
                }
            }

            AlbumShelf {
                shelf: "discoverForgotten"
                title: qsTr("Forgotten favourites")
                subtitle: qsTr("Albums you played a lot, but not for a while")
                model: discover.forgottenAlbums
            }
            SongShelf {
                shelf: "discoverForgottenSongs"
                listName: "songs"
                title: qsTr("Songs you used to love")
                subtitle: qsTr("Played often, liked or rated highly, then left behind")
                model: discover.forgottenSongs
            }
            Column {
                objectName: "artistsShelf"
                visible: page.shelfOn("discoverForgottenArtists") && discover.forgottenArtists.count > 0
                width: parent.width
                spacing: 14
                ShelfHeader {
                    shelf: "discoverForgottenArtists"
                    title: qsTr("Artists to return to")
                    subtitle: qsTr("Ones you played often, not lately")
                }
                Item {
                    width: parent.width
                    height: 222
                    ListView {
                        WheelScroll {}
                        id: artistRow
                        anchors.fill: parent
                        anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                        topMargin: 14; leftMargin: 14; rightMargin: 14
                        contentY: -topMargin
                        orientation: ListView.Horizontal
                        spacing: 20
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        model: discover.forgottenArtists
                        delegate: ArtistCard {
                            name: model.name
                            subtitle: model.reason || ""
                            artUrl: model.artUrl
                            fromDiscover: true
                        }
                    }
                    ShelfArrows { row: artistRow; anchors.fill: parent }
                }
            }
            // --- artists like yours (online, off unless chosen) --------------------------------------------
            Column {
                objectName: "similarShelf"
                visible: page.online && page.shelfOn("discoverSimilar")
                width: parent.width
                spacing: 14
                ShelfHeader {
                    shelf: "discoverSimilar"
                    title: qsTr("Artists like yours")
                    subtitle: qsTr("Not in your library, but like the artists you play most")
                    online: true
                }
                OnlineNote { busyWith: "similar"; count: onlineDiscover.similarArtists.length
                             emptyText: onlineDiscover.similarSource === "lastfm" && !onlineDiscover.lastfmReady
                                        ? qsTr("Last.fm needs to be set up first (Settings → Scrobbling & sharing), or choose another source in Settings → Discover.")
                                        : qsTr("Nothing found yet: play some music and check again.") }
                Item {
                    visible: onlineDiscover.similarArtists.length > 0
                    width: parent.width
                    height: 236
                    ListView {
                        WheelScroll {}
                        id: similarRow
                        anchors.fill: parent
                        anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                        topMargin: 14; leftMargin: 14; rightMargin: 14
                        contentY: -topMargin
                        orientation: ListView.Horizontal
                        spacing: 20
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        model: onlineDiscover.similarArtists
                        delegate: SimilarCard {}
                    }
                    ShelfArrows { row: similarRow; anchors.fill: parent }
                }
            }
            SongShelf {
                shelf: "discoverDeepCuts"
                listName: "deepCuts"
                title: qsTr("Deep cuts")
                subtitle: qsTr("Songs you've never played by the artists you play most")
                model: discover.deepCuts
            }
            AlbumShelf {
                shelf: "discoverNeverPlayed"
                title: qsTr("Never played")
                subtitle: qsTr("Albums you added a while ago and haven't listened to yet")
                model: discover.neverPlayed
            }

            // --- on this day ----------------------------------------------------------------------------
            Column {
                objectName: "onThisDayShelf"
                visible: page.shelfOn("discoverOnThisDay") && discover.onThisDay.length > 0
                width: parent.width
                spacing: 14
                ShelfHeader {
                    shelf: "discoverOnThisDay"
                    title: qsTr("On this day")
                    subtitle: qsTr("What you listened to around today's date in other years")
                }
                Repeater {
                    model: discover.onThisDay
                    Column {
                        required property var modelData
                        required property int index
                        width: col.width
                        spacing: 10
                        RowLayout {
                            width: parent.width
                            Text {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                text: qsTr("%1  ·  %2").arg(modelData.label).arg(modelData.year)
                                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
                            }
                            PillButton {
                                text: qsTr("Play those songs")
                                height: 30
                                onClicked: discover.playDay(index, 0)
                            }
                        }
                        Item {
                            width: parent.width
                            height: 262
                            ListView {
                                WheelScroll {}
                                id: dayRow
                                anchors.fill: parent
                                anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                                topMargin: 14; leftMargin: 14; rightMargin: 14
                                contentY: -topMargin
                                orientation: ListView.Horizontal
                                spacing: 20
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                model: modelData.albums
                                delegate: AlbumCard {
                                    required property var modelData
                                    albumKey: modelData.album_key
                                    title: modelData.album
                                    subtitle: modelData.album_artist
                                    artist: modelData.album_artist
                                    artUrl: modelData.artUrl
                                    fromDiscover: true
                                }
                            }
                            ShelfArrows { row: dayRow; anchors.fill: parent }
                        }
                    }
                }
            }

            // --- the wishlist (kept on this computer; shown once something is on it) ---------------------
            Column {
                objectName: "wishlistShelf"
                visible: page.online && page.shelfOn("discoverWishlist") && onlineDiscover.wishlist.length > 0
                width: parent.width
                spacing: 10
                ShelfHeader {
                    shelf: "discoverWishlist"
                    title: qsTr("Wishlist")
                    subtitle: qsTr("Albums and artists you want, kept on this computer. They're ticked off when they turn up in your library.")
                }
                Repeater {
                    model: page.online ? onlineDiscover.wishlist : []
                    WishRow {}
                }
            }

            // --- once: the online shelves, offered (they're off unless chosen) ---------------------------
            Rectangle {
                id: offerCard
                objectName: "onlineOffer"
                visible: page.online && shell.features.discoverNewReleases !== true && shell.features.discoverSimilar !== true
                         && shell.uiValue("discoverOnlineOffer", "") !== "no" && !offerGone
                property bool offerGone: false
                width: parent.width
                height: offer.implicitHeight + 32
                radius: Theme.radius
                color: Theme.surface
                border.width: 1
                border.color: Theme.stroke
                Column {
                    id: offer
                    x: 16; y: 16
                    width: parent.width - 32
                    spacing: 10
                    Text {
                        textFormat: Text.PlainText
                        text: qsTr("Look beyond your library?")
                        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold
                    }
                    Text {
                        textFormat: Text.PlainText
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: qsTr("Discover can also show new releases from the artists you play, and artists like yours you don't have yet, with short previews. For that it sends the names of artists you play to MusicBrainz, ListenBrainz or Deezer (nothing else). Each is off until you turn it on, and offline mode stops them.")
                        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        PillButton { objectName: "offerReleases"; height: 30; text: qsTr("Show new releases"); onClicked: shell.setFeature("discoverNewReleases", true) }
                        PillButton { objectName: "offerSimilar"; height: 30; text: qsTr("Show artists like yours"); onClicked: shell.setFeature("discoverSimilar", true) }
                        PillButton {
                            objectName: "offerNo"
                            height: 30
                            text: qsTr("Not now")
                            onClicked: { shell.setUiValue("discoverOnlineOffer", "no"); offerCard.offerGone = true
                                         Nav.notify(qsTr("They're in Settings → Discover whenever you want them")) }
                        }
                    }
                }
            }
        }
    }

    // What an online shelf is doing when it has nothing to show: offline, looking, or nothing found
    component OnlineNote: Text {
        property string busyWith
        property int count
        property string emptyText
        textFormat: Text.PlainText
        width: col.width
        wrapMode: Text.WordWrap
        visible: text.length > 0
        text: onlineDiscover.offline ? (count ? qsTr("Offline mode is on: what was found before is shown, and nothing new is looked up.")
                                              : qsTr("Offline mode is on, so nothing is looked up."))
              : onlineDiscover.busy === busyWith ? qsTr("Looking… %1 of %2").arg(Theme.num(onlineDiscover.done)).arg(Theme.num(onlineDiscover.total))
              : count === 0 ? emptyText : ""
        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
    }

    // A new release: its cover, title, artist and when; click for what to do with it
    component ReleaseCard: Item {
        id: rel
        required property var modelData
        required property int index
        objectName: "release_" + index
        width: 180
        height: 248
        Accessible.role: Accessible.Button
        Accessible.name: qsTr("%1 by %2").arg(modelData.title).arg(modelData.artist)
        activeFocusOnTab: true
        Keys.onReturnPressed: relMenu.popup()
        Keys.onMenuPressed: relMenu.popup()
        Cover {
            id: relCover
            width: 180; height: 180
            radius: Theme.radiusSmall
            source: rel.modelData.cover
            fallback: "♪"
        }
        Rectangle {  // on the wishlist
            visible: rel.modelData.wished
            anchors { right: relCover.right; top: relCover.top; margins: 8 }
            width: 26; height: 26; radius: 13
            color: Theme.accent
            Icon { anchors.centerIn: parent; width: 14; height: 14; name: "heart"; filled: true; color: Theme.onAccent }
        }
        Column {
            anchors { left: parent.left; right: parent.right; top: relCover.bottom; topMargin: 8 }
            spacing: 2
            Text {
                textFormat: Text.PlainText
                width: parent.width; elide: Text.ElideRight
                text: rel.modelData.title
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width; elide: Text.ElideRight
                text: rel.modelData.artist
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width; elide: Text.ElideRight
                text: ({ Album: qsTr("Album"), EP: qsTr("EP"), Single: qsTr("Single") })[rel.modelData.kind]
                      + (rel.modelData.extra.length ? " (" + rel.modelData.extra.join(", ") + ")" : "") + "  ·  " + rel.modelData.date
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
            }
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onClicked: relMenu.popup()
        }
        Menu {
            id: relMenu
            MenuItem {
                objectName: "releaseWish"
                text: rel.modelData.wished ? qsTr("On your wishlist") : qsTr("Add to wishlist"); icon.name: "heart"
                enabled: !rel.modelData.wished
                onTriggered: onlineDiscover.addWish("album", rel.modelData.artist, rel.modelData.title, rel.modelData.link, rel.modelData.id)
            }
            MenuItem { text: qsTr("Look for it…"); icon.name: "search"; onTriggered: onlineDiscover.lookFor(rel.modelData.artist, rel.modelData.title) }
            MenuItem { text: qsTr("Open on MusicBrainz"); icon.name: "discover"; onTriggered: onlineDiscover.openLink(rel.modelData.link) }
            MenuItem { text: qsTr("Go to %1").arg(Theme.plain(rel.modelData.artist)); icon.name: "artist"; onTriggered: Nav.openArtist(rel.modelData.artist) }
            MenuSeparator {}
            MenuItem {
                text: qsTr("Not interested"); icon.name: "close"
                onTriggered: onlineDiscover.notInterestedRelease(rel.modelData.id, qsTr("%1 by %2").arg(rel.modelData.title).arg(rel.modelData.artist))
            }
        }
    }

    // An artist like yours: their picture, name and who they're like; a preview, the wishlist, more in the menu
    component SimilarCard: Item {
        id: sim
        required property var modelData
        required property int index
        objectName: "similar_" + index
        readonly property bool playing: onlineDiscover.previewing === modelData.name
        width: 160
        height: 222
        Accessible.role: Accessible.Button
        Accessible.name: modelData.name
        activeFocusOnTab: true
        Keys.onReturnPressed: simMenu.popup()
        Keys.onMenuPressed: simMenu.popup()
        Cover {
            id: simPic
            width: 160; height: 160
            radius: 80
            source: sim.modelData.picture
            fallback: sim.modelData.name.length ? sim.modelData.name.charAt(0).toUpperCase() : "♪"
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onClicked: simMenu.popup()
        }
        IconButton {
            objectName: "previewButton"
            visible: onlineDiscover.previews !== "off" && !onlineDiscover.offline
            anchors { right: simPic.right; bottom: simPic.bottom; margins: 4 }
            icon: sim.playing ? "pause" : "play"
            tip: sim.playing ? qsTr("Stop the preview") : qsTr("Play a preview")
            onClicked: onlineDiscover.preview(sim.modelData.name)
        }
        Column {
            anchors { left: parent.left; right: parent.right; top: simPic.bottom; topMargin: 8 }
            spacing: 2
            Text {
                textFormat: Text.PlainText
                width: parent.width; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter
                text: sim.modelData.name
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter
                text: sim.playing && onlineDiscover.previewTitle.length ? qsTr("Playing “%1”").arg(onlineDiscover.previewTitle)
                      : qsTr("Like %1").arg(sim.modelData.because.join(", "))
                color: sim.playing ? Theme.accent : Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
        Menu {
            id: simMenu
            MenuItem {
                visible: onlineDiscover.previews !== "off"; height: visible ? implicitHeight : 0
                text: sim.playing ? qsTr("Stop the preview") : qsTr("Play a preview"); icon.name: sim.playing ? "pause" : "play"
                onTriggered: onlineDiscover.preview(sim.modelData.name)
            }
            MenuItem {
                text: sim.modelData.wished ? qsTr("On your wishlist") : qsTr("Add to wishlist"); icon.name: "heart"
                enabled: !sim.modelData.wished
                onTriggered: onlineDiscover.addWish("artist", sim.modelData.name, "", sim.modelData.url, sim.modelData.mbid || "")
            }
            MenuItem { text: qsTr("Look for them…"); icon.name: "search"; onTriggered: onlineDiscover.lookFor(sim.modelData.name, "") }
            MenuItem {
                visible: sim.modelData.url.length > 0; height: visible ? implicitHeight : 0
                text: qsTr("Open their page"); icon.name: "discover"; onTriggered: onlineDiscover.openLink(sim.modelData.url)
            }
            MenuSeparator {}
            MenuItem { text: qsTr("Not interested"); icon.name: "close"; onTriggered: onlineDiscover.notInterestedArtist(sim.modelData.name, sim.modelData.name) }
        }
    }

    // One wish: what it is, your note, and whether it's in your library now
    component WishRow: Rectangle {
        id: wish
        required property var modelData
        required property int index
        objectName: "wish_" + index
        readonly property bool got: modelData.got !== null && modelData.got !== undefined
        width: col.width
        height: 58
        radius: Theme.radiusSmall
        color: wishHover.hovered ? Theme.surfaceHi : "transparent"
        HoverHandler { id: wishHover }
        RowLayout {
            anchors { fill: parent; leftMargin: 12; rightMargin: 8 }
            spacing: 12
            Icon { width: 20; height: 20; name: wish.modelData.kind === "album" ? "album" : "artist"; color: Theme.textDim }
            Column {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    textFormat: Text.PlainText
                    width: parent.width; elide: Text.ElideRight
                    text: wish.modelData.kind === "album" ? qsTr("%1 by %2").arg(wish.modelData.title).arg(wish.modelData.artist) : wish.modelData.artist
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                    font.strikeout: wish.got
                }
                Text {
                    textFormat: Text.PlainText
                    width: parent.width; elide: Text.ElideRight
                    text: wish.got ? qsTr("In your library now") : (wish.modelData.note || qsTr("Added %1").arg(new Date(wish.modelData.added * 1000).toLocaleDateString(Qt.locale(), Locale.ShortFormat)))
                    color: wish.got ? Theme.accent : Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
            }
            PillButton {
                visible: !wish.got
                height: 28
                text: qsTr("Look for it")
                onClicked: onlineDiscover.lookFor(wish.modelData.artist, wish.modelData.title)
            }
            IconButton { icon: "more"; tip: qsTr("More for this wish"); onClicked: wishMenu.popup() }
        }
        Menu {
            id: wishMenu
            MenuItem { text: qsTr("Edit the note…"); icon.name: "edit"; onTriggered: noteDlg.open() }
            MenuItem {
                visible: wish.modelData.link.length > 0; height: visible ? implicitHeight : 0
                text: qsTr("Open its page"); icon.name: "discover"; onTriggered: onlineDiscover.openLink(wish.modelData.link)
            }
            MenuItem {
                visible: wish.got; height: visible ? implicitHeight : 0
                text: qsTr("Go to %1").arg(Theme.plain(wish.modelData.artist)); icon.name: "artist"; onTriggered: Nav.openArtist(wish.modelData.artist)
            }
            MenuSeparator {}
            MenuItem {
                objectName: "wishRemove"
                text: qsTr("Remove from the wishlist"); icon.name: "remove"
                onTriggered: {
                    var w = wish.modelData
                    onlineDiscover.removeWish(w.key)
                    Nav.notifyAction(qsTr("Removed from your wishlist"), qsTr("Undo"),
                                     function () { onlineDiscover.addWish(w.kind, w.artist, w.title, w.link, w.ref) })
                }
            }
        }
        Dialog {
            id: noteDlg
            parent: Overlay.overlay
            anchors.centerIn: parent
            modal: true
            title: qsTr("Note")
            standardButtons: Dialog.Ok | Dialog.Cancel
            onOpened: { noteField.text = wish.modelData.note; noteField.forceActiveFocus() }
            onAccepted: onlineDiscover.setWishNote(wish.modelData.key, noteField.text)
            TextField {
                id: noteField
                implicitWidth: 320
                placeholderText: qsTr("Which edition, where you heard of it…")
                selectByMouse: true
                maximumLength: 300
                onAccepted: noteDlg.accept()
            }
        }
    }

    // A shelf's heading, with its own menu: hide it, or go to Discover's settings
    component ShelfHeader: RowLayout {
        id: header
        property string shelf
        property string title
        property string subtitle
        property bool online: false  // (an online shelf: "Check now" too)
        width: col.width
        SectionHeader { Layout.fillWidth: true; title: header.title; subtitle: header.subtitle }
        IconButton {
            objectName: "shelfMenu_" + header.shelf
            icon: "more"
            tip: qsTr("Options for this shelf")
            onClicked: shelfMenu.popup()
        }
        Menu {
            id: shelfMenu
            MenuItem {
                visible: header.online; height: visible ? implicitHeight : 0
                enabled: !onlineDiscover.offline && onlineDiscover.busy === ""
                text: qsTr("Check now"); icon.name: "repeat"; onTriggered: onlineDiscover.refresh()
            }
            MenuItem { objectName: "hideShelf_" + header.shelf; text: qsTr("Hide this shelf"); icon.name: "close"; onTriggered: page.hideShelf(header.shelf, header.title) }
            MenuItem { text: qsTr("Discover settings…"); icon.name: "settings"; onTriggered: Nav.openSettingsAt("discover") }
        }
    }

    component AlbumShelf: Column {
        id: albumShelf
        property string shelf
        property alias model: row.model
        property string title
        property string subtitle
        objectName: "shelf_" + shelf
        visible: page.shelfOn(shelf) && row.count > 0
        width: col.width
        spacing: 14
        ShelfHeader { shelf: albumShelf.shelf; title: albumShelf.title; subtitle: albumShelf.subtitle }
        Item {
            width: parent.width
            height: 262
            ListView {
                WheelScroll {}
                id: row
                anchors.fill: parent
                anchors.topMargin: -14; anchors.leftMargin: -14; anchors.rightMargin: -14
                topMargin: 14; leftMargin: 14; rightMargin: 14
                contentY: -topMargin
                orientation: ListView.Horizontal
                spacing: 20
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                delegate: AlbumCard {
                    albumKey: model.album_key
                    title: model.album
                    subtitle: model.album_artist
                    artist: model.album_artist
                    artUrl: model.artUrl
                    note: model.reason || ""
                    fromDiscover: true
                    selectionSource: ListView.view ? ListView.view.model : null
                    rowIndex: index
                }
            }
            ShelfArrows { row: row; anchors.fill: parent }
        }
    }

    // A few songs, with more a click away (a long list would push everything else off the page)
    component SongShelf: Column {
        id: songShelf
        property string shelf
        property string listName
        property alias model: songs.model
        property string title
        property string subtitle
        property bool expanded: false
        objectName: "shelf_" + shelf
        visible: page.shelfOn(shelf) && songs.count > 0
        width: col.width
        spacing: 10
        ShelfHeader { shelf: songShelf.shelf; title: songShelf.title; subtitle: songShelf.subtitle }
        Row {
            spacing: 10
            PillButton { text: qsTr("Play all"); height: 30; onClicked: discover.playSongs(songShelf.listName, 0) }
        }
        // (a Column of rows: a shelf holds a couple of dozen songs at most. Rows keep TrackRow's own height: it
        // has no implicit height, and sizing rows by it made every row nothing tall, an empty shelf)
        Column {
            id: songList
            width: parent.width
            Repeater {
                id: songs
                readonly property int shown: songShelf.expanded ? count : Math.min(count, 5)
                delegate: TrackRow {
                    width: songList.width
                    visible: index < songs.shown  // (a Column leaves hidden rows out)
                    number: index + 1
                    title: model.title
                    artist: model.artist
                    album: model.reason || model.album
                    durText: model.durText
                    artUrl: model.artUrl
                    path: model.path
                    context: "discover"
                    rowIndex: index
                    selectionSource: songs.model
                    current: player.current && player.current.path === model.path
                    onActivated: discover.playSongs(songShelf.listName, index)
                    onEnqueue: player.enqueue(songs.model.get(index))
                }
            }
        }
        PillButton {
            visible: songs.count > 5
            height: 30
            text: songShelf.expanded ? qsTr("Show fewer") : qsTr("Show all %1").arg(songs.count)
            onClicked: songShelf.expanded = !songShelf.expanded
        }
    }

    // One daily mix: up to four covers, its name, what's in it; click to play, menu for the rest
    component MixCard: Rectangle {
        id: mix
        required property var modelData
        required property int index
        objectName: "mix_" + index
        width: 220
        height: 300
        radius: Theme.radius
        color: hover.hovered ? Theme.surfaceHi : Theme.surface
        border.width: 1
        border.color: Theme.stroke
        Accessible.role: Accessible.Button
        Accessible.name: modelData.title
        HoverHandler { id: hover }
        Grid {
            id: mosaic
            x: 14; y: 14
            columns: 2
            readonly property real cell: (mix.width - 28) / 2
            Repeater {
                model: 4
                Cover {
                    required property int index
                    width: mosaic.cell; height: mosaic.cell
                    source: mix.modelData.arts.length ? mix.modelData.arts[index % mix.modelData.arts.length] : ""
                }
            }
        }
        Column {
            anchors { left: parent.left; right: parent.right; top: mosaic.bottom; margins: 14 }
            spacing: 4
            Text {
                textFormat: Text.PlainText
                width: parent.width
                elide: Text.ElideRight
                text: mix.modelData.title
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                elide: Text.ElideRight
                text: mix.modelData.subtitle
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Text {
                textFormat: Text.PlainText
                text: qsTr("%1 songs  ·  %2 min").arg(mix.modelData.count).arg(mix.modelData.minutes)
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11)
            }
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onClicked: function (mouse) {
                if (mouse.button === Qt.RightButton) mixMenu.popup()
                else discover.playMix(mix.index, false)
            }
        }
        IconButton {
            anchors { right: parent.right; bottom: parent.bottom; margins: 8 }
            icon: "more"
            tip: qsTr("More for this mix")
            onClicked: mixMenu.popup()
        }
        Keys.onReturnPressed: discover.playMix(mix.index, false)
        Keys.onMenuPressed: mixMenu.popup()
        activeFocusOnTab: true
        Menu {
            id: mixMenu
            MenuItem { text: qsTr("Play"); icon.name: "play"; onTriggered: discover.playMix(mix.index, false) }
            MenuItem { text: qsTr("Shuffle"); icon.name: "shuffle"; onTriggered: discover.playMix(mix.index, true) }
            MenuItem {
                text: qsTr("Add to queue"); icon.name: "queue"
                onTriggered: { discover.queueMix(mix.index); Nav.notify(qsTr("“%1” added to the queue").arg(mix.modelData.title)) }
            }
            MenuItem {
                objectName: "saveMix"
                text: qsTr("Save as a playlist"); icon.name: "playlist"
                onTriggered: {
                    var id = discover.saveMix(mix.index)
                    if (id >= 0) Nav.notifyAction(qsTr("Saved as a playlist: it stays as it is when the mix changes"), qsTr("Open"),
                                                  function () { Nav.openPlaylist(id) })
                }
            }
        }
    }
}
