import QtQuick
import QtQuick.Dialogs

// Native folder chooser; adds the picked folder to the library and starts scanning.
FolderDialog {
    title: qsTr("Choose your music folder")
    onAccepted: library.addFolder(selectedFolder.toString())
}
