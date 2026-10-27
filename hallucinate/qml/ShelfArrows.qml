import QtQuick
import "."

// Back and forward buttons over a row that scrolls sideways (Home's shelves, search results): they show while
// the pointer is over the row and there's more that way, and move it about a row's width. Lay it over the row:
//     Item { ListView { id: row; anchors.fill: parent; ... }  ShelfArrows { row: row; anchors.fill: parent } }
Item {
    id: arrows
    property var row: null
    property string what: "albums"   // for screen readers: "Earlier albums", "More albums"
    readonly property real minX: row ? row.originX - row.leftMargin : 0
    readonly property real maxX: row ? Math.max(minX, row.originX + row.contentWidth + row.rightMargin - row.width) : 0
    readonly property bool canBack: row !== null && row.contentX > minX + 1
    readonly property bool canOn: row !== null && row.contentX < maxX - 1
    readonly property bool shown: hover.hovered && shell.ui.shelfArrows !== "false"

    function page(dir) {
        if (!row) return
        var from = slide.running ? slide.to : row.contentX
        slide.to = Math.max(minX, Math.min(maxX, from + dir * Math.max(200, row.width * 0.8)))
        slide.restart()
    }
    NumberAnimation {
        id: slide
        target: arrows.row
        property: "contentX"
        duration: Theme.reduceMotion ? 0 : 260
        easing.type: Easing.OutCubic
    }
    HoverHandler { id: hover; acceptedDevices: PointerDevice.Mouse }

    Repeater {
        model: [-1, 1]
        delegate: Rectangle {
            required property int modelData
            readonly property bool can: modelData < 0 ? arrows.canBack : arrows.canOn
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -20
            x: modelData < 0 ? 4 : arrows.width - width - 4
            width: 40; height: 40; radius: Theme.round(20)
            color: Theme.popup
            border.width: 1; border.color: Theme.border
            opacity: arrows.shown && can ? (ma.containsMouse ? 1 : 0.85) : 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: Theme.reduceMotion ? 0 : 140 } }
            Icon {
                anchors.centerIn: parent
                width: 18; height: 18
                name: modelData < 0 ? "back" : "forward"
                color: ma.containsMouse ? Theme.text : Theme.textDim
            }
            MouseArea {
                id: ma
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: arrows.page(modelData)
            }
            Accessible.role: Accessible.Button
            Accessible.name: (modelData < 0 ? "Earlier " : "More ") + arrows.what
            Accessible.onPressAction: arrows.page(modelData)
        }
    }
}
