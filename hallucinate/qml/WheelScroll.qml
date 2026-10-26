import QtQuick
import "."

// The mouse wheel for the list or page it's declared in. Qt's own wheel handling moved a page about 70 px a
// notch, threw away notches turned quickly (three notches went barely further than one) and moved high-resolution
// wheels (a Logitech G502 X sends a notch as eight small steps) less than half as far. Here every notch, or its
// share of one, moves the same distance (Settings → Appearance → Scroll speed), quick notches add up, and
// touchpads keep Qt's own smooth, flickable scrolling.
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
    readonly property real minY: view ? view.originY - view.topMargin : 0
    readonly property real maxY: view ? Math.max(minY, view.originY + view.contentHeight + view.bottomMargin - view.height) : 0
    property real targetY: 0
    target: null
    acceptedDevices: PointerDevice.Mouse
    // a list that can't scroll up and down (or isn't meant to be scrolled) leaves the wheel to what's around it
    enabled: view !== null && view.interactive && maxY - minY > 1
    onWheel: function (event) {
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
    property NumberAnimation scroll: NumberAnimation {
        target: ws.view
        property: "contentY"
        duration: Theme.reduceMotion ? 0 : 160
        easing.type: Easing.OutCubic
    }
}
