import QtQuick
import QtQuick.Controls
import "."

// A theme of your own: start from the current one, change its main colours, give it a name. It's saved as a
// theme file in your theme folder (where it can be edited or shared) and chosen straight away.
Dialog {
    id: dlg
    objectName: "themeEditor"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(480, (parent ? parent.width : 480) - 40)
    modal: true
    title: qsTr("Make my own theme")
    standardButtons: Dialog.Save | Dialog.Cancel
    readonly property var keys: [["bg", qsTr("Background")], ["surface", qsTr("Cards and fields")], ["text", qsTr("Text")],
                                 ["textDim", qsTr("Quieter text")], ["accent", qsTr("Accent")]]
    property var values: ({})
    onOpened: {
        var colors = themeManager.themeColors(themeManager.currentTheme)
        var v = {}
        for (var i = 0; i < keys.length; i++) v[keys[i][0]] = colors[keys[i][0]]
        values = v
        nameField.text = qsTr("%1 (mine)").arg(themeManager.currentTheme)
        nameField.forceActiveFocus()
        nameField.selectAll()
    }
    onAccepted: {
        var err = themeManager.saveCustomTheme(nameField.text, values)
        Nav.notify(err.length ? err : qsTr("Saved “%1” in your themes").arg(nameField.text.trim()))
    }
    Column {
        width: dlg.availableWidth
        spacing: 10
        TextField {
            id: nameField; width: parent.width; placeholderText: qsTr("Theme name"); selectByMouse: true; Accessible.name: qsTr("Theme name")
            onTextChanged: { var b = dlg.standardButton(Dialog.Save) || dlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }  // keeps your colours until it has a name
            onVisibleChanged: if (visible) { var b = dlg.standardButton(Dialog.Save) || dlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
        Repeater {
            model: dlg.keys
            Row {
                required property var modelData
                spacing: 10
                Rectangle {
                    width: 30; height: 30; radius: Theme.round(8)
                    anchors.verticalCenter: parent.verticalCenter
                    color: dlg.values[modelData[0]] || "transparent"
                    border.width: 1; border.color: Theme.border
                }
                Text {
                    textFormat: Text.PlainText
                    width: 140
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData[1]
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
                }
                TextField {
                    width: 130
                    text: dlg.values[modelData[0]] || ""
                    selectByMouse: true
                    Accessible.name: qsTr("%1 colour").arg(modelData[1])
                    onTextEdited: if (/^#[0-9a-fA-F]{6}$/.test(text)) { var v = Object.assign({}, dlg.values); v[modelData[0]] = text; dlg.values = v }
                }
            }
        }
        Text {
            textFormat: Text.PlainText
            width: parent.width
            wrapMode: Text.WordWrap
            text: qsTr("Colours as hex codes (#rrggbb). Everything else (rounded corners, font) comes from the current theme; the file in your theme folder can change those too.")
            color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
        }
    }
}
