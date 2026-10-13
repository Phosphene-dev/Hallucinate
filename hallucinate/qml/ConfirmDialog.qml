import QtQuick
import QtQuick.Controls
import "."

// "Are you sure?" with the action named on its button. Set destructive for anything that deletes or trashes.
// keys/what carry what the action applies to, for the dialog's onAccepted.
Dialog {
    id: dlg
    property var keys: []
    property string what: ""
    property string body: ""
    property string confirmText: "OK"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: parent && parent.width > 0 ? Math.min(440, parent.width - 40) : 440
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel
    function nameButton() { var b = standardButton(Dialog.Ok); if (b) b.text = confirmText }
    Component.onCompleted: nameButton()
    onConfirmTextChanged: nameButton()
    Text {
        textFormat: Text.PlainText
        width: dlg.availableWidth
        wrapMode: Text.WordWrap
        text: dlg.body
        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13)
        lineHeight: 1.15
    }
}
