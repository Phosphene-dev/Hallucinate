import QtQuick
import QtQuick.Controls.impl
import QtQuick.Controls.Basic.impl
import QtQuick.Templates as T
import ".."

// Text fields: rounded, on the theme's surface, with an accent ring while typing.
T.TextField {
    id: control
    // A field without a label of its own is announced by what it asks for ("Search settings", "Last.fm API key")
    Accessible.name: placeholderText
    Accessible.description: echoMode === TextInput.Password ? placeholderText : ""  // Qt withholds a password field's name

    implicitWidth: implicitBackgroundWidth + leftInset + rightInset
                   || Math.max(contentWidth, placeholder.implicitWidth) + leftPadding + rightPadding
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             contentHeight + topPadding + bottomPadding,
                             placeholder.implicitHeight + topPadding + bottomPadding)

    padding: 8
    leftPadding: 12
    rightPadding: 12

    color: Theme.text
    selectionColor: Theme.accent
    selectedTextColor: Theme.onAccent
    placeholderTextColor: Theme.textDim
    verticalAlignment: TextInput.AlignVCenter
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSize(14)

    ContextMenu.menu: TextEditMenu {
        editor: control
    }
    readonly property string editMenuName: ContextMenu.menu ? ContextMenu.menu.objectName : ""

    PlaceholderText {
        id: placeholder
        x: control.leftPadding
        y: control.topPadding
        width: control.width - (control.leftPadding + control.rightPadding)
        height: control.height - (control.topPadding + control.bottomPadding)
        text: control.placeholderText
        font: control.font
        color: control.placeholderTextColor
        verticalAlignment: control.verticalAlignment
        visible: !control.length && !control.preeditText && (!control.activeFocus || control.horizontalAlignment !== Qt.AlignHCenter)
        elide: Text.ElideRight
        renderType: control.renderType
    }

    background: Rectangle {
        implicitWidth: 200
        implicitHeight: 38
        radius: Theme.radius
        color: Theme.surface
        opacity: control.enabled ? 1 : 0.6
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? Theme.accent : Theme.border
        Behavior on border.color { ColorAnimation { duration: 120 } }
        Bevel { sunken: true }
    }
}
