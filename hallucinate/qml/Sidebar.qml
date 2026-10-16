import QtQuick
import QtQuick.Controls
import "."

// Floating glass navigation rail. Collapsed it shows icons only; expanded it adds labels and the playlists.
Item {
    id: side
    property bool collapsed: shell.sidebarCollapsed
    property string section: ""
    property bool atRoot: true
    signal navigate(string id)
    signal openPlaylist(int id, string name)
    signal openSmartPlaylist(int id, string name)
    signal newPlaylist()
    signal newSmartPlaylist()

    readonly property int railWidth: 76
    readonly property int fullWidth: 236
    // Short windows (small screens, fractional scaling) get tighter entries; whatever still doesn't fit scrolls
    // above Settings, so the two never overlap.
    readonly property bool compact: height < 700
    readonly property int entryHeight: compact ? 34 : 42
    width: collapsed ? railWidth : fullWidth
    Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

    readonly property var pages: [
        { id: "home", t: "Home", i: "home" }, { id: "albums", t: "Albums", i: "album" },
        { id: "artists", t: "Artists", i: "artist" }, { id: "songs", t: "Songs", i: "songs" },
        { id: "folders", t: "Folders", i: "folder" },
        { id: "liked", t: "Liked Songs", i: "heart" }, { id: "stats", t: "Stats", i: "stats" },
        { id: "history", t: "History", i: "history" },
        { id: "recap", t: "Recap", i: "recap" }, { id: "visualizer", t: "Visualizer", i: "wave" }
    ]

    Rectangle {
        id: panel
        anchors { fill: parent; leftMargin: 10; topMargin: 10; bottomMargin: 10 }
        radius: 24
        color: Theme.glass
        border.width: 1
        border.color: Theme.stroke

        Flickable {
            id: navFlick
            objectName: "sidebarScroll"
            anchors { left: parent.left; right: parent.right; top: parent.top; bottom: footer.top; bottomMargin: 6 }
            clip: true
            contentWidth: width
            contentHeight: navContent.height
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: navFlick.contentHeight > navFlick.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }

            Item {
                id: navContent
                width: navFlick.width
                height: (side.collapsed ? plHeader.y + plHeader.height : plList.y + plList.height) + 8

                // Brand
                Item {
                    id: brand
                    anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: side.compact ? 8 : 12 }
                    height: side.compact ? 40 : 48
                    Image {
                        id: logo
                        x: side.collapsed ? (parent.width - width) / 2 : 14
                        anchors.verticalCenter: parent.verticalCenter
                        width: 32; height: 32
                        source: "../assets/hallucinate.png"; sourceSize: Qt.size(64, 64); smooth: true
                        Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                    }
                    FlagStripe {  // a pride theme's flag, quietly under the name
                        anchors { left: logo.right; leftMargin: 11; top: parent.verticalCenter; topMargin: 12 }
                        width: 44; height: 3
                        colors: Theme.themePalette
                        opacity: side.collapsed ? 0 : 0.85
                        visible: colors.length > 0 && opacity > 0
                        Behavior on opacity { NumberAnimation { duration: 140 } }
                    }
                    Text {
                        textFormat: Text.PlainText
                        anchors { left: logo.right; leftMargin: 10; verticalCenter: parent.verticalCenter }
                        text: "Hallucinate"
                        opacity: side.collapsed ? 0 : 1
                        visible: opacity > 0
                        Behavior on opacity { NumberAnimation { duration: 140 } }
                        color: Theme.text
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.fontSize(15)
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.3
                    }
                }

                Column {
                    id: navCol
                    anchors { left: parent.left; right: parent.right; top: brand.bottom; topMargin: side.compact ? 8 : 14; leftMargin: 10; rightMargin: 10 }
                    spacing: side.compact ? 2 : 4
                    Repeater {
                        model: side.pages.filter(function (p) { return shell.features[p.id] !== false })
                        RailButton {
                            required property var modelData
                            width: navCol.width
                            height: side.entryHeight
                            text: modelData.t
                            icon: modelData.i
                            collapsed: side.collapsed
                            selected: side.section === modelData.id && side.atRoot
                            onClicked: side.navigate(modelData.id)
                        }
                    }
                }

                Rectangle {
                    id: divider
                    anchors { left: parent.left; right: parent.right; top: navCol.bottom; topMargin: side.compact ? 8 : 12; leftMargin: 22; rightMargin: 22 }
                    height: 1
                    color: Theme.stroke
                }

                // Playlists: a list when expanded, a menu behind one button when collapsed
                Item {
                    id: plHeader
                    anchors { left: parent.left; right: parent.right; top: divider.bottom; topMargin: side.compact ? 6 : 10; leftMargin: 10; rightMargin: 10 }
                    height: side.collapsed ? side.entryHeight : 30
                    RailButton {
                        anchors.fill: parent
                        visible: side.collapsed
                        text: "Playlists"
                        icon: "playlist"
                        collapsed: true
                        selected: (side.section.indexOf("pl") === 0 || side.section.indexOf("smart") === 0) && side.atRoot
                        onClicked: playlistMenu.popup(side.railWidth - 10, 0)
                    }
                    Text {
                        textFormat: Text.PlainText
                        visible: !side.collapsed
                        anchors { left: parent.left; leftMargin: 14; verticalCenter: parent.verticalCenter }
                        text: "PLAYLISTS"
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(11)
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.2
                    }
                    IconButton {
                        id: newPlButton
                        visible: !side.collapsed
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                        icon: "plus"; size: 14; tip: "New playlist"
                        onClicked: newPlMenu.popup(newPlButton, 0, newPlButton.height)
                    }
                    Menu {
                        id: newPlMenu
                        MenuItem { text: "New playlist"; icon.name: "playlist"; onTriggered: side.newPlaylist() }
                        MenuItem { text: "New smart playlist"; icon.name: "smartlist"; onTriggered: side.newSmartPlaylist() }
                        MenuItem { text: "Import playlist file…"; icon.name: "folder"; onTriggered: Nav.importPlaylist() }
                    }
                    Menu {
                        id: playlistMenu
                        MenuItem { text: "New playlist…"; icon.name: "plus"; onTriggered: side.newPlaylist() }
                        MenuItem { text: "New smart playlist…"; icon.name: "smartlist"; onTriggered: side.newSmartPlaylist() }
                        MenuItem { text: "Import playlist file…"; icon.name: "folder"; onTriggered: Nav.importPlaylist() }
                        MenuSeparator {}
                        Instantiator {
                            model: userLib.playlists
                            delegate: MenuItem {
                                text: model.name
                                icon.name: "playlist"
                                onTriggered: side.openPlaylist(model.id, model.name)
                            }
                            onObjectAdded: (index, object) => playlistMenu.insertItem(index + 3, object)
                            onObjectRemoved: (index, object) => playlistMenu.removeItem(object)
                        }
                        Instantiator {
                            model: userLib.smartPlaylists
                            delegate: MenuItem {
                                text: model.name
                                icon.name: "smartlist"
                                onTriggered: side.openSmartPlaylist(model.id, model.name)
                            }
                            onObjectAdded: (index, object) => playlistMenu.addItem(object)
                            onObjectRemoved: (index, object) => playlistMenu.removeItem(object)
                        }
                    }
                }

                Column {
                    id: plList
                    visible: !side.collapsed
                    anchors { left: parent.left; right: parent.right; top: plHeader.bottom; topMargin: 4; leftMargin: 10; rightMargin: 10 }
                    Repeater {
                        model: userLib.playlists
                        RailButton {
                            width: plList.width
                            height: side.compact ? 32 : 36
                            text: model.name
                            icon: "playlist"
                            selected: side.section === "pl" + model.id && side.atRoot
                            hasMenu: true
                            onMenuRequested: plItemMenu.show(model.id, model.name, false)
                            onClicked: side.openPlaylist(model.id, model.name)
                        }
                    }
                    Repeater {
                        model: userLib.smartPlaylists
                        RailButton {
                            width: plList.width
                            height: side.compact ? 32 : 36
                            text: model.name
                            icon: "smartlist"
                            selected: side.section === "smart" + model.id && side.atRoot
                            hasMenu: true
                            onMenuRequested: plItemMenu.show(model.id, model.name, true)
                            onClicked: side.openSmartPlaylist(model.id, model.name)
                        }
                    }
                }
            }
        }

        // A soft edge when more entries are scrolled out of view below
        Rectangle {
            anchors { left: navFlick.left; right: navFlick.right; bottom: navFlick.bottom; leftMargin: 1; rightMargin: 1 }
            height: 28
            visible: navFlick.contentHeight > navFlick.height && !navFlick.atYEnd
            gradient: Gradient {
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 1; color: Theme.glassStrong }
            }
        }

        // Settings, the collapse toggle and scan progress stay at the bottom
        Column {
            id: footer
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; bottomMargin: side.compact ? 8 : 12; leftMargin: 10; rightMargin: 10 }
            spacing: side.compact ? 2 : 4
            ScanBar {
                width: parent.width - 16
                x: 8
                compact: true
                visible: active && !side.collapsed
            }
            RailButton {  // only with the update check turned on and a newer release out
                objectName: "updateAvailable"
                width: parent.width
                height: side.entryHeight
                visible: shell.updates.enabled && shell.updates.available
                text: shell.updates.installing ? "Updating… " + Math.round(shell.updates.installProgress * 100) + "%"
                                               : "Update to " + shell.updates.latestVersion
                icon: "download"
                collapsed: side.collapsed
                selected: true
                onClicked: {
                    if (shell.updates.installing) Nav.openSettings()
                    else if (shell.updates.canInstall) Nav.installUpdate()
                    else Qt.openUrlExternally(shell.updates.releaseUrl)
                }
            }
            RailButton {
                width: parent.width
                height: side.entryHeight
                text: "Settings"
                icon: "settings"
                collapsed: side.collapsed
                selected: side.section === "settings" && side.atRoot
                onClicked: side.navigate("settings")
            }
            RailButton {
                objectName: "sidebarToggle"
                width: parent.width
                height: side.entryHeight
                text: side.collapsed ? "Expand sidebar" : "Collapse sidebar"
                icon: "sidebar"
                collapsed: side.collapsed
                onClicked: shell.setSidebarCollapsed(!side.collapsed)
            }
        }
    }

    // Right-click on a playlist in the list: open, rename or edit its rules, delete
    Menu {
        id: plItemMenu
        objectName: "playlistItemMenu"
        property int pid: -1
        property string name: ""
        property bool smart: false
        function show(id, n, isSmart) { pid = id; name = n; smart = isSmart; popup() }
        MenuItem {
            text: "Open"; icon.name: plItemMenu.smart ? "smartlist" : "playlist"
            onTriggered: plItemMenu.smart ? side.openSmartPlaylist(plItemMenu.pid, plItemMenu.name) : side.openPlaylist(plItemMenu.pid, plItemMenu.name)
        }
        MenuItem {
            visible: !plItemMenu.smart
            height: visible ? implicitHeight : 0
            text: "Rename…"; icon.name: "edit"
            onTriggered: { renameField.text = plItemMenu.name; renamePl.open() }
        }
        MenuItem {
            visible: plItemMenu.smart
            height: visible ? implicitHeight : 0
            text: "Edit rules…"; icon.name: "edit"
            onTriggered: Nav.editSmartPlaylist(plItemMenu.pid, plItemMenu.name)
        }
        MenuSeparator {}
        MenuItem {
            text: "Delete…"; icon.name: "trash"; icon.color: Theme.error
            onTriggered: { deletePl.what = "“" + plItemMenu.name + "”"; deletePl.open() }
        }
    }
    Dialog {
        id: renamePl
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "Rename playlist"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { renameField.forceActiveFocus(); renameField.selectAll() }
        onAccepted: if (renameField.text.trim().length) userLib.renamePlaylist(plItemMenu.pid, renameField.text.trim())
        TextField { id: renameField; width: 280; selectByMouse: true; onAccepted: renamePl.accept() }
    }
    ConfirmDialog {
        id: deletePl
        title: plItemMenu.smart ? "Delete this smart playlist?" : "Delete this playlist?"
        confirmText: "Delete playlist"
        destructive: true
        body: what + " is deleted. The songs in it stay in your library."
        onAccepted: {
            var open = side.section === (plItemMenu.smart ? "smart" : "pl") + plItemMenu.pid
            if (plItemMenu.smart) userLib.deleteSmartPlaylist(plItemMenu.pid)
            else userLib.deletePlaylist(plItemMenu.pid)
            if (open) Nav.goHome()
        }
    }
}
