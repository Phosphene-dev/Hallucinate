import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "."

// Podcasts: what you were listening to, new episodes, the shows you follow, and finding more.
Item {
    id: page
    objectName: "podcasts"
    property string query: ""

    Connections {
        target: podcasts
        function onMessage(text) { Nav.notify(text) }
    }
    EpisodeMenu { id: episodeMenu }
    Menu {
        id: showMenu
        objectName: "showMenu"
        property var show: ({})
        function showFor(s) { show = s; popup() }
        MenuItem { text: qsTr("Open"); icon.name: "podcast"; onTriggered: Nav.openPodcast(showMenu.show.id) }
        MenuItem { text: qsTr("Check for new episodes"); icon.name: "download"; onTriggered: podcasts.refresh(showMenu.show.id) }
        MenuItem { text: qsTr("Mark all as played"); icon.name: "check"; onTriggered: podcasts.markAllPlayed(showMenu.show.id) }
        MenuSeparator {}
        MenuItem {
            text: qsTr("Unfollow…"); icon.name: "remove"; icon.color: Theme.error
            onTriggered: { unfollowDlg.show = showMenu.show; unfollowDlg.open() }
        }
    }
    ConfirmDialog {
        id: unfollowDlg
        objectName: "unfollowDialog"
        property var show: ({})
        title: qsTr("Unfollow this show?")
        body: "“" + (show.title || "") + "” and where you were in its episodes go away"
              + (show.folder ? qsTr(". The files in its folder stay where they are.") : qsTr(", along with its downloads."))
        confirmText: qsTr("Unfollow")
        destructive: true
        onAccepted: { var id = show.id; podcasts.unfollow(id, true); Nav.routeGone("podcast", id) }
    }
    Dialog {
        id: followDlg
        objectName: "followDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(460, (parent ? parent.width : 460) - 40)
        modal: true
        title: qsTr("Follow a show")
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { feedField.text = ""; feedField.forceActiveFocus() }
        onAccepted: podcasts.follow(feedField.text)
        Column {
            width: followDlg.availableWidth
            spacing: 10
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Paste the show's RSS feed link. Most show websites list it as “RSS”.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            TextField {
                id: feedField
                width: parent.width
                placeholderText: "https://…/feed.xml"
                selectByMouse: true
                Accessible.name: "Feed link"
                onAccepted: followDlg.accept()
            }
        }
    }
    FolderDialog {
        id: folderDlg
        title: qsTr("Choose a folder of episodes")
        onAccepted: podcasts.addFolder(selectedFolder.toString())
    }
    FileDialog {
        id: importDlg
        title: qsTr("Import shows (OPML)")
        nameFilters: [qsTr("OPML files (*.opml *.xml)"), qsTr("All files (*)")]
        onAccepted: Nav.notify(podcasts.importOpml(selectedFile.toString()))
    }
    FileDialog {
        id: exportDlg
        title: qsTr("Export your shows (OPML)")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "opml"
        nameFilters: [qsTr("OPML file (*.opml)")]
        onAccepted: Nav.notify(podcasts.exportOpml(selectedFile.toString()))
    }

    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        id: fl
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: col
            x: Theme.contentX(fl.width); y: 20
            width: Theme.contentWidth(fl.width)
            spacing: 16

            Column {
                width: parent.width
                spacing: 4
                Text {
                    textFormat: Text.PlainText
                    text: qsTr("Podcasts")
                    color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(25)) * Theme.displayScale; font.weight: Font.Bold
                }
                Text {
                    textFormat: Text.PlainText
                    text: podcasts.busy ? qsTr("Checking feeds…") : podcasts.count === 1 ? qsTr("1 show") : Theme.num(podcasts.count) + " shows"
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                }
            }
            Flow {
                id: actions
                width: parent.width
                spacing: 8
                PillButton { objectName: "followShow"; primary: true; text: qsTr("Follow by link"); onClicked: followDlg.open() }
                PillButton { text: qsTr("Add a folder"); onClicked: folderDlg.open() }
                PillButton { text: qsTr("Check for new"); enabled: podcasts.count > 0 && !podcasts.busy; onClicked: podcasts.refreshAll() }
                PillButton { text: qsTr("Import"); onClicked: importDlg.open() }
                PillButton { text: qsTr("Export"); enabled: podcasts.count > 0; onClicked: exportDlg.open() }
            }

            TextField {
                id: search
                objectName: "podcastSearch"
                width: Math.min(520, parent.width)
                height: 40
                placeholderText: qsTr("Find shows by name or topic")
                color: Theme.text
                placeholderTextColor: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(14)
                leftPadding: 16
                selectByMouse: true
                Accessible.name: "Find shows"
                background: Rectangle { radius: Theme.round(height / 2); color: Theme.surface; border.color: search.activeFocus ? Theme.accent : Theme.border; Bevel { sunken: true } }
                onAccepted: { page.query = text.trim(); podcasts.search(page.query) }
                onTextChanged: if (!text.length) { page.query = ""; podcasts.search("") }
                Keys.onEscapePressed: text = ""
            }
            Text {
                textFormat: Text.PlainText
                visible: podcasts.searching || podcasts.status.length > 0
                text: podcasts.searching ? qsTr("Searching…") : podcasts.status
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Column {
                objectName: "podcastResults"
                width: parent.width
                spacing: 2
                visible: page.query.length > 0 && podcasts.results.count > 0
                SectionHeader { title: qsTr("From the directory"); subtitle: qsTr("Apple Podcasts' public list; only the search words are sent") }
                Repeater {
                    model: podcasts.results
                    Rectangle {
                        required property var model
                        width: col.width
                        height: 56
                        radius: Theme.round(14)
                        color: resultMouse.containsMouse ? Theme.glassHover : "transparent"
                        Column {
                            anchors { left: parent.left; leftMargin: 14; right: followBtn.left; rightMargin: 10; verticalCenter: parent.verticalCenter }
                            spacing: 3
                            Text { textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight; text: model.title; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold }
                            Text { textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight; text: [model.author, model.genre].filter(function (x) { return x }).join("  ·  "); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12) }
                        }
                        MouseArea {
                            id: resultMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.NoButton
                        }
                        PillButton {
                            id: followBtn
                            anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                            text: model.followed ? qsTr("✓ Following") : qsTr("Follow")
                            enabled: !model.followed && !podcasts.busy
                            onClicked: podcasts.followResult(model.row)
                        }
                    }
                }
            }

            SectionHeader { visible: podcasts.upNext.count > 0; title: qsTr("Up next"); subtitle: qsTr("Episodes you've lined up, across shows; they play in this order") }
            Column {
                objectName: "upNextEpisodes"
                width: parent.width
                spacing: 2
                visible: podcasts.upNext.count > 0
                Repeater {
                    model: podcasts.upNext
                    EpisodeRow {
                        required property var model
                        required property int index
                        selectionSource: podcasts.upNext
                        rowIndex: index
                        width: col.width
                        episode: model
                        showPodcast: true
                        upNextRow: true
                        onMenu: episodeMenu.showFor(model, true)
                    }
                }
            }
            SectionHeader { visible: podcasts.inProgress.count > 0; title: qsTr("Continue listening") }
            Column {
                width: parent.width
                spacing: 2
                visible: podcasts.inProgress.count > 0
                Repeater {
                    model: podcasts.inProgress
                    EpisodeRow {
                        required property var model
                        required property int index
                        selectionSource: podcasts.inProgress
                        rowIndex: index
                        width: col.width
                        episode: model
                        showPodcast: true
                        onMenu: episodeMenu.showFor(model, true)
                    }
                }
            }

            SectionHeader { visible: podcasts.latest.count > 0; title: qsTr("New episodes"); subtitle: qsTr("Not played yet, newest first") }
            Column {
                objectName: "latestEpisodes"
                width: parent.width
                spacing: 2
                visible: podcasts.latest.count > 0
                Repeater {
                    model: podcasts.latest
                    EpisodeRow {
                        required property var model
                        required property int index
                        selectionSource: podcasts.latest
                        rowIndex: index
                        width: col.width
                        episode: model
                        showPodcast: true
                        onMenu: episodeMenu.showFor(model, true)
                    }
                }
            }

            SectionHeader { visible: podcasts.count > 0; title: qsTr("Your listening"); subtitle: qsTr("Time spent on podcasts, kept apart from your music's stats") }
            ListeningStrip {
                objectName: "podcastListening"
                visible: podcasts.count > 0
                width: parent.width
                source: podcasts
                countKey: "finished"; countOne: qsTr("episode finished"); countMany: qsTr("episodes finished")
                onOpenItem: function (id) { if (id) Nav.openPodcast(id) }
            }

            SectionHeader { visible: podcasts.count > 0; title: qsTr("Your shows") }
            Flow {
                objectName: "followedShows"
                width: parent.width
                spacing: 16
                Repeater {
                    model: podcasts.shows
                    Item {
                        id: tile
                        required property var model
                        readonly property int across: Math.max(2, Math.floor((col.width + 16) / 176))
                        width: (col.width - (across - 1) * 16) / across
                        height: width + 54
                        Cover {
                            id: showArt
                            width: parent.width; height: parent.width; radius: Theme.round(16)
                            source: tile.model.artUrl
                            fallback: (tile.model.title || "?").charAt(0)
                            Rectangle {
                                visible: tile.model.unplayed > 0
                                anchors { right: parent.right; top: parent.top; margins: 8 }
                                width: Math.max(24, newCount.implicitWidth + 12); height: 24; radius: Theme.round(12)
                                color: Theme.accent
                                Text { id: newCount; anchors.centerIn: parent; text: tile.model.unplayed; color: Theme.onAccent; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: Font.Bold; textFormat: Text.PlainText }
                            }
                        }
                        Text {
                            textFormat: Text.PlainText
                            anchors { top: showArt.bottom; topMargin: 8; left: parent.left; right: parent.right }
                            elide: Text.ElideRight
                            text: tile.model.title
                            color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
                        }
                        Text {
                            textFormat: Text.PlainText
                            anchors { top: showArt.bottom; topMargin: 28; left: parent.left; right: parent.right }
                            elide: Text.ElideRight
                            text: tile.model.error ? qsTr("Couldn't check the feed") : tile.model.detail
                            color: tile.model.error ? Theme.error : Theme.textDim
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onClicked: function (mouse) {
                                mouse.button === Qt.RightButton ? showMenu.showFor(tile.model) : Nav.openPodcast(tile.model.id)
                            }
                            onPressAndHold: showMenu.showFor(tile.model)
                            Accessible.role: Accessible.Button
                            Accessible.name: tile.model.title + ", " + tile.model.detail
                            Accessible.onPressAction: Nav.openPodcast(tile.model.id)
                        }
                    }
                }
            }

            Item { width: 1; height: 20; visible: emptyState.visible }
            EmptyState {
                id: emptyState
                anchors.horizontalCenter: parent.horizontalCenter
                visible: podcasts.count === 0 && page.query.length === 0
                icon: "podcast"
                title: qsTr("No shows yet")
                hint: qsTr("Find one above, follow a show by its feed link, add a folder of episodes, or import the list from another podcast app (OPML).")
                actionText: qsTr("Follow by link")
                onAction: followDlg.open()
            }
        }
    }
}
