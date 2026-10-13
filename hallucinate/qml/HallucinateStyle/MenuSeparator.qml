import QtQuick
import QtQuick.Templates as T
import ".."

T.MenuSeparator {
    id: control
    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             implicitContentHeight + topPadding + bottomPadding)
    leftPadding: 10
    rightPadding: 10
    topPadding: 5
    bottomPadding: 5
    contentItem: Rectangle {
        implicitWidth: 200
        implicitHeight: 1
        color: Theme.stroke
    }
}
