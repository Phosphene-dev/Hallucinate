import QtQuick
import QtQuick.Templates as T
import ".."

T.ToolTip {
    id: control

    x: parent ? (parent.width - implicitWidth) / 2 : 0
    y: -implicitHeight - 6

    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             implicitContentHeight + topPadding + bottomPadding)

    margins: 8
    horizontalPadding: 10
    verticalPadding: 6
    delay: 350

    closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutsideParent | T.Popup.CloseOnReleaseOutsideParent

    contentItem: Text {
        textFormat: Text.PlainText
        text: control.text
        wrapMode: Text.Wrap
        color: Theme.retro && Theme.light ? "#000000" : Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(12)
    }

    background: Rectangle {
        radius: Theme.round(8)
        // a retro light theme's tooltip is the pale yellow note of old desktops
        color: Theme.retro && Theme.light ? "#ffffe1" : Theme.popup
        border.width: 1
        border.color: Theme.retro ? (Theme.light ? "#000000" : Theme.border) : Theme.stroke
        SoftShadow { radius: parent.radius; spread: 10; offsetY: 3; strength: 0.22 }
        Bevel {}
    }

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 110 } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 80 } }
}
