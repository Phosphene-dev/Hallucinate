import QtQuick
import QtQuick.Controls
import "."

// One show: its cover, notes and settings, then every episode, newest first.
Item {
    id: page
    objectName: "podcast"
    property int podcastId: 0
    property var info: ({})
    readonly property var coverColors: themeManager.imagePalette(info.artUrl || "")
    function refreshInfo() { info = podcasts.show(podcastId) }
    Component.onCompleted: { podcasts.openShow(podcastId); refreshInfo() }
    Connections {
        target: podcasts
        function onChanged() { page.refreshInfo() }
        function onMessage(text) { Nav.notify(text) }
    }
    EpisodeMenu { id: episodeMenu }
    Dialog {
        id: showSettings
        objectName: "showSettings"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(560, (parent ? parent.width : 560) - 40)
        modal: true
        title: "Settings for " + (page.info.title || "this show")
        standardButtons: Dialog.Close
        readonly property var secs: [0, 15, 30, 45, 60, 90, 120]
        function secLabels(none) { return secs.map(function (n) { return n ? n + " seconds" : none }) }
        Column {
            width: showSettings.availableWidth
            spacing: 12
            OptionCombo {
                label: "Episodes"
                values: [1, 0]; labels: ["Newest first", "Oldest first"]
                current: page.info.newest_first === undefined ? 1 : page.info.newest_first
                onPicked: function (v) { podcasts.setShowOption(page.podcastId, "newest_first", v) }
            }
            StyledCheck {
                text: "Hide episodes I've played"
                checked: !!page.info.hide_played
                onToggled: podcasts.setShowOption(page.podcastId, "hide_played", checked ? 1 : 0)
            }
            OptionCombo {
                label: "Speed"
                values: [0, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3]
                labels: ["Your podcast speed (" + player.podcastSpeed + "×)", "0.75×", "1×", "1.25×", "1.5×", "1.75×", "2×", "2.5×", "3×"]
                current: page.info.speed || 0
                onPicked: function (v) { podcasts.setShowOption(page.podcastId, "speed", v) }
            }
            OptionCombo {
                label: "Skip the intro"
                values: showSettings.secs; labels: showSettings.secLabels("Don't skip")
                current: page.info.skip_intro || 0
                onPicked: function (v) { podcasts.setShowOption(page.podcastId, "skip_intro", v) }
            }
            OptionCombo {
                label: "Skip the outro"
                values: showSettings.secs; labels: showSettings.secLabels("Don't skip")
                current: page.info.skip_outro || 0
                onPicked: function (v) { podcasts.setShowOption(page.podcastId, "skip_outro", v) }
            }
            OptionCombo {
                visible: !page.info.folder
                label: "Download by itself"
                values: [0, 1, 2, 3, 5]; labels: ["Nothing", "The newest episode", "The newest 2", "The newest 3", "The newest 5"]
                current: page.info.auto_download || 0
                onPicked: function (v) { podcasts.setShowOption(page.podcastId, "auto_download", v) }
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Skipping the intro starts episodes you haven't begun after it; skipping the outro moves on (and marks the episode played) that long before the end."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
    }
    ConfirmDialog {
        id: unfollowDlg
        title: "Unfollow this show?"
        body: "“" + (page.info.title || "") + "” and where you were in its episodes go away"
              + (page.info.folder ? ". The files in its folder stay where they are." : ", along with its downloads.")
        confirmText: "Unfollow"
        destructive: true
        onAccepted: { var id = page.podcastId; podcasts.unfollow(id, true); Nav.back(); Nav.routeGone("podcast", id) }
    }

    ListView {
        id: list
        objectName: "episodeList"
        anchors.fill: parent
        anchors.leftMargin: 20; anchors.rightMargin: 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: podcasts.episodes
        spacing: 2
        ScrollBar.vertical: ScrollBar {}

        header: Item {
            width: list.width
            height: headerColumn.height
            // the show's own colours, glowing behind its cover
            Bloom { tint: page.coverColors.length ? page.coverColors[0] : Theme.accent; size: 560; x: -140; y: -200 }
            Bloom { tint: page.coverColors.length > 1 ? page.coverColors[1] : Theme.art1; size: 420; x: list.width * 0.45; y: -180 }
                Column {
                id: headerColumn
                width: list.width
                spacing: 14
                topPadding: 20
                bottomPadding: 14
                Row {
                    width: parent.width - 16
                    x: 8
                    spacing: 20
                    Cover {
                        id: art
                        width: Math.min(180, list.width * 0.28); height: width; radius: 18
                        source: page.info.artUrl || ""
                        fallback: (page.info.title || "?").charAt(0)
                    }
                    Column {
                        width: parent.width - art.width - 20
                        anchors.verticalCenter: art.verticalCenter
                        spacing: 8
                        Text { textFormat: Text.PlainText; text: page.info.folder ? "PODCAST · FOLDER" : "PODCAST"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold }
                        Text {
                            textFormat: Text.PlainText
                            width: parent.width
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            text: page.info.title || ""
                            color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(28); font.weight: Font.Bold
                        }
                        Text { textFormat: Text.PlainText; visible: text.length > 0; text: page.info.author || ""; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14) }
                        Text {
                            textFormat: Text.PlainText
                            visible: (page.info.error || "").length > 0
                            width: parent.width
                            wrapMode: Text.WordWrap
                            text: "Couldn't check the feed: " + (page.info.error || "")
                            color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                        }
                        Flow {
                            width: parent.width
                            spacing: 10
                            PillButton {
                                objectName: "playLatest"
                                primary: true
                                text: "Play latest"
                                enabled: list.count > 0
                                onClicked: podcasts.playLatest(page.podcastId)
                            }
                            PillButton { text: "Check for new"; enabled: !podcasts.busy; onClicked: podcasts.refresh(page.podcastId) }
                            PillButton { text: "Mark all played"; enabled: (page.info.unplayed || 0) > 0; onClicked: podcasts.markAllPlayed(page.podcastId) }
                            PillButton {
                                objectName: "downloadUnplayed"
                                text: "Download all unplayed"
                                visible: !(page.info.folder || "").length  // a folder's episodes are on disk already
                                enabled: (page.info.unplayed || 0) > 0
                                onClicked: podcasts.downloadUnplayed(page.podcastId)
                            }
                            PillButton { objectName: "showSettingsButton"; text: "Show settings"; onClicked: showSettings.open() }
                        PillButton { text: "Unfollow"; onClicked: unfollowDlg.open() }
                        }
                    }
                }
                Text {
                    textFormat: Text.PlainText
                    x: 8
                    width: parent.width - 16
                    visible: text.length > 0
                    wrapMode: Text.WordWrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                    text: page.info.description || ""
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                    lineHeight: 1.15
                }
                TextField {
                    id: episodeSearch
                    objectName: "episodeSearch"
                    x: 8
                    width: Math.min(420, parent.width - 16)
                    height: 38
                    visible: (page.info.episodes || 0) > 8 || text.length > 0
                    placeholderText: "Find an episode"
                    selectByMouse: true
                    Accessible.name: "Find an episode"
                    onTextChanged: podcasts.setEpisodeFilter(text)
                    Keys.onEscapePressed: text = ""
                }
            }
        }

        delegate: EpisodeRow {
            required property var model
            width: list.width - 8
            episode: model
            onMenu: episodeMenu.showFor(model, false)
        }

        footer: Item {
            width: list.width
            height: list.count === 0 ? 160 : 40
            EmptyState {
                anchors.centerIn: parent
                visible: list.count === 0
                icon: "podcast"
                busy: podcasts.busy
                title: podcasts.busy ? "Checking for episodes…" : "No episodes"
                hint: page.info.folder ? "No audio files in this folder." : "The feed has no episodes with audio."
            }
        }
    }
}
