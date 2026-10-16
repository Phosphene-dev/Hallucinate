import QtQuick
import QtQuick.Controls
import "."

// Right-click on a text field: the usual editing actions in the app's own menu. Qt's built-in one opens as a
// native menu, which ignores the theme (white highlight on a dark window).
Menu {
    id: menu
    objectName: "textEditMenu"
    property Item editor
    popupType: Popup.Item
    MenuItem { text: "Undo"; enabled: menu.editor && menu.editor.canUndo; onTriggered: menu.editor.undo() }
    MenuItem { text: "Redo"; enabled: menu.editor && menu.editor.canRedo; onTriggered: menu.editor.redo() }
    MenuSeparator {}
    MenuItem {
        text: "Cut"
        enabled: menu.editor && !menu.editor.readOnly && menu.editor.selectedText.length > 0
                 && menu.editor.echoMode === TextInput.Normal
        onTriggered: menu.editor.cut()
    }
    MenuItem {
        text: "Copy"
        enabled: menu.editor && menu.editor.selectedText.length > 0 && menu.editor.echoMode === TextInput.Normal
        onTriggered: menu.editor.copy()
    }
    MenuItem { text: "Paste"; enabled: menu.editor && !menu.editor.readOnly && menu.editor.canPaste; onTriggered: menu.editor.paste() }
    MenuItem {
        text: "Delete"
        enabled: menu.editor && !menu.editor.readOnly && menu.editor.selectedText.length > 0
        onTriggered: menu.editor.remove(menu.editor.selectionStart, menu.editor.selectionEnd)
    }
    MenuSeparator {}
    MenuItem { text: "Select all"; enabled: menu.editor && menu.editor.length > 0; onTriggered: menu.editor.selectAll() }
}
