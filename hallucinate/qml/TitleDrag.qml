import QtQuick
import "."

// A stretch of the window that acts as its title bar when the title bar is built in: drag it to move the
// window, double-click to maximize or restore. Put it under the row's buttons and fields; they keep their clicks.
Item {
    id: drag
    readonly property var win: Window.window
    enabled: shell.customTitleBar && win !== null && win.visibility !== Window.FullScreen

    DragHandler {
        target: null
        grabPermissions: PointerHandler.CanTakeOverFromAnything
        onActiveChanged: if (active && drag.win) drag.win.startSystemMove()
    }
    TapHandler {
        acceptedButtons: Qt.LeftButton
        onDoubleTapped: {
            if (!drag.win) return
            if (drag.win.visibility === Window.Maximized) drag.win.showNormal()
            else drag.win.showMaximized()
        }
    }
}
