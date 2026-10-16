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
    ConfirmDialog {
        id: unfollowDlg
        title: "Unfollow this show?"
        body: "“" + (page.info.title || "") + "” and where you were in its episodes go away"
              + (page.info.folder ? ". The files in its folder stay where they are." : ", along with its downloads.")
        confirmText: "Unfollow"
        destructive: true
        onAccepted: { podcasts.unfollow(page.podcastId, true); Nav.back() }
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
                            PillButton { text: "Unfollow"; onClicked: unfollowDlg.open() }
                        }
                        StyledCheck {
                            visible: !page.info.folder
                            text: "Download new episodes by themselves"
                            checked: !!page.info.auto_download
                            onToggled: podcasts.setAutoDownload(page.podcastId, checked)
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
