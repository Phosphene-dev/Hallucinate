import QtQuick
import QtQuick.Templates as T
import ".."

// The buttons along the bottom of a dialog, as the app's pill buttons, on the right. The confirming one (OK,
// Save, Yes…) is filled with the accent, or with the warning colour when the dialog is destructive.
T.DialogButtonBox {
    id: control

    property bool destructive: false

    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             implicitContentHeight + topPadding + bottomPadding)
    contentWidth: (contentItem as ListView)?.contentWidth

    spacing: 10
    padding: 22
    topPadding: 12
    alignment: Qt.AlignRight

    delegate: T.Button {
        id: btn
        readonly property bool primary: DialogButtonBox.buttonRole === DialogButtonBox.AcceptRole
                                        || DialogButtonBox.buttonRole === DialogButtonBox.YesRole
                                        || DialogButtonBox.buttonRole === DialogButtonBox.ApplyRole
        readonly property color fill: control.destructive ? Theme.error : Theme.accent
        implicitWidth: Math.max(96, label.implicitWidth + 40)
        implicitHeight: 38
        focusPolicy: Qt.StrongFocus
        hoverEnabled: true
        contentItem: Text {
            id: label
            textFormat: Text.PlainText
            text: btn.text
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: btn.primary ? (control.destructive ? "white" : Theme.onAccent) : Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(14)
            font.weight: Font.DemiBold
        }
        background: Rectangle {
            radius: Theme.round(height / 2)
            color: btn.primary ? (btn.down ? Qt.darker(btn.fill, 1.15) : btn.hovered ? Qt.lighter(btn.fill, 1.1) : btn.fill)
                               : (btn.down ? Theme.surface : btn.hovered ? Theme.surfaceHi : Theme.surface)
            border.width: btn.primary ? 0 : 1
            border.color: Theme.border
            Behavior on color { ColorAnimation { duration: 100 } }
            Rectangle {
                anchors { fill: parent; margins: -3 }
                radius: Theme.round(height / 2)
                color: "transparent"
                border.width: 2
                border.color: Theme.accent
                visible: btn.visualFocus
            }
        }
    }

    contentItem: ListView {
        implicitWidth: contentWidth
        model: control.contentModel
        spacing: control.spacing
        orientation: ListView.Horizontal
        boundsBehavior: Flickable.StopAtBounds
        snapMode: ListView.SnapToItem
    }

    background: Item { implicitHeight: 38 }
}
