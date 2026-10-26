import QtQuick
import QtQuick.Controls
import "."

// The window's own buttons when the title bar is built into the window (Settings → Desktop): minimize (can be
// hidden), maximize or restore, and close (which does what "When I close the window" says).
Row {
    id: controls
    property bool light: false   // white, over Now Playing's dark backdrop
    readonly property var win: Window.window
    readonly property bool maximized: win !== null && win.visibility === Window.Maximized
    spacing: 6
    // on the left, close comes first (as on macOS and GNOME's left-hand layout)
    layoutDirection: shell.titleBarSide === "left" ? Qt.RightToLeft : Qt.LeftToRight
    visible: shell.customTitleBar && win !== null && win.visibility !== Window.FullScreen

    component WinButton: Rectangle {
        id: b
        property string icon
        property string tip
        property bool danger: false
        property bool light: false
        signal clicked()
        width: 30; height: 30
        radius: Theme.round(15)
        color: ma.containsMouse ? (b.danger ? "#e5484d" : (b.light ? Qt.rgba(1, 1, 1, 0.16) : Theme.glassHover))
                                : (b.light ? Qt.rgba(1, 1, 1, 0.06) : Theme.glass)
        border.width: Theme.retro ? 0 : 1
        border.color: b.light ? Qt.rgba(1, 1, 1, 0.12) : Theme.stroke
        Bevel {}
        Icon {
            anchors.centerIn: parent
            width: 14; height: 14
            name: b.icon
            color: ma.containsMouse && b.danger ? "white" : (b.light ? "white" : Theme.text)
        }
        MouseArea {
            id: ma
            anchors.fill: parent
            hoverEnabled: true
            onClicked: b.clicked()
            ToolTip.visible: containsMouse
            ToolTip.delay: 600
            ToolTip.text: b.tip
        }
        Accessible.role: Accessible.Button
        Accessible.name: b.tip
        Accessible.onPressAction: b.clicked()
    }

    WinButton {
        objectName: "windowMinimize"
        light: controls.light
        visible: shell.titleBarMinimize
        icon: "winmin"; tip: "Minimize"
        onClicked: controls.win.showMinimized()
    }
    WinButton {
        objectName: "windowMaximize"
        light: controls.light
        icon: controls.maximized ? "winrestore" : "winmax"
        tip: controls.maximized ? "Restore" : "Maximize"
        onClicked: controls.maximized ? controls.win.showNormal() : controls.win.showMaximized()
    }
    WinButton {
        objectName: "windowClose"
        light: controls.light
        icon: "close"; tip: "Close"
        danger: true
        onClicked: controls.win.close()
    }
}
