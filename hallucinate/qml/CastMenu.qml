import QtQuick
import QtQuick.Controls
import "."

// Play on: this computer, or a Chromecast, DLNA/UPnP device, AirPlay speaker or Snapcast room found on the network.
// Opening it looks for devices (a few seconds); the list fills in as they answer. AirPlay speakers and Snapcast
// rooms can also play together (Play on several).
Menu {
    id: castMenu
    objectName: "castMenu"
    onAboutToShow: { casting.refresh(); handoff.refresh() }

    MenuItem {
        objectName: "castHere"
        text: qsTr("This computer")
        icon.name: "computer"
        checkable: true
        checked: !casting.active && casting.connecting.length === 0
        // (a click toggles the tick and so breaks the binding: put it back, the state says which is ticked)
        onTriggered: { casting.cancelConnecting(); casting.stopCasting(); checked = Qt.binding(() => !casting.active && casting.connecting.length === 0) }
    }
    MenuSeparator {}
    MenuItem {  // a phone playing the music itself (picked on the phone, in its remote)
        objectName: "castPhone"
        visible: casting.deviceKind === "phone"
        height: visible ? implicitHeight : 0
        text: Theme.plain(casting.deviceName)
        icon.name: "phone"
        checkable: true
        checked: true
        onTriggered: checked = true  // (it's chosen on the phone; This computer brings the music back)
    }
    MenuItem {
        visible: casting.connecting.length > 0
        height: visible ? implicitHeight : 0
        enabled: false
        text: qsTr("Connecting to %1…").arg(Theme.plain(casting.connecting))
    }
    Instantiator {
        model: casting.devices
        delegate: MenuItem {
            required property var modelData
            text: Theme.plain(modelData.name) + (modelData.unsupported ? "  ·  " + modelData.unsupported
                                                 : modelData.model && modelData.model !== modelData.name
                                                 ? "  ·  " + Theme.plain(modelData.model) : "")
            enabled: !modelData.unsupported
            icon.name: Theme.castIcon(modelData.kind)
            checkable: true
            checked: modelData.active
            onTriggered: { if (!modelData.active) casting.castTo(modelData.id); checked = Qt.binding(() => modelData.active) }
        }
        onObjectAdded: (i, o) => castMenu.insertItem(3 + i, o)
        onObjectRemoved: (i, o) => castMenu.removeItem(o)
    }
    MenuItem {
        objectName: "castSearching"
        visible: casting.searching
        height: visible ? implicitHeight : 0
        enabled: false
        text: qsTr("Looking for devices on your network…")
    }
    MenuItem {
        objectName: "castNone"
        visible: !casting.searching && casting.devices.length === 0
        height: visible ? implicitHeight : 0
        enabled: false
        text: qsTr("No devices found")
    }
    MenuItem {
        objectName: "castSeveral"
        readonly property int groupable: casting.devices.filter(function (d) { return d.groupable }).length
        visible: groupable >= 2
        height: visible ? implicitHeight : 0
        text: qsTr("Play on several together…")
        icon.name: "speakers"
        onTriggered: castMenu.groupDialog.open()
    }
    MenuSeparator {}
    Menu {  // another computer running Hallucinate: hand what's playing over to it
        id: computersMenu
        objectName: "handoffMenu"
        title: qsTr("Hand over to another computer")
        icon.name: "computer"
        Instantiator {
            model: handoff.computers
            delegate: MenuItem {
                required property var modelData
                text: modelData.paired ? Theme.plain(modelData.name) + (modelData.online ? "" : "  ·  " + qsTr("not found just now"))
                                       : qsTr("Pair with %1…").arg(Theme.plain(modelData.name))
                enabled: !handoff.busy.length && (!modelData.paired || player.hasTrack)
                onTriggered: modelData.paired ? handoff.handTo(modelData.id)
                                              : Nav.pairComputer(modelData.host, modelData.port, modelData.name)
            }
            onObjectAdded: (i, o) => computersMenu.insertItem(i, o)
            onObjectRemoved: (i, o) => computersMenu.removeItem(o)
        }
        MenuItem {
            visible: handoff.searching
            height: visible ? implicitHeight : 0
            enabled: false
            text: qsTr("Looking for other computers…")
        }
        MenuSeparator {}
        MenuItem {
            text: qsTr("Pair with another computer…")
            onTriggered: Nav.pairComputer("", 8483, "")
        }
    }
    MenuItem {
        text: qsTr("Look again")
        icon.name: "radio"
        enabled: !casting.searching
        onTriggered: { casting.refresh(); handoff.refresh() }
    }
    MenuItem {
        text: qsTr("Casting settings…")
        onTriggered: Nav.openSettingsAt("casting")
    }

    // Play on several: AirPlay speakers and Snapcast rooms, ticked, play the same thing together
    property Dialog groupDialog: Dialog {
        objectName: "castGroupDialog"
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        title: qsTr("Play on several together")
        property var chosen: ({})
        readonly property int count: Object.keys(chosen).filter(function (k) { return chosen[k] }).length
        onOpened: {
            var c = {}
            casting.devices.forEach(function (d) { if (d.groupable && d.active) c[d.id] = true })
            chosen = c
        }
        footer: DialogButtonBox {
            Button {
                objectName: "castGroupPlay"
                text: qsTr("Play together")
                enabled: castMenu.groupDialog.count >= 2
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
            }
            Button { text: qsTr("Cancel"); DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
        }
        onAccepted: casting.castToGroup(Object.keys(chosen).filter(function (k) { return chosen[k] }))
        Column {
            spacing: 6
            width: Math.min(420, Overlay.overlay ? Overlay.overlay.width - 80 : 420)
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("AirPlay speakers and Snapcast rooms can play the same music in step. Chromecasts and DLNA devices can't be kept in step, so they aren't listed.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Repeater {
                model: casting.devices.filter(function (d) { return d.groupable })
                StyledCheck {
                    required property var modelData
                    objectName: "castGroup_" + modelData.id
                    text: modelData.name
                    checked: castMenu.groupDialog.chosen[modelData.id] === true
                    onToggled: {
                        var c = Object.assign({}, castMenu.groupDialog.chosen)
                        c[modelData.id] = checked
                        castMenu.groupDialog.chosen = c
                    }
                }
            }
        }
    }
}
