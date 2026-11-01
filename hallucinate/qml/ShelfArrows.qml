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

    function page(dir) { slideBy(dir * Math.max(200, row ? row.width * 0.8 : 0), 260) }
    // Moves the row by dx (quick turns add up); false when it can't go that way
    function slideBy(dx, ms) {
        if (!row || maxX - minX < 1) return false
        var from = slide.running ? slide.to : row.contentX
        var to = Math.max(minX, Math.min(maxX, from + dx))
        if (Math.abs(to - from) < 0.5) return false
        slide.duration = Theme.reduceMotion ? 0 : ms
        slide.to = to
        slide.restart()
        return true
    }
    NumberAnimation {
        id: slide
        target: arrows.row
        property: "contentX"
        easing.type: Easing.OutCubic
    }
    HoverHandler { id: hover; acceptedDevices: PointerDevice.Mouse }

    // The mouse wheel over the row (#109). A MouseArea's wheel, which every platform delivers alike: a
    // WheelHandler on the list didn't get the wheel on the tester's desktop. Clicks and hovering go through
    // (it takes no buttons). What it doesn't use goes on to the page.
    MouseArea {
        objectName: "shelfWheel"
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        onWheel: function (wheel) {
            wheel.accepted = false
            if (!arrows.row || wheel.angleDelta.x !== 0 || wheel.angleDelta.y === 0) return  // sideways: the list's
            if (wheel.phase !== Qt.NoScrollPhase && wheel.pixelDelta.y !== 0) return  // a touchpad: the list's own
            var sideways = (wheel.modifiers & Qt.ShiftModifier) !== 0
            var mode = shell.ui.shelfWheel || "auto"
            // (a page scroll already under way carries on past the row)
            var takes = sideways || mode === "row" || (mode === "auto" && Date.now() - WheelLatch.pageAt > WheelLatch.settle)
            if (!takes) return
            if (arrows.slideBy(-wheel.angleDelta.y / 120 * 220 * shell.scrollSpeed, 160) || sideways)
                wheel.accepted = true  // at the row's end the page moves on
        }
    }

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
            Accessible.name: (modelData < 0 ? qsTr("Earlier ") : qsTr("More ")) + arrows.what
            Accessible.onPressAction: arrows.page(modelData)
        }
    }
}
