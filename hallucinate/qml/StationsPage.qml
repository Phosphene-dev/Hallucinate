import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "."

// Internet radio: your saved stations, and the Radio Browser directory to find more. Click a station to tune
// in; right-click (or long press) for the rest.
Item {
    id: page
    objectName: "stations"
    property string query: ""
    readonly property int playingId: player.hasTrack && player.current.kind === "station" ? (player.current.station_id || 0) : 0

    function showMenu(station) {
        stationMenu.station = station
        stationMenu.popup()
    }

    Connections {
        target: stations
        function onMessage(text) { Nav.notify(text) }
    }

    Menu {
        id: stationMenu
        objectName: "stationMenu"
        property var station: ({})
        MenuItem { text: "Play"; icon.name: "play"; onTriggered: stations.play(stationMenu.station.id) }
        MenuItem { text: "Play next"; icon.name: "next"; onTriggered: stations.playNext(stationMenu.station.id) }
        MenuSeparator {}
        MenuItem {
            text: "Rename…"; icon.name: "edit"
            onTriggered: { renameDlg.stationId = stationMenu.station.id; renameField.text = stationMenu.station.name; renameDlg.open() }
        }
        MenuItem { text: "Copy stream link"; icon.name: "playlist"; onTriggered: { shell.copyText(stationMenu.station.url); Nav.notify("Stream link copied") } }
        MenuItem {
            visible: (stationMenu.station.homepage || "").length > 0
            height: visible ? implicitHeight : 0
            text: "Open the station's website"; icon.name: "expand"
            onTriggered: Qt.openUrlExternally(stationMenu.station.homepage)
        }
        MenuSeparator {}
        MenuItem {
            objectName: "stationRemove"
            text: "Remove station"; icon.name: "remove"; icon.color: Theme.error
            onTriggered: stations.remove(stationMenu.station.id)
        }
    }

    Dialog {
        id: addDlg
        objectName: "addStationDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(460, (parent ? parent.width : 460) - 40)
        modal: true
        title: "Add a station"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { urlField.text = ""; nameField.text = ""; urlField.forceActiveFocus() }
        onAccepted: stations.add(urlField.text, nameField.text)
        Column {
            width: addDlg.availableWidth
            spacing: 10
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Paste the station's stream link. A .pls or .m3u link works too."
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            TextField {
                id: urlField
                objectName: "stationUrl"
                width: parent.width
                placeholderText: "https://…"
                selectByMouse: true
                Accessible.name: "Stream link"
                onAccepted: addDlg.accept()
            }
            TextField {
                id: nameField
                width: parent.width
                placeholderText: "Name (optional: the station's own name is used)"
                selectByMouse: true
                Accessible.name: "Station name"
                onAccepted: addDlg.accept()
            }
        }
    }
    Dialog {
        id: renameDlg
        property int stationId: 0
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: "Rename station"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: renameField.forceActiveFocus()
        onAccepted: stations.rename(stationId, renameField.text)
        TextField { id: renameField; width: 280; selectByMouse: true; Accessible.name: "Station name"; onAccepted: renameDlg.accept() }
    }
    FileDialog {
        id: importDlg
        title: "Import stations"
        nameFilters: ["Station lists (*.m3u *.m3u8 *.pls *.xspf)", "All files (*)"]
        onAccepted: Nav.notify(stations.importFile(selectedFile.toString()))
    }
    FileDialog {
        id: exportDlg
        title: "Export your stations"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "m3u"
        nameFilters: ["M3U playlist (*.m3u)"]
        onAccepted: Nav.notify(stations.exportFile(selectedFile.toString()))
    }

    // One station: its logo, name and details. Used for saved stations and search results alike.
    component StationRow: Rectangle {
        id: row
        property string name
        property string detail
        property string artUrl
        property bool playing: false
        property alias trailing: trailingSlot.data
        signal activated()
        signal menu()
        width: parent ? parent.width : 400
        height: 60
        radius: 14
        color: rowMouse.containsMouse || playing ? Theme.glassHover : "transparent"
        border.width: playing ? 1 : 0
        border.color: Theme.accent
        Cover {
            id: logo
            x: 10
            anchors.verticalCenter: parent.verticalCenter
            width: 40; height: 40; radius: 10
            source: row.artUrl
            fallback: (row.name || "?").charAt(0)
        }
        Column {
            anchors { left: logo.right; leftMargin: 12; right: trailingSlot.left; rightMargin: 10; verticalCenter: parent.verticalCenter }
            spacing: 3
            Text {
                textFormat: Text.PlainText
                width: parent.width
                elide: Text.ElideRight
                text: row.name
                color: row.playing ? Theme.accent : Theme.text
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
            }
            Text {
                textFormat: Text.PlainText
                width: parent.width
                elide: Text.ElideRight
                visible: text.length > 0
                text: row.playing && player.current.artist ? player.current.artist + " – " + player.current.title : row.detail
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
        MouseArea {
            id: rowMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onClicked: function (mouse) { mouse.button === Qt.RightButton ? row.menu() : row.activated() }
            onPressAndHold: row.menu()
            Accessible.role: Accessible.Button
            Accessible.name: (row.playing ? "Playing: " : "Play ") + row.name
            Accessible.onPressAction: row.activated()
        }
        Row {
            id: trailingSlot
            anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
            spacing: 6
        }
    }

    Flickable {
        id: fl
        anchors.fill: parent
        contentWidth: width
        contentHeight: col.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        Column {
            id: col
            x: 28; y: 20
            width: fl.width - 56
            spacing: 16

            Row {
                width: parent.width
                spacing: 12
                Column {
                    width: parent.width - actions.width - 12
                    spacing: 4
                    Text {
                        textFormat: Text.PlainText
                        text: "Internet radio"
                        color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: Theme.fontSize(25); font.weight: Font.Bold
                    }
                    Text {
                        textFormat: Text.PlainText
                        text: stations.count === 1 ? "1 station" : stations.count + " stations"
                        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
                    }
                }
                Row {
                    id: actions
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    PillButton { objectName: "addStation"; primary: true; text: stations.busy ? "Checking…" : "Add by link"; enabled: !stations.busy; onClicked: addDlg.open() }
                    PillButton { text: "Import"; onClicked: importDlg.open() }
                    PillButton { text: "Export"; enabled: stations.count > 0; onClicked: exportDlg.open() }
                }
            }

            // Find stations in the directory
            TextField {
                id: search
                objectName: "stationSearch"
                width: Math.min(520, parent.width)
                height: 40
                placeholderText: "Find stations by name or genre (jazz, BBC, lofi…)"
                color: Theme.text
                placeholderTextColor: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(14)
                leftPadding: 16
                selectByMouse: true
                Accessible.name: "Find stations"
                background: Rectangle { radius: height / 2; color: Theme.surface; border.color: search.activeFocus ? Theme.accent : Theme.border }
                onAccepted: { page.query = text.trim(); stations.search(page.query) }
                onTextChanged: if (!text.length) { page.query = ""; stations.search("") }
                Keys.onEscapePressed: text = ""
            }
            Text {
                textFormat: Text.PlainText
                visible: stations.searching || stations.status.length > 0
                text: stations.searching ? "Searching…" : stations.status
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
            }
            Column {
                objectName: "stationResults"
                width: parent.width
                spacing: 2
                visible: page.query.length > 0 && stations.results.count > 0
                SectionHeader { title: "From the directory"; subtitle: "Radio Browser, a free and open list of stations" }
                Repeater {
                    model: stations.results
                    StationRow {
                        required property var model
                        width: col.width
                        name: model.name
                        detail: model.detail
                        onActivated: stations.playResult(model.row)
                        onMenu: resultMenu.popupFor(model.row, model.saved)
                        trailing: [
                            PillButton {
                                text: model.saved ? "Saved" : "Save"
                                enabled: !model.saved
                                onClicked: stations.addResult(model.row)
                            }
                        ]
                    }
                }
            }
            Menu {
                id: resultMenu
                property int row: -1
                property bool saved: false
                function popupFor(r, s) { row = r; saved = s; popup() }
                MenuItem { text: "Listen"; icon.name: "play"; onTriggered: stations.playResult(resultMenu.row) }
                MenuItem { text: "Save to your stations"; icon.name: "plus"; enabled: !resultMenu.saved; onTriggered: stations.addResult(resultMenu.row) }
            }

            SectionHeader {
                visible: stations.count > 0
                title: "Your stations"
                subtitle: "Click to tune in. Next and previous move between them."
            }
            Column {
                objectName: "savedStations"
                width: parent.width
                spacing: 2
                Repeater {
                    model: stations.model
                    StationRow {
                        required property var model
                        width: col.width
                        name: model.name
                        detail: model.detail
                        artUrl: model.artUrl
                        playing: page.playingId === model.id
                        onActivated: page.playingId === model.id ? player.toggle() : stations.play(model.id)
                        onMenu: page.showMenu({ id: model.id, name: model.name, url: model.url, homepage: model.homepage })
                        trailing: [
                            Text {
                                visible: page.playingId === model.id
                                textFormat: Text.PlainText
                                text: player.playing ? "LIVE" : "PAUSED"
                                color: Theme.accent; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); font.weight: Font.Bold
                                font.letterSpacing: 1
                            }
                        ]
                    }
                }
            }
            Item { width: 1; height: 20; visible: emptyState.visible }
            EmptyState {
                id: emptyState
                anchors.horizontalCenter: parent.horizontalCenter
                visible: stations.count === 0 && page.query.length === 0
                icon: "station"
                title: "No stations yet"
                hint: "Find one above, or add a station you know by its stream link."
                actionText: "Add by link"
                onAction: addDlg.open()
            }
        }
    }
}
