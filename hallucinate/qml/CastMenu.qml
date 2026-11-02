import QtQuick
import QtQuick.Controls
import "."

// Play on: this computer, or a Chromecast or DLNA/UPnP device found on the network. Opening it looks for devices
// (a few seconds); the list fills in as they answer.
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
            text: Theme.plain(modelData.name) + (modelData.model && modelData.model !== modelData.name
                                                 ? "  ·  " + Theme.plain(modelData.model) : "")
            icon.name: modelData.kind === "chromecast" ? "speaker" : "tv"
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
}
