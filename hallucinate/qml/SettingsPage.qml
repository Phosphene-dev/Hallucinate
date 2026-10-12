import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "."

Item {
    id: page
    objectName: "settings"
    property string query: ""
    readonly property var sectionIds: ["appearance", "playback", "sound", "library", "sharing", "desktop", "about"]
    readonly property var sectionTitles: ["Appearance", "Playback", "Sound", "Library", "Internet & sharing", "Desktop", "About"]

    function sectionItem(i) { return [sec_appearance, sec_playback, sec_sound, sec_library, sec_sharing, sec_desktop, sec_about][i] }
    function jumpTo(i) {
        page.query = ""
        search.text = ""
        flick.contentY = Math.max(0, Math.min(sectionItem(i).y, flick.contentHeight - flick.height))
    }

    // Search and jump to a section; the page below scrolls
    Column {
        id: header
        x: 28; y: 20
        width: page.width - 56
        spacing: 12
        Row {
            width: parent.width
            spacing: 16
            Text { id: pageTitle; text: "Settings"; color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(25); font.weight: Font.Bold }
            TextField {
                id: search
                objectName: "settingsSearch"
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(340, parent.width - pageTitle.width - 16)
                height: 36
                placeholderText: "Search settings"
                color: Theme.text
                placeholderTextColor: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(14)
                leftPadding: 14
                selectByMouse: true
                background: Rectangle { radius: height / 2; color: Theme.surface; border.color: search.activeFocus ? Theme.accent : Theme.border }
                onTextChanged: { page.query = text; flick.contentY = 0 }
                Keys.onEscapePressed: text = ""
            }
        }
        Flow {
            width: parent.width
            spacing: 8
            visible: page.query.length === 0
            Repeater {
                model: page.sectionTitles
                Chip {
                    required property string modelData
                    required property int index
                    text: modelData
                    onClicked: page.jumpTo(index)
                }
            }
        }
        Text {
            visible: page.query.length > 0
            text: noMatches ? "No settings match “" + page.query + "”" : "Showing settings that match “" + page.query + "”"
            readonly property bool noMatches: !(sec_appearance.matches || sec_playback.matches || sec_sound.matches || sec_library.matches || sec_sharing.matches || sec_desktop.matches || sec_about.matches)
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
        }
    }

    Flickable {
        id: flick
        anchors { left: parent.left; right: parent.right; top: header.bottom; topMargin: 14; bottom: parent.bottom }
        contentWidth: width
        contentHeight: settingsColumn.implicitHeight + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

    Column {
        id: settingsColumn
        x: 28
        width: page.width - 56
        spacing: 18

        SettingsSection {
            id: sec_appearance
            objectName: "settings_appearance"
            title: "Appearance"
            keywords: "theme colours font accent album art ambient motion visualizer vinyl dark light pride"
            query: page.query
            StyledCheck {
                text: "Show audio format and average bitrate on tracks"
                checked: player.showTrackInfo
                onToggled: player.setShowTrackInfo(checked)
                Accessible.name: "Show track audio format and average bitrate"
            }
            Text {
                text: "Shows compact format and approximate average bitrate badges in song rows and the now-playing bar."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                wrapMode: Text.WordWrap
            }
            Row {
                spacing: 12
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Theme"
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(14)
                }
                ComboBox {
                    id: themePicker
                    objectName: "themePicker"
                    width: 260
                    model: themeManager.availableThemes
                    currentIndex: Math.max(0, themeManager.availableThemes.indexOf(themeManager.currentTheme))
                    onActivated: themeManager.selectTheme(currentText)
                    contentItem: Text {
                        objectName: "themePickerText"
                        leftPadding: 12
                        rightPadding: 28
                        text: themePicker.displayText
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(14)
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    background: Rectangle {
                        implicitHeight: 38
                        radius: Theme.radius
                        color: Theme.surface
                        border.color: themePicker.activeFocus ? Theme.accent : Theme.border
                    }
                }
            }
            StyledCheck {
                objectName: "ambientMotion"
                text: "Animated background (slowly drifting colours from the current cover)"
                checked: shell.ambientMotion
                onToggled: shell.setAmbientMotion(checked)
            }
            CheckBox {
                id: albumAccentToggle
                text: "Use album-art accent color"
                checked: themeManager.albumArtAccent
                onToggled: themeManager.setAlbumArtAccent(checked)
                contentItem: Text {
                    text: albumAccentToggle.text
                    leftPadding: 30
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(14)
                    verticalAlignment: Text.AlignVCenter
                }
                indicator: Rectangle {
                    implicitWidth: 20
                    implicitHeight: 20
                    radius: Theme.radius / 2
                    x: albumAccentToggle.leftPadding
                    y: parent.height / 2 - height / 2
                    color: albumAccentToggle.checked ? Theme.accent : Theme.surface
                    border.color: albumAccentToggle.checked ? Theme.accent : Theme.border
                    Text {
                        anchors.centerIn: parent
                        text: albumAccentToggle.checked ? "✓" : ""
                        color: Theme.onAccent
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(13)
                    }
                }
            }
            Text {
                text: "Custom themes: " + themeManager.userThemeDirectory + "/*.json"
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(12)
            }
            PillButton {
                text: "Reload themes"
                onClicked: themeManager.reloadThemes()
            }

        }
        SettingsSection {
            id: sec_playback
            objectName: "settings_playback"
            title: "Playback"
            keywords: "output device audio replaygain loudness crossfade gapless speed sleep"
            query: page.query
            Row {
                spacing: 12
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Output device"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14) }
                StyledCombo {
                    id: deviceCombo
                    objectName: "outputDevice"
                    width: 360
                    model: player.outputDevices
                    textRole: "name"
                    currentIndex: player.outputDevices.findIndex(d => d.key === player.outputDevice)
                    onActivated: player.setOutputDevice(player.outputDevices[currentIndex].key)
                    // Activating breaks the binding above; re-sync when devices come and go.
                    Connections {
                        target: player
                        function onOutputDevicesChanged() {
                            deviceCombo.currentIndex = player.outputDevices.findIndex(d => d.key === player.outputDevice)
                        }
                    }
                }
            }
            Row {
                spacing: 12
                Text { anchors.verticalCenter: parent.verticalCenter; text: "ReplayGain"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14) }
                StyledCombo {
                    objectName: "rgMode"
                    model: ["Off", "Track", "Album"]
                    currentIndex: ["off", "track", "album"].indexOf(player.replayGainMode)
                    onActivated: player.setReplayGainMode(["off", "track", "album"][currentIndex])
                }
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Preamp " + player.replayGainPreamp.toFixed(1) + " dB"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14) }
                StyledSlider {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 140
                    from: -15; to: 15; stepSize: 0.5
                    value: player.replayGainPreamp
                    onMoved: player.setReplayGainPreamp(value)
                }
            }
            Row {
                spacing: 12
                PillButton {
                    objectName: "analyseReplayGain"
                    text: replayGain.busy ? "Stop measuring" : "Measure songs without ReplayGain"
                    onClicked: replayGain.busy ? replayGain.cancel() : replayGain.analyseMissing()
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: replayGain.busy ? "Measured " + replayGain.done + " of " + replayGain.total + " songs…"
                        : "Measures loudness (EBU R128) for songs whose files have no ReplayGain tags. Files aren't changed."
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(12)
                }
            }
            Row {
                spacing: 12
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Crossfade " + (player.crossfade > 0 ? player.crossfade + " s" : "off"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14) }
                StyledSlider {
                    objectName: "crossfade"
                    anchors.verticalCenter: parent.verticalCenter
                    width: 200
                    from: 0; to: 12; stepSize: 1
                    value: player.crossfade
                    onMoved: player.setCrossfade(value)
                }
            }
            Text { text: "Gapless playback is always on; with crossfade off, consecutive tracks play back to back."; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12) }
        }
        SettingsSection {
            id: sec_sound
            objectName: "settings_sound"
            title: "Sound"
            keywords: "equalizer eq bass treble headphones autoeq crossfeed"
            query: page.query
            EqualizerPanel {}
            Row {
                spacing: 12
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Headphone crossfeed"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14) }
                StyledCombo {
                    objectName: "crossfeed"
                    enabled: player.eqAvailable
                    model: ["Off", "Light", "Medium", "Strong"]
                    currentIndex: Math.max(0, player.crossfeedPresets.indexOf(player.crossfeed))
                    onActivated: player.setCrossfeed(player.crossfeedPresets[currentIndex])
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Lets each ear hear a little of the other channel, as from speakers. Old stereo recordings with "
                    + "instruments hard left or right get much easier on the ears over headphones."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }

        }
        SettingsSection {
            id: sec_library
            objectName: "settings_library"
            title: "Library"
            keywords: "music folders scan rescan health import strawberry clementine rhythmbox musicbee itunes foobar playlists"
            query: page.query
            Text {
                text: "Folders are scanned in the background and watched for changes."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }

            Repeater {
                model: library.folders
                Rectangle {
                    required property var modelData
                    width: parent.width; height: 48; radius: Theme.radius
                    color: Theme.surface
                    Text {
                        anchors { left: parent.left; leftMargin: 16; right: rm.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                        text: modelData
                        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); elide: Text.ElideMiddle
                    }
                    IconButton {
                        id: rm
                        anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                        icon: "close"; size: 14
                        onClicked: library.removeFolder(modelData)
                    }
                }
            }

            Row {
                spacing: 10
                TextField {
                    id: pathField
                    width: 420; height: 38
                    placeholderText: "/path/to/music"
                    color: Theme.text
                    placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSize(14)
                    leftPadding: 14
                    background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: pathField.activeFocus ? Theme.accent : Theme.border }
                    onAccepted: add.clicked()
                }
                PillButton {
                    id: add
                    primary: true
                    text: "Add folder"
                    onClicked: { library.addFolder(pathField.text); pathField.text = "" }
                }
                PillButton { text: "Rescan now"; onClicked: library.rescan() }
                PillButton { objectName: "openHealth"; text: "Library health"; onClicked: Nav.openHealth() }
            }
            ScanBar { width: parent.width }
            Text {
                visible: !library.scanning && library.status.length > 0
                text: library.status
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Text {
                width: parent.width
                visible: library.missingFolders.length > 0
                wrapMode: Text.WordWrap
                text: "Folder not found or unreadable: " + library.missingFolders.join(", ")
                color: Theme.error; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Text {
                visible: library.unreadableFiles > 0 && !library.scanning
                text: library.unreadableFiles + " files could not be read and were skipped."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            PillButton { text: "Choose folder…"; onClicked: picker.open() }
            FolderPicker { id: picker }

            Rectangle { width: parent.width; height: 1; color: Theme.border }
            Rectangle { width: parent.width; height: 1; color: Theme.border }
            Text { text: "From another player"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Bring over play counts, skips, ratings and playlists from Strawberry, Clementine, Rhythmbox, MusicBee "
                    + "or iTunes. Songs are matched to your library; importing again never counts anything twice, and "
                    + "ratings you set here are kept."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Flow {
                width: parent.width
                spacing: 10
                Repeater {
                    id: foundPlayers
                    model: userLib.otherPlayerLibraries()
                    PillButton {
                        required property var modelData
                        text: "Import from " + modelData.name
                        enabled: !userLib.playerImportBusy
                        onClicked: userLib.importFromPlayer(modelData.path)
                    }
                }
                PillButton {
                    objectName: "importPlayerFile"
                    text: foundPlayers.count ? "Choose another library file…" : "Choose a library file…"
                    enabled: !userLib.playerImportBusy
                    onClicked: playerFile.open()
                }
                PillButton {
                    text: userLib.playerImportBusy ? "Importing…" : "foobar2000: play counts from tags"
                    enabled: !userLib.playerImportBusy
                    onClicked: userLib.importTagStatistics()
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "MusicBee: turn on Preferences → Library → “make library and playlists accessible to other "
                    + "applications”, then choose its iTunes Music Library.xml. foobar2000 keeps its statistics to "
                    + "itself, so write them to the files with foo_playcount first; its playlists come over as M3U files."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            FileDialog {
                id: playerFile
                title: "Choose another player's library"
                nameFilters: ["Player libraries (*.db *.xml)", "All files (*)"]
                onAccepted: userLib.importFromPlayer(selectedFile.toString())
            }
        }
        SettingsSection {
            id: sec_sharing
            objectName: "settings_sharing"
            title: "Internet & sharing"
            keywords: "offline mode internet network privacy connection last.fm lastfm listenbrainz scrobble discord rich presence history import account"
            query: page.query
            Text { text: "Offline mode"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Hallucinate makes no internet connections at all: no lyrics or cover lookups, scrobbling, headphone EQ downloads or update checks. Scrobbles wait and are sent when you turn it off. Discord status talks only to the Discord app on this computer, so it keeps its own switch below (it shows no cover art while offline)."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            StyledCheck {
                objectName: "offlineMode"
                text: "Offline mode"
                checked: shell.offlineMode
                onToggled: shell.setOfflineMode(checked)
            }
            Text { text: "Last.fm"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Connect your Last.fm account to send now-playing updates and scrobbles after listening to half a track or four minutes, whichever comes first. API credentials are stored in the system keyring."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Register an API application, then enter its key and secret. Last.fm account authorization opens in your browser."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Row {
                spacing: 10
                TextField {
                    id: apiKey
                    width: 250; height: 38
                    placeholderText: "Last.fm API key"
                    color: Theme.text; placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                    background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: apiKey.activeFocus ? Theme.accent : Theme.border }
                }
                TextField {
                    id: apiSecret
                    width: 250; height: 38
                    placeholderText: "Last.fm API secret"
                    echoMode: TextInput.Password
                    color: Theme.text; placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                    background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: apiSecret.activeFocus ? Theme.accent : Theme.border }
                }
                PillButton {
                    text: "Save API credentials"
                    primary: true
                    enabled: apiKey.text.length > 0 && apiSecret.text.length > 0 && !scrobbler.busy
                    onClicked: {
                        scrobbler.setApiCredentials(apiKey.text, apiSecret.text)
                        apiSecret.text = ""
                    }
                }
            }
            Row {
                spacing: 10
                PillButton {
                    text: "Get API credentials"
                    onClicked: Qt.openUrlExternally("https://www.last.fm/api/account/create")
                }
                PillButton {
                    visible: !scrobbler.connected
                    primary: true
                    text: scrobbler.busy ? "Connecting…" : "Connect Last.fm"
                    enabled: scrobbler.configured && !scrobbler.busy && !shell.offlineMode
                    onClicked: scrobbler.connectAccount()
                }
                PillButton {
                    visible: scrobbler.authorizationUrl.length > 0 && !scrobbler.connected
                    text: "Open authorization"
                    onClicked: scrobbler.openAuthorizationUrl()
                }
                PillButton {
                    visible: scrobbler.authorizationUrl.length > 0 && !scrobbler.connected
                    primary: true
                    text: "I've authorized"
                    enabled: !scrobbler.busy
                    onClicked: scrobbler.completeAuthorization()
                }
                PillButton {
                    visible: scrobbler.connected
                    text: "Disconnect Last.fm"
                    enabled: !scrobbler.busy
                    onClicked: scrobbler.disconnectAccount()
                }
            }
            Text {
                width: parent.width
                text: scrobbler.status + (scrobbler.pendingCount > 0 ? " · " + scrobbler.pendingCount + " queued scrobbles" : "")
                color: scrobbler.connected ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
                wrapMode: Text.WordWrap
            }
            Text { text: "ListenBrainz"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Connect with a ListenBrainz user token to send now-playing updates and listens. Tokens stay in the system keyring; failed submissions remain queued for retry."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Row {
                spacing: 10
                TextField {
                    id: lbToken
                    width: 320; height: 38
                    visible: !listenbrainz.connected
                    placeholderText: "ListenBrainz user token"
                    echoMode: TextInput.Password
                    color: Theme.text; placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                    background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: lbToken.activeFocus ? Theme.accent : Theme.border }
                }
                PillButton {
                    visible: !listenbrainz.connected
                    primary: true
                    text: listenbrainz.busy ? "Validating…" : "Connect ListenBrainz"
                    enabled: lbToken.text.length > 0 && !listenbrainz.busy
                    onClicked: { listenbrainz.connectToken(lbToken.text, ""); lbToken.text = "" }
                }
                PillButton {
                    visible: listenbrainz.connected
                    text: "Disconnect ListenBrainz"
                    enabled: !listenbrainz.busy
                    onClicked: listenbrainz.disconnectAccount()
                }
            }
            Text {
                width: parent.width
                text: listenbrainz.status + (listenbrainz.pendingCount > 0 ? " · " + listenbrainz.pendingCount + " queued listens" : "")
                color: listenbrainz.connected ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); wrapMode: Text.WordWrap
            }
            Text { text: "Import listening history"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
            Row {
                spacing: 10
                StyledCombo {
                    id: historySource
                    width: 150
                    model: ["ListenBrainz", "Last.fm"]
                }
                TextField {
                    id: historyUser
                    width: 260; height: 38
                    placeholderText: historySource.currentIndex === 0 && listenbrainz.connected ? "Username (blank = connected account)" : "Username"
                    color: Theme.text; placeholderTextColor: Theme.textDim
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); leftPadding: 14
                    background: Rectangle { radius: Theme.radiusLarge; color: Theme.surface; border.color: historyUser.activeFocus ? Theme.accent : Theme.border }
                }
                PillButton {
                    primary: true
                    text: listenbrainz.importing ? "Importing…" : "Import history"
                    enabled: !shell.offlineMode && !listenbrainz.importing
                             && (historyUser.text.length > 0 || (historySource.currentIndex === 0 && listenbrainz.connected))
                    onClicked: listenbrainz.importHistory(historySource.currentIndex === 0 ? "listenbrainz" : "lastfm", historyUser.text)
                }
            }
            Text {
                visible: listenbrainz.importStatus.length > 0
                width: parent.width
                text: listenbrainz.importStatus
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); wrapMode: Text.WordWrap
            }
            Text { text: "Discord Rich Presence"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Show what you're listening to on your Discord profile. Create an application at discord.com/developers, paste its Application ID below and upload your icon as an art asset named “hallucinate”. Status: " + discord.status
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            StyledCheck { text: "Enable Discord Rich Presence"; checked: discord.enabled; onToggled: discord.setEnabled(checked) }
            TextField {
                width: 320
                placeholderText: "Discord application ID"
                text: discord.appId
                selectByMouse: true
                color: Theme.text
                placeholderTextColor: Theme.textDim
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                background: Rectangle { radius: Theme.radiusSmall; color: Theme.surface; border.color: parent.activeFocus ? Theme.accent : Theme.border }
                onEditingFinished: discord.setAppId(text)
            }
            StyledCheck { text: "Hide when paused"; checked: discord.hidePaused; onToggled: discord.setPref("hidePaused", checked) }
            StyledCheck { text: "Hide cover art"; checked: discord.hideCover; onToggled: discord.setPref("hideCover", checked) }
            StyledCheck { text: "Privacy mode (don't share track details)"; checked: discord.privacy; onToggled: discord.setPref("privacy", checked) }

        }
        SettingsSection {
            id: sec_desktop
            objectName: "settings_desktop"
            title: "Desktop"
            keywords: "tray notifications close mini player"
            query: page.query
            StyledCheck {
                visible: shell.trayAvailable
                text: "Show system tray icon"
                checked: shell.trayEnabled
                onToggled: shell.setTrayEnabled(checked)
            }
            StyledCheck {
                visible: shell.trayAvailable
                enabled: shell.trayEnabled
                text: "Keep playing in the tray when the window is closed"
                checked: shell.closeToTray
                onToggled: shell.setCloseToTray(checked)
            }
            StyledCheck {
                visible: Qt.platform.os === "linux" || shell.trayAvailable
                text: "Show desktop notifications when tracks change"
                checked: shell.desktopNotifications
                onToggled: shell.setDesktopNotifications(checked)
            }
            PillButton { text: "Open mini player"; onClicked: shell.toggleMini() }

        }
        SettingsSection {
            id: sec_about
            objectName: "settings_about"
            title: "About"
            keywords: "version debug bug report update check logo"
            query: page.query
            Image {
                width: 260
                height: 210
                source: "../assets/logo.png"
                fillMode: Image.PreserveAspectFit
                sourceSize: Qt.size(600, 600)
                smooth: true
                Accessible.name: "Hallucinate logo"
            }
            Text {
                text: "Hallucinate " + shell.appVersion + " — a modern music library and player"
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Row {
                spacing: 10
                PillButton {
                    objectName: "copyDebugInfo"
                    text: "Copy debug info"
                    onClicked: { shell.copyDebugInfo(); Nav.notify("Debug info copied — paste it into your bug report") }
                }
                PillButton {
                    text: "Report a bug"
                    onClicked: Qt.openUrlExternally("https://github.com/Phosphene-dev/Hallucinate/issues/new")
                }
            }
            Text {
                visible: !shell.updates.supported
                text: "Updates come through Flathub (your software centre)."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Row {
                visible: shell.updates.supported
                spacing: 12
                StyledCheck {
                    objectName: "updateChecks"
                    text: "Tell me when a new version is out (checks GitHub once a day)"
                    checked: shell.updates.enabled
                    onToggled: shell.updates.setEnabled(checked)
                }
                PillButton {
                    anchors.verticalCenter: parent.verticalCenter
                    height: 32
                    text: shell.updates.busy ? "Checking…" : "Check now"
                    enabled: !shell.updates.busy && !shell.offlineMode
                    onClicked: shell.updates.checkNow()
                }
                PillButton {
                    objectName: "updateNow"
                    anchors.verticalCenter: parent.verticalCenter
                    height: 32
                    primary: true
                    visible: shell.updates.canInstall && (shell.updates.available || shell.updates.installing)
                    text: shell.updates.installing ? "Cancel" : "Update now"
                    enabled: shell.updates.installing || !shell.offlineMode
                    onClicked: shell.updates.installing ? shell.updates.cancelInstall() : Nav.installUpdate()
                }
            }
            Text {
                visible: shell.updates.status.length > 0
                text: shell.updates.status
                color: shell.updates.available ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                MouseArea {
                    anchors.fill: parent
                    enabled: shell.updates.available
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Qt.openUrlExternally(shell.updates.releaseUrl)
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Debug info lists versions, your system, display and audio setup and the recent log. It leaves out "
                    + "file paths, your music and account names."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
    }
    }
}
