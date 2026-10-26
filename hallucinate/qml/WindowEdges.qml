import QtQuick
import "."

// With the title bar built into the window there's no system frame to resize it by: thin strips along the
// edges and corners hand a drag to the window manager instead. Not while maximized or full screen.
Item {
    id: edges
    readonly property var win: Window.window
    property int grip: 6
    anchors.fill: parent
    z: 1000
    visible: shell.customTitleBar && win !== null && win.visibility === Window.Windowed

    component Edge: MouseArea {
        property int edgeMask: 0
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onPressed: if (Window.window) Window.window.startSystemResize(edgeMask)
    }
    Edge { edgeMask: Qt.LeftEdge; cursorShape: Qt.SizeHorCursor
           anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: edges.grip * 2; bottomMargin: edges.grip * 2 } width: edges.grip }
    Edge { edgeMask: Qt.RightEdge; cursorShape: Qt.SizeHorCursor
           anchors { right: parent.right; top: parent.top; bottom: parent.bottom; topMargin: edges.grip * 2; bottomMargin: edges.grip * 2 } width: edges.grip }
    Edge { edgeMask: Qt.TopEdge; cursorShape: Qt.SizeVerCursor
           anchors { top: parent.top; left: parent.left; right: parent.right; leftMargin: edges.grip * 2; rightMargin: edges.grip * 2 } height: edges.grip }
    Edge { edgeMask: Qt.BottomEdge; cursorShape: Qt.SizeVerCursor
           anchors { bottom: parent.bottom; left: parent.left; right: parent.right; leftMargin: edges.grip * 2; rightMargin: edges.grip * 2 } height: edges.grip }
    Edge { edgeMask: Qt.TopEdge | Qt.LeftEdge; cursorShape: Qt.SizeFDiagCursor
           anchors { top: parent.top; left: parent.left } width: edges.grip * 2; height: edges.grip * 2 }
    Edge { edgeMask: Qt.TopEdge | Qt.RightEdge; cursorShape: Qt.SizeBDiagCursor
           anchors { top: parent.top; right: parent.right } width: edges.grip * 2; height: edges.grip * 2 }
    Edge { edgeMask: Qt.BottomEdge | Qt.LeftEdge; cursorShape: Qt.SizeBDiagCursor
           anchors { bottom: parent.bottom; left: parent.left } width: edges.grip * 2; height: edges.grip * 2 }
    Edge { edgeMask: Qt.BottomEdge | Qt.RightEdge; cursorShape: Qt.SizeFDiagCursor
           anchors { bottom: parent.bottom; right: parent.right } width: edges.grip * 2; height: edges.grip * 2 }
}
