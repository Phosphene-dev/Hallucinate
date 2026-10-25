import QtQuick
import QtQuick.Templates as T
import ".."

// Dialogs: the app's glass in front of the page. A soft shadow and a dimmed page set them apart; a short
// fade and scale brings them in. `destructive` turns the confirming button into a warning (deleting, trashing).
T.Dialog {
    id: control

    property bool destructive: false

    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding,
                            implicitHeaderWidth,
                            implicitFooterWidth)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             implicitContentHeight + topPadding + bottomPadding
                             + (implicitHeaderHeight > 0 ? implicitHeaderHeight + spacing : 0)
                             + (implicitFooterHeight > 0 ? implicitFooterHeight + spacing : 0))

    padding: 22
    topPadding: control.title !== "" ? 4 : 22
    spacing: 4

    background: Rectangle {
        radius: Theme.round(20)
        color: Theme.popup
        border.width: 1
        border.color: Theme.stroke
        SoftShadow { radius: parent.radius; spread: 34; offsetY: 12; strength: 0.42 }
        // a faint accent sheen along the top edge
        Rectangle {
            x: parent.radius; y: 0
            width: parent.width - 2 * parent.radius; height: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 0.5; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.55) }
                GradientStop { position: 1; color: "transparent" }
            }
        }
    }

    header: Text {
        textFormat: Text.PlainText
        text: control.title
        visible: control.title !== ""
        elide: Text.ElideRight
        leftPadding: 22; rightPadding: 22; topPadding: 20; bottomPadding: 10
        color: Theme.text
        font.family: Theme.displayFamily
        font.weight: Font.DemiBold
        font.pixelSize: Theme.fontSize(16)
    }

    footer: DialogButtonBox {
        visible: count > 0
        destructive: control.destructive
    }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 160; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: 180; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 120; easing.type: Easing.InCubic }
        NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: 120; easing.type: Easing.InCubic }
    }

    T.Overlay.modal: Rectangle {
        color: Theme.scrim
        Behavior on opacity { NumberAnimation { duration: 160 } }
    }
    T.Overlay.modeless: Rectangle {
        color: Qt.rgba(Theme.scrim.r, Theme.scrim.g, Theme.scrim.b, 0.15)
    }
}
