import QtQuick
import "."

// The mouse wheel for the list or page it's declared in. Qt's own wheel handling moved a page about 70 px a
// notch, threw away notches turned quickly (three notches went barely further than one) and moved high-resolution
// wheels (a Logitech G502 X sends a notch as eight small steps) less than half as far. Here every notch, or its
// share of one, moves the same distance (Settings → Appearance → Scroll speed), quick notches add up, and
// touchpads keep Qt's own smooth, flickable scrolling.
// In a row that scrolls sideways (Home's shelves) Shift+wheel, or a tilt wheel, moves the row; the plain wheel
// moves the page, or the row first (Settings → Appearance → "Mouse wheel over a row of albums").
//     ListView { WheelScroll {} ... }
WheelHandler {
    id: ws
    // what it scrolls: the list or page it's declared in, or, for a row that only scrolls sideways (Home's
    // shelves), the page around it, so the wheel over a shelf still moves the page up and down
    readonly property var view: {
        var p = parent
        while (p) {
            if (p.contentY !== undefined && p.originY !== undefined && p.flickableDirection !== undefined
                    && p.flickableDirection !== Flickable.HorizontalFlick
                    && p.contentHeight + p.topMargin + p.bottomMargin > p.height + 1)
                return p
            p = p.parent
        }
        return null
    }
    // the row itself, when it's one that scrolls sideways
    readonly property var row: {
        // (declared in a list, a handler can land in its contentItem)
        for (var p = parent, n = 0; p && n < 2; p = p.parent, n++)
            if (p.orientation === ListView.Horizontal) return p
        return null
    }
    readonly property real maxX: row ? Math.max(row.originX, row.originX + row.contentWidth - row.width) : 0
    property real targetX: 0
    readonly property real minY: view ? view.originY - view.topMargin : 0
    readonly property real maxY: view ? Math.max(minY, view.originY + view.contentHeight + view.bottomMargin - view.height) : 0
    property real targetY: 0
    target: null
    acceptedDevices: PointerDevice.Mouse
    // a list that can't scroll up and down (or isn't meant to be scrolled) leaves the wheel to what's around it
    enabled: (view !== null && view.interactive && maxY - minY > 1) || row !== null
    // moves the row by `steps` notches; false when it can't go that way (at its end, or it all fits)
    function moveRow(steps) {
        if (!row || !row.interactive || maxX - row.originX < 1) return false
        var from = rowScroll.running ? targetX : row.contentX
        var to = Math.max(row.originX, Math.min(maxX, from - steps * 220 * shell.scrollSpeed))
        if (Math.abs(to - from) < 0.5) return false
        targetX = to
        rowScroll.to = to
        rowScroll.restart()
        return true
    }
    onWheel: function (event) {
        if (row && event.angleDelta.x === 0 && event.angleDelta.y !== 0) {
            var sideways = (event.modifiers & Qt.ShiftModifier) !== 0
            if (sideways || shell.ui.shelfWheel === "row") {
                if (moveRow(event.angleDelta.y / 120) || sideways) return
                // at the row's end the page moves on
            }
        }
        var steps = event.angleDelta.y / 120
        if (steps === 0 || !view) {
            event.accepted = false  // sideways (a tilt wheel, Shift): for the row itself
            return
        }
        var from = scroll.running ? ws.targetY : view.contentY
        ws.targetY = Math.max(ws.minY, Math.min(ws.maxY, from - steps * 110 * shell.scrollSpeed))
        scroll.to = ws.targetY
        scroll.restart()
    }
    property NumberAnimation rowScroll: NumberAnimation {
        target: ws.row
        property: "contentX"
        duration: Theme.reduceMotion ? 0 : 160
        easing.type: Easing.OutCubic
    }
    property NumberAnimation scroll: NumberAnimation {
        target: ws.view
        property: "contentY"
        duration: Theme.reduceMotion ? 0 : 160
        easing.type: Easing.OutCubic
    }
}
