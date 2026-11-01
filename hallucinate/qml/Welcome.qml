import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// First run: where your music is, how the app should look, what's switched on (and what may go online), and
// whether to scrobble. Opens over everything
// until it is finished or skipped; every choice can be changed later in Settings. While open it has the keyboard:
// Tab goes through its own buttons and fields, and the window's shortcuts stand aside (main.qml).
FocusScope {
    id: welcome
    objectName: "welcome"
    property int step: 0
    readonly property int steps: 4
    property bool open: shell.uiValue("welcome", "0") === "1"
    property bool triedListenBrainz: false
    signal finished()
    visible: opacity > 0
    opacity: open ? 1 : 0
    enabled: open
    Behavior on opacity { NumberAnimation { duration: 420; easing.type: Easing.InOutCubic } }
    onOpenChanged: if (open) Qt.callLater(function () { if (welcome.open) nextButton.forceActiveFocus() })
    Component.onCompleted: if (open) Qt.callLater(function () { if (welcome.open) nextButton.forceActiveFocus() })

    function finish() {
        shell.setUiValue("welcome", "0")
        open = false
        finished()
    }

    // keep clicks, wheel and keys from reaching the app underneath
    MouseArea { anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.AllButtons; onWheel: function (w) { w.accepted = true } }
    Ambience { anchors.fill: parent; animated: welcome.open && shell.ambientMotion && !shell.reduceMotion }

    component Heading: Text {
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: (Theme.fontSize(24)) * Theme.displayScale
        font.weight: Font.DemiBold
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    component Body: Text {
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(14)
        lineHeight: 1.15
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    component Field: TextField {
        implicitHeight: 38
        color: Theme.text
        placeholderTextColor: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(14)
        leftPadding: 14
        background: Rectangle { radius: Theme.round(height / 2); color: Theme.surface; border.color: parent.activeFocus ? Theme.accent : Theme.border }
    }

    GlassPanel {
        id: card
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 660)
        height: Math.min(parent.height - 48, 560)
        color: Theme.glassStrong

        ColumnLayout {
            anchors { fill: parent; margins: 32 }
            spacing: 18

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Image {
                    source: "../assets/hallucinate.png"
                    sourceSize: Qt.size(64, 64)
                    Layout.preferredWidth: 32
                    Layout.preferredHeight: 32
                    smooth: true
                }
                Text {
                    textFormat: Text.PlainText
                    text: qsTr("Hallucinate")
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: (Theme.fontSize(17)) * Theme.displayScale
                    font.weight: Font.DemiBold
                }
                Item { Layout.fillWidth: true }
                Row {
                    objectName: "welcomeDots"
                    spacing: 8
                    Repeater {
                        model: welcome.steps
                        Rectangle {
                            required property int index
                            width: index === welcome.step ? 22 : 8; height: 8; radius: 4
                            color: index <= welcome.step ? Theme.accent : Theme.border
                            Behavior on width { NumberAnimation { duration: 200 } }
                        }
                    }
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: welcome.step

                // 1. Your music
                ColumnLayout {
                    spacing: 14
                    Heading { text: qsTr("Where's your music?") }
                    Body {
                        text: qsTr("Choose the folders that hold your music. Hallucinate reads them without changing a thing, and keeps an eye out for new songs.")
                    }
                    ListView {
                        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
                        objectName: "welcomeFolders"
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(contentHeight, 150)
                        clip: true
                        spacing: 6
                        model: library.folders
                        delegate: Rectangle {
                            required property var modelData
                            width: ListView.view.width; height: 44; radius: Theme.radius
                            color: Theme.surface
                            Icon {
                                id: folderIcon
                                anchors { left: parent.left; leftMargin: 14; verticalCenter: parent.verticalCenter }
                                name: "folder"; width: 16; height: 16; color: Theme.accent
                            }
                            Text {
                                textFormat: Text.PlainText
                                anchors { left: folderIcon.right; leftMargin: 10; right: rm.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                                text: modelData
                                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                                elide: Text.ElideMiddle
                            }
                            IconButton {
                                id: rm
                                anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                                icon: "close"; size: 13; tip: qsTr("Remove")
                                onClicked: library.removeFolder(modelData)
                            }
                        }
                    }
                    RowLayout {
                        spacing: 10
                        PillButton {
                            objectName: "welcomeChooseFolder"
                            primary: library.folders.length === 0
                            text: library.folders.length ? qsTr("Add another folder…") : qsTr("Choose folder…")
                            onClicked: picker.open()
                        }
                        FolderPicker { id: picker }
                    }
                    Text {
                        textFormat: Text.PlainText
                        objectName: "welcomeFound"
                        Layout.fillWidth: true
                        visible: !library.scanning && library.folders.length > 0
                        text: library.trackCount > 0
                              ? Theme.counted(qsTr("%n song(s) found", "", library.trackCount), library.trackCount)
                              : library.missingFolders.length > 0 ? qsTr("Can't read %1").arg(library.missingFolders.join(", "))
                              : qsTr("No songs found there yet")
                        color: library.trackCount > 0 ? Theme.accent : Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(13)
                        font.weight: Font.DemiBold
                    }
                    ScanBar { Layout.fillWidth: true }
                    Item { Layout.fillHeight: true }
                }

                // 2. A look
                ColumnLayout {
                    spacing: 14
                    Heading { text: qsTr("Pick a look") }
                    Body { text: qsTr("Themes change the whole app as you click. There are more options in Settings.") }
                    Flickable {
                        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
                        id: themeScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentHeight: themeGrid.implicitHeight
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: themeScroll.contentHeight > themeScroll.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
                        GridLayout {
                            id: themeGrid
                            objectName: "welcomeThemes"
                            width: themeScroll.width - 12
                            columns: 3
                            rowSpacing: 10
                            columnSpacing: 10
                            Repeater {
                                model: themeManager.availableThemes
                                Rectangle {
                                    id: swatch
                                    required property string modelData
                                    readonly property var c: themeManager.themeColors(modelData)
                                    readonly property bool current: themeManager.currentTheme === modelData
                                    readonly property var flag: themeManager.paletteOf(modelData)
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 58
                                    radius: Theme.radius
                                    color: c.bg || Theme.bg
                                    border.width: current ? 2 : 1
                                    border.color: current ? Theme.accent : (themeHover.hovered ? Theme.textDim : Theme.border)
                                    Rectangle {
                                        id: chip
                                        x: 12; anchors.verticalCenter: parent.verticalCenter
                                        width: 26; height: 26; radius: Theme.round(13)
                                        color: swatch.c.accent || Theme.accent
                                    }
                                    Column {
                                        anchors { left: chip.right; leftMargin: 10; right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                                        spacing: 5
                                        Text {
                                            textFormat: Text.PlainText
                                            width: parent.width
                                            text: swatch.modelData
                                            elide: Text.ElideRight
                                            color: swatch.c.text || Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.fontSize(13)
                                            font.weight: Font.DemiBold
                                        }
                                        FlagStripe { colors: swatch.flag; width: 52 }
                                        Row {
                                            visible: swatch.flag.length === 0
                                            spacing: 4
                                            Rectangle { width: 30; height: 5; radius: 2.5; color: swatch.c.surface || Theme.surface }
                                            Rectangle { width: 18; height: 5; radius: 2.5; color: swatch.c.textDim || Theme.textDim; opacity: 0.6 }
                                        }
                                    }
                                    HoverHandler { id: themeHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: themeManager.selectTheme(swatch.modelData) }
                                }
                            }
                        }
                    }
                    StyledCheck {
                        text: qsTr("Tint the accent with each album's cover")
                        checked: themeManager.albumArtAccent
                        onToggled: themeManager.setAlbumArtAccent(checked)
                    }
                }

                // 3. What's on, and what may go online
                Flickable {
                    WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
                    id: choices
                    objectName: "welcomeChoices"
                    clip: true
                    contentHeight: choiceCol.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: choices.contentHeight > choices.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
                    component Group: Text {
                        textFormat: Text.PlainText
                        topPadding: 6
                        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold
                    }
                    component Feature: StyledCheck {
                        property string name
                        objectName: "welcome_" + name
                        width: Math.max(200, implicitWidth + 12)
                        checked: shell.features[name] === true
                        onToggled: shell.setFeature(name, checked)
                    }
                    ColumnLayout {
                        id: choiceCol
                        width: choices.width - 12
                        spacing: 8
                        Heading { text: qsTr("What would you like?") }
                        Body {
                            text: qsTr("Switch on what you'll use. Nothing here goes online unless you tick it, and it can all be changed later in Settings → Features and Settings → Internet & sharing.")
                        }
                        Group { text: qsTr("Features") }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 4
                            Feature { name: "stations"; text: qsTr("Internet radio") }
                            Feature { name: "podcasts"; text: qsTr("Podcasts") }
                            Feature { name: "servers"; text: qsTr("Music servers (Jellyfin, Navidrome, Subsonic)") }
                            Feature { name: "lyrics"; text: qsTr("Lyrics") }
                            Feature { name: "visualizer"; text: qsTr("Visualizer") }
                            Feature { name: "liked"; text: qsTr("Liked Songs") }
                            Feature { name: "folders"; text: qsTr("Folders") }
                            Feature { name: "stats"; text: qsTr("Stats") }
                            Feature { name: "history"; text: qsTr("History") }
                            Feature { name: "recap"; text: qsTr("Recap") }
                            Feature { name: "health"; text: qsTr("Library health") }
                        }
                        Group { text: qsTr("Going online") }
                        StyledCheck {
                            objectName: "welcomeLyricsOnline"
                            visible: shell.features.lyrics !== false
                            text: qsTr("Find lyrics online for songs that have none (asks LRCLIB with the song's artist and title)")
                            checked: lyricsCtl.onlineLookup
                            onToggled: lyricsCtl.setOnlineLookup(checked)
                        }
                        StyledCheck {
                            objectName: "welcomeBios"
                            text: qsTr("Look up an artist's bio when their page opens (asks Wikipedia through MusicBrainz)")
                            checked: sources.fetchBios
                            onToggled: sources.setFetchBios(checked)
                        }
                        StyledCheck {
                            objectName: "welcomeUpdates"
                            visible: shell.updates.supported
                            text: qsTr("Tell me when a new version is out (checks GitHub once a day)")
                            checked: shell.updates.enabled
                            onToggled: shell.updates.setEnabled(checked)
                        }
                        StyledCheck {
                            objectName: "welcomeOffline"
                            text: qsTr("Offline mode: never go online at all (overrides everything above, and radio, podcasts, servers and scrobbling)")
                            checked: shell.offlineMode
                            onToggled: shell.setOfflineMode(checked)
                        }
                        Body {
                            text: qsTr("Covers, tags and genres are only looked up when you ask. Radio, podcasts and music servers only connect to the stations, feeds and servers you add.")
                        }
                    }
                }

                // 4. Scrobbling
                ColumnLayout {
                    spacing: 12
                    Heading { text: qsTr("Keep a record of what you play?") }
                    Body {
                        text: qsTr("Hallucinate keeps your listening history on this computer either way. Scrobbling also sends it to ListenBrainz or Last.fm. It's optional, and you can set it up later in Settings.")
                    }
                    Text {
                        textFormat: Text.PlainText
                        text: qsTr("ListenBrainz")
                        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        visible: !listenbrainz.connected
                        Field {
                            id: lbToken
                            objectName: "welcomeLbToken"
                            Layout.fillWidth: true
                            placeholderText: qsTr("Your user token")
                            echoMode: TextInput.Password
                            onAccepted: lbConnect.clicked()
                        }
                        PillButton {
                            id: lbConnect
                            primary: true
                            text: listenbrainz.busy ? qsTr("Checking…") : qsTr("Connect")
                            enabled: lbToken.text.length > 0 && !listenbrainz.busy
                            onClicked: {
                                welcome.triedListenBrainz = true
                                listenbrainz.connectToken(lbToken.text, "")
                                lbToken.text = ""
                            }
                        }
                        PillButton { text: qsTr("Get a token"); onClicked: Qt.openUrlExternally("https://listenbrainz.org/settings/") }
                    }
                    Body {
                        visible: (listenbrainz.connected || welcome.triedListenBrainz) && listenbrainz.status.length > 0
                        text: listenbrainz.status
                        color: listenbrainz.connected ? Theme.accent : Theme.textDim
                    }
                    Text {
                        textFormat: Text.PlainText
                        Layout.topMargin: 6
                        text: qsTr("Last.fm")
                        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold
                    }
                    RowLayout {
                        spacing: 10
                        visible: scrobbler.configured && !scrobbler.connected
                        PillButton {
                            primary: scrobbler.authorizationUrl.length === 0
                            text: scrobbler.busy ? qsTr("Connecting…") : qsTr("Connect Last.fm")
                            enabled: !scrobbler.busy
                            onClicked: scrobbler.connectAccount()
                        }
                        PillButton {
                            visible: scrobbler.authorizationUrl.length > 0
                            text: qsTr("Open Last.fm again")
                            onClicked: scrobbler.openAuthorizationUrl()
                        }
                        PillButton {
                            visible: scrobbler.authorizationUrl.length > 0
                            primary: true
                            text: qsTr("I've allowed access")
                            enabled: !scrobbler.busy
                            onClicked: scrobbler.completeAuthorization()
                        }
                    }
                    Body {
                        text: scrobbler.connected ? scrobbler.status
                            : scrobbler.configured ? scrobbler.status
                            : qsTr("Last.fm asks each app user for an API key of their own. Add yours in Settings → Internet & sharing whenever you like.")
                        color: scrobbler.connected ? Theme.accent : Theme.textDim
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Text {
                    id: skipLink
                    textFormat: Text.PlainText
                    objectName: "welcomeSkip"
                    text: qsTr("Skip setup")
                    color: skipMouse.containsMouse || activeFocus ? Theme.text : Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(13)
                    font.underline: activeFocus
                    // a link that Tab reaches too: Enter or Space skips
                    activeFocusOnTab: true
                    Keys.onShortcutOverride: function (event) { event.accepted = event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter }
                    Keys.onSpacePressed: welcome.finish()
                    Keys.onReturnPressed: welcome.finish()
                    Keys.onEnterPressed: welcome.finish()
                    Accessible.role: Accessible.Button
                    Accessible.name: qsTr("Skip setup")
                    Accessible.description: qsTr("Close the welcome; everything can be set later in Settings")
                    Accessible.onPressAction: welcome.finish()
                    Rectangle {
                        anchors { fill: parent; margins: -4 }
                        radius: Theme.round(6); color: "transparent"; border.width: 2; border.color: Theme.accent
                        visible: skipLink.activeFocus
                    }
                    LinkArea { id: skipMouse; name: "Skip setup"; hoverEnabled: true; onClicked: welcome.finish() }
                }
                Item { Layout.fillWidth: true }
                PillButton {
                    visible: welcome.step > 0
                    text: qsTr("Back")
                    onClicked: welcome.step--
                }
                PillButton {
                    id: nextButton
                    objectName: "welcomeNext"
                    primary: true
                    text: welcome.step < welcome.steps - 1 ? qsTr("Next") : qsTr("Start listening")
                    onClicked: welcome.step < welcome.steps - 1 ? welcome.step++ : welcome.finish()
                }
            }
        }
    }
}
