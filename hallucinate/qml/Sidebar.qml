import QtQuick
import QtQuick.Controls
import "."

// Floating glass navigation rail. Collapsed it shows icons only; expanded it adds labels and the playlists.
Item {
    id: side
    // Collapsed by choice, or because the window is too narrow for labels and a page beside them (a window
    // on half a screen, or with the queue open): then it shows icons only until there's room again.
    property bool squeezed: false
    readonly property bool collapsed: shell.sidebarCollapsed || squeezed
    property string section: ""
    property bool atRoot: true
    // Playlists and smart playlists grouped by folder: {folders: [{name, items}], loose: [items]}, each item
    // {id, name, smart, folder}. Worked out again whenever either list changes.
    property int plRevision: 0
    Connections {
        target: userLib.playlists
        function onModelReset() { side.plRevision++ }
        function onRowsInserted() { side.plRevision++ }
        function onRowsRemoved() { side.plRevision++ }
        function onDataChanged() { side.plRevision++ }
    }
    Connections {
        target: userLib.smartPlaylists
        function onModelReset() { side.plRevision++ }
        function onRowsInserted() { side.plRevision++ }
        function onRowsRemoved() { side.plRevision++ }
        function onDataChanged() { side.plRevision++ }
    }
    // The order of the playlists (issue 103): by name either way, newest or oldest, most recently added to, most
    // songs, or your own (Move up and Move down in a playlist's menu). Folders keep to A–Z; inside one, the same order.
    readonly property string plSort: shell.ui.playlistSort || "name"
    readonly property var plCustom: (shell.ui.playlistOrder || "").split(",").filter(function (k) { return k.length })
    readonly property var plSorts: [{ id: "name", t: "Name, A–Z" }, { id: "name-desc", t: "Name, Z–A" }, { id: "newest", t: "Newest first" },
                                    { id: "oldest", t: "Oldest first" }, { id: "added", t: "Recently added to" },
                                    { id: "songs", t: "Most songs" }, { id: "custom", t: "My own order" }]
    function plKey(item) { return (item.smart ? "s" : "p") + item.id }
    function plCompare(a, b) {
        var byName = a.name.localeCompare(b.name, undefined, { sensitivity: "base", numeric: true })
        switch (plSort) {
        case "name-desc": return -byName
        case "newest": return (b.created || 0) - (a.created || 0) || byName
        case "oldest": return (a.created || 0) - (b.created || 0) || byName
        case "added": return (b.last_added || 0) - (a.last_added || 0) || byName
        case "songs": return (b.n || 0) - (a.n || 0) || byName
        case "custom":
            var ia = plCustom.indexOf(plKey(a)), ib = plCustom.indexOf(plKey(b))
            if (ia < 0 && ib < 0) return byName
            return ia < 0 ? 1 : ib < 0 ? -1 : ia - ib  // new playlists go to the end
        }
        return byName
    }
    // Move up/down: switches to "My own order", starting from the order shown now
    function plMove(item, step) {
        var flat = plTree.folders.reduce(function (acc, f) { return acc.concat(f.items) }, []).concat(plTree.loose)
        var sameFolder = flat.filter(function (x) { return (x.folder || "").toLowerCase() === (item.folder || "").toLowerCase() })
        var keys = flat.map(plKey), k = plKey(item)
        var at = sameFolder.map(plKey).indexOf(k), to = at + step
        if (at < 0 || to < 0 || to >= sameFolder.length) return
        var a = keys.indexOf(k), b = keys.indexOf(plKey(sameFolder[to]))
        keys[a] = keys[b]; keys[b] = k
        shell.setUiValue("playlistOrder", keys.join(","))
        shell.setUiValue("playlistSort", "custom")
    }
    readonly property var plTree: {
        var r = plRevision, s = plSort, c = plCustom, byFolder = {}, names = [], loose = []
        function add(list, smart) {
            for (var i = 0; i < list.length; i++) {
                var item = { id: list[i].id, name: list[i].name, smart: smart, folder: list[i].folder || "",
                             created: list[i].created || 0, last_added: list[i].last_added || 0, n: list[i].n || 0 }
                if (!item.folder) { loose.push(item); continue }
                var key = item.folder.toLowerCase()
                if (!byFolder[key]) { byFolder[key] = { name: item.folder, items: [] }; names.push(key) }
                byFolder[key].items.push(item)
            }
        }
        add(userLib.playlists.toList(), false)
        add(userLib.smartPlaylists.toList(), true)
        loose.sort(plCompare)
        for (var f in byFolder) byFolder[f].items.sort(plCompare)
        names.sort(function (a, b) { return byFolder[a].name.localeCompare(byFolder[b].name, undefined, { sensitivity: "base", numeric: true }) })
        return { folders: names.map(function (k) { return byFolder[k] }), loose: loose }
    }
    readonly property var folderNames: plTree.folders.map(function (f) { return f.name })
    property int folderRevision: 0  // (open and closed is kept in the settings: this makes it read again)
    function folderOpen(name) { return folderRevision >= 0 && shell.uiValue("playlistFolderOpen/" + name, "1") === "1" }
    function setFolderOpen(name, open) { shell.setUiValue("playlistFolderOpen/" + name, open ? "1" : "0"); folderRevision++ }

    // A playlist in the list: opens it; right-click for its menu
    component PlaylistEntry: RailButton {
        id: plEntry
        property var entry: ({})
        pick: Pick { target: plEntry; kind: plEntry.entry.smart ? "smart" : "playlist"; entry: plEntry.entry; carries: false }
        // a selection carried over a playlist (not a smart one: its rules choose its songs) is added to it
        dropping: plDrop.containsDrag
        DropArea {
            id: plDrop
            anchors.fill: parent
            keys: ["hallucinate/selection"]
            enabled: !plEntry.entry.smart
            onDropped: function (drop) {
                var p = Selection.songPaths()
                Selection.clear()
                Nav.addToPlaylist(plEntry.entry.id, plEntry.entry.name, p, "")
                drop.accept()
            }
        }
        height: side.compact ? 32 : 36
        text: entry.name || ""
        icon: entry.smart ? "smartlist" : "playlist"
        selected: side.section === (entry.smart ? "smart" : "pl") + entry.id && side.atRoot
        hasMenu: true
        onMenuRequested: plItemMenu.show(entry.id, entry.name, entry.smart, entry.folder)
        onClicked: entry.smart ? side.openSmartPlaylist(entry.id, entry.name) : side.openPlaylist(entry.id, entry.name)
    }
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

    readonly property var allPages: [
        { id: "home", t: "Home", i: "home" }, { id: "albums", t: "Albums", i: "album" },
        { id: "artists", t: "Artists", i: "artist" }, { id: "genres", t: "Genres", i: "genre" },
        { id: "songs", t: "Songs", i: "songs" },
        { id: "folders", t: "Folders", i: "folder" },
        { id: "liked", t: "Liked Songs", i: "heart" }, { id: "stats", t: "Stats", i: "stats" },
        { id: "history", t: "History", i: "history" },
        { id: "recap", t: "Recap", i: "recap" }, { id: "visualizer", t: "Visualizer", i: "wave" },
        { id: "stations", t: "Internet radio", i: "station" }, { id: "podcasts", t: "Podcasts", i: "podcast" }
    ]
    // In the order you've arranged them (Settings → Appearance → Sidebar, or right-click an entry)
    readonly property var pages: {
        var order = shell.sidebarOrder, byId = {}
        for (var i = 0; i < allPages.length; i++) byId[allPages[i].id] = allPages[i]
        return order.map(function (id) { return byId[id] }).filter(function (p) { return p !== undefined })
    }
    readonly property var shownPages: pages.filter(function (p) { return shell.features[p.id] !== false })

    Menu {
        id: pageMenu
        objectName: "sidebarPageMenu"
        property string page: ""
        readonly property int at: side.shownPages.map(function (p) { return p.id }).indexOf(page)
        MenuItem { text: "Move up"; icon.name: "up"; enabled: pageMenu.at > 0; onTriggered: shell.moveSidebarPage(pageMenu.page, -1) }
        MenuItem {
            text: "Move down"; icon.name: "down"; enabled: pageMenu.at >= 0 && pageMenu.at < side.shownPages.length - 1
            onTriggered: shell.moveSidebarPage(pageMenu.page, 1)
        }
        MenuSeparator {}
        MenuItem { text: "Rearrange…"; icon.name: "settings"; onTriggered: side.rearrange() }
    }
    signal rearrange()  // open Settings at the sidebar list

    Rectangle {
        id: panel
        anchors { fill: parent; leftMargin: 10; topMargin: 10; bottomMargin: 10 }
        radius: Theme.round(24)
        color: Theme.glass
        border.width: 1
        border.color: Theme.stroke
        Bevel {}

        Flickable {
            WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
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
                    TitleDrag { anchors.fill: parent }  // the name moves the window too (title bar built in)
                    Image {
                        id: logo
                        x: side.collapsed ? (side.railWidth - width) / 2 : 14  // (the rail's final width, not the moving one: no jump)
                        anchors.verticalCenter: parent.verticalCenter
                        width: 32; height: 32
                        source: "../assets/hallucinate.png"; sourceSize: Qt.size(64, 64); smooth: true
                        Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                        // Pointed at, it rocks from side to side along an arc, like a rainbow's, and settles back
                        // when the pointer leaves (#118); reduced motion keeps it still
                        transform: Rotation {
                            id: rock
                            origin.x: logo.width / 2; origin.y: logo.height * 1.6  // a pivot below: the tilt is an arc
                            angle: 0
                        }
                        HoverHandler { id: logoHover; objectName: "logoHover" }
                        readonly property bool rocking: logoHover.hovered && !Theme.reduceMotion
                        onRockingChanged: if (!rocking) settle.restart()
                        SequentialAnimation {
                            running: logo.rocking
                            loops: Animation.Infinite
                            NumberAnimation { target: rock; property: "angle"; to: -12; duration: 420; easing.type: Easing.InOutSine }
                            NumberAnimation { target: rock; property: "angle"; to: 12; duration: 840; easing.type: Easing.InOutSine }
                            NumberAnimation { target: rock; property: "angle"; to: 0; duration: 420; easing.type: Easing.InOutSine }
                        }
                        NumberAnimation { id: settle; target: rock; property: "angle"; to: 0; duration: 320; easing.type: Easing.OutBack }
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
                        font.pixelSize: (Theme.fontSize(15)) * Theme.displayScale
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.3
                    }
                }

                // Where a dragged entry would land: a line between entries
                Rectangle {
                    id: dropLine
                    property int index: -1
                    visible: index >= 0
                    z: 2
                    x: navCol.x + 14; width: navCol.width - 28; height: 2; radius: 1
                    y: navCol.y + index * (side.entryHeight + navCol.spacing) - navCol.spacing / 2 - 1
                    color: Theme.accent
                }
                Column {
                    id: navCol
                    anchors { left: parent.left; right: parent.right; top: brand.bottom; topMargin: side.compact ? 8 : 14; leftMargin: 10; rightMargin: 10 }
                    spacing: side.compact ? 2 : 4
                    Repeater {
                        model: side.shownPages
                        RailButton {
                            id: rail
                            required property var modelData
                            required property int index
                            objectName: "rail_" + modelData.id
                            hasMenu: true
                            z: dragger.active ? 3 : 0
                            opacity: dragger.active ? 0.85 : 1
                            transform: Translate { y: dragger.active ? dragger.activeTranslation.y : 0 }
                            Accessible.description: "Alt+Up or Alt+Down moves it"
                            Keys.onPressed: function (event) {
                                if (!(event.modifiers & Qt.AltModifier)) return
                                if (event.key === Qt.Key_Up) { shell.moveSidebarPage(modelData.id, -1); event.accepted = true }
                                else if (event.key === Qt.Key_Down) { shell.moveSidebarPage(modelData.id, 1); event.accepted = true }
                            }
                            // Drag an entry up or down to move it
                            // the slot the entry would take, and the line drawn at that slot's edge
                            readonly property int dropIndex: Math.max(0, Math.min(side.shownPages.length - 1,
                                Math.round((y + dragger.activeTranslation.y) / (side.entryHeight + navCol.spacing))))
                            DragHandler {
                                id: dragger
                                target: null
                                xAxis.enabled: false
                                onActiveChanged: {
                                    if (active) return
                                    dropLine.index = -1
                                    if (rail.dropIndex !== rail.index) shell.placeSidebarPage(rail.modelData.id, rail.dropIndex)
                                }
                                onActiveTranslationChanged: if (active) dropLine.index = rail.dropIndex > rail.index ? rail.dropIndex + 1 : rail.dropIndex
                            }
                            width: navCol.width
                            height: side.entryHeight
                            text: modelData.t
                            icon: modelData.i
                            collapsed: side.collapsed
                            selected: side.section === modelData.id && side.atRoot
                            onClicked: side.navigate(modelData.id)
                            onMenuRequested: { pageMenu.page = modelData.id; pageMenu.popup() }
                            // a selection carried onto Liked Songs is liked
                            dropping: likeDrop.containsDrag
                            DropArea {
                                id: likeDrop
                                anchors.fill: parent
                                keys: ["hallucinate/selection"]
                                enabled: rail.modelData.id === "liked"
                                onDropped: function (drop) {
                                    var p = Selection.songPaths()
                                    userLib.setLikedPaths(p, true)
                                    Selection.clear()
                                    Nav.notify(Theme.num(p.length) + (p.length === 1 ? " song" : " songs") + " liked")
                                    drop.accept()
                                }
                            }
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
                    IconButton {
                        id: sortPlButton
                        objectName: "playlistSortButton"
                        visible: !side.collapsed
                        anchors { right: newPlButton.left; rightMargin: 2; verticalCenter: parent.verticalCenter }
                        icon: "sort"; size: 14; tip: "Order: " + (side.plSorts.filter(function (o) { return o.id === side.plSort })[0] || side.plSorts[0]).t
                        onClicked: sortPlMenu.popup(sortPlButton, 0, sortPlButton.height)
                    }
                    Menu {
                        id: sortPlMenu
                        objectName: "playlistSortMenu"
                        Repeater {
                            model: side.plSorts
                            MenuItem {
                                required property var modelData
                                text: modelData.t
                                checkable: true
                                checked: side.plSort === modelData.id
                                onTriggered: shell.setUiValue("playlistSort", modelData.id)
                            }
                        }
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
                                text: Theme.plain(model.name)
                                icon.name: "playlist"
                                onTriggered: side.openPlaylist(model.id, model.name)
                            }
                            onObjectAdded: (index, object) => playlistMenu.insertItem(index + 4, object)  // after the three actions and the separator
                            onObjectRemoved: (index, object) => playlistMenu.removeItem(object)
                        }
                        Instantiator {
                            model: userLib.smartPlaylists
                            delegate: MenuItem {
                                text: Theme.plain(model.name)
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
                    objectName: "playlistList"
                    visible: !side.collapsed
                    anchors { left: parent.left; right: parent.right; top: plHeader.bottom; topMargin: 4; leftMargin: 10; rightMargin: 10 }
                    // folders first (each opens and closes, remembered), then the playlists in none
                    Repeater {
                        model: side.plTree.folders
                        Column {
                            id: folderBlock
                            required property var modelData
                            readonly property bool open: side.folderOpen(modelData.name)
                            width: plList.width
                            RailButton {
                                objectName: "playlistFolder_" + folderBlock.modelData.name
                                width: plList.width
                                height: side.compact ? 32 : 36
                                text: folderBlock.modelData.name + "  (" + Theme.num(folderBlock.modelData.items.length) + ")"
                                icon: folderBlock.open ? "down" : "next"
                                hasMenu: true
                                Accessible.name: "Folder " + folderBlock.modelData.name + (folderBlock.open ? ", open" : ", closed")
                                onMenuRequested: folderMenu.show(folderBlock.modelData.name)
                                onClicked: side.setFolderOpen(folderBlock.modelData.name, !folderBlock.open)
                            }
                            Repeater {
                                model: folderBlock.open ? folderBlock.modelData.items : []
                                PlaylistEntry { x: 14; width: plList.width - 14; entry: modelData; required property var modelData }
                            }
                        }
                    }
                    Repeater {
                        model: side.plTree.loose
                        PlaylistEntry { width: plList.width; entry: modelData; required property var modelData }
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
            ActivityIndicator {  // a scan, covers or genres, loudness, downloads: whatever's working
                width: side.collapsed ? parent.width : parent.width - 16
                x: side.collapsed ? 0 : 8
                compact: side.collapsed
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
                visible: !side.squeezed  // there's no room to expand it
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
        property string folder: ""
        function show(id, n, isSmart, inFolder) { pid = id; name = n; smart = isSmart; folder = inFolder || ""; popup() }
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
        Menu {
            id: moveMenu
            objectName: "moveToFolder"
            title: "Move to folder"
            icon.name: "folder"
            MenuItem { text: "New folder…"; icon.name: "plus"; onTriggered: { folderField.text = ""; newFolder.open() } }
            MenuItem {
                visible: plItemMenu.folder.length > 0
                height: visible ? implicitHeight : 0
                text: "Out of “" + Theme.plain(plItemMenu.folder) + "”"
                onTriggered: userLib.setPlaylistFolder(plItemMenu.pid, plItemMenu.smart, "")
            }
            MenuSeparator { visible: side.folderNames.length > 0; height: visible ? implicitHeight : 0 }
            Instantiator {
                model: side.folderNames
                delegate: MenuItem {
                    required property string modelData
                    text: Theme.plain(modelData)
                    checkable: true
                    checked: modelData === plItemMenu.folder
                    onTriggered: userLib.setPlaylistFolder(plItemMenu.pid, plItemMenu.smart, modelData)
                }
                onObjectAdded: (i, o) => moveMenu.addItem(o)
                onObjectRemoved: (i, o) => moveMenu.removeItem(o)
            }
        }
        MenuItem {
            objectName: "playlistMoveUp"
            text: "Move up"; icon.name: "up"
            onTriggered: side.plMove({ id: plItemMenu.pid, smart: plItemMenu.smart, folder: plItemMenu.folder }, -1)
        }
        MenuItem {
            text: "Move down"; icon.name: "down"
            onTriggered: side.plMove({ id: plItemMenu.pid, smart: plItemMenu.smart, folder: plItemMenu.folder }, 1)
        }
        MenuSeparator {}
        MenuItem {
            text: "Delete…"; icon.name: "trash"; icon.color: Theme.error
            onTriggered: { deletePl.what = "“" + plItemMenu.name + "”"; deletePl.open() }
        }
    }
    Dialog {
        id: newFolder
        objectName: "newFolderDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "New folder"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: folderField.forceActiveFocus()
        onAccepted: {
            var name = folderField.text.trim()
            if (!name.length) return
            userLib.setPlaylistFolder(plItemMenu.pid, plItemMenu.smart, name)
            side.setFolderOpen(name, true)
        }
        TextField {
            id: folderField; implicitWidth: 280; selectByMouse: true; placeholderText: "Folder name (Workout, Moods…)"
            onAccepted: if (text.trim().length) newFolder.accept()
            onTextChanged: { var b = newFolder.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
    }
    // Right-click on a folder: rename it, or let its playlists out (they stay, outside any folder)
    Menu {
        id: folderMenu
        objectName: "playlistFolderMenu"
        property string name: ""
        function show(n) { name = n; popup() }
        MenuItem { text: "Rename folder…"; icon.name: "edit"; onTriggered: { renameFolderField.text = folderMenu.name; renameFolder.open() } }
        MenuItem {
            objectName: "ungroupFolder"
            text: "Ungroup"; icon.name: "remove"
            onTriggered: { userLib.renamePlaylistFolder(folderMenu.name, ""); Nav.notify("The playlists in “" + folderMenu.name + "” are out of the folder") }
        }
    }
    Dialog {
        id: renameFolder
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "Rename folder"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { renameFolderField.forceActiveFocus(); renameFolderField.selectAll() }
        onAccepted: {
            var name = renameFolderField.text.trim()
            if (!name.length || name === folderMenu.name) return
            side.setFolderOpen(name, side.folderOpen(folderMenu.name))
            userLib.renamePlaylistFolder(folderMenu.name, name)
        }
        TextField { id: renameFolderField; implicitWidth: 280; selectByMouse: true; onAccepted: if (text.trim().length) renameFolder.accept() }
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
        TextField { id: renameField; implicitWidth: 280; selectByMouse: true; onAccepted: renamePl.accept() }
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
            Nav.routeGone(plItemMenu.smart ? "smart" : "playlist", plItemMenu.pid)
        }
    }
}
