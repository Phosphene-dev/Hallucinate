pragma Singleton
import QtQuick

// Dragging over a list with the mouse (see Pick): from an item that isn't selected it paints a selection across the
// items passed over; from one that is, it picks the whole selection up, to drop on a playlist in the sidebar or on
// the queue. Near the top or bottom of a scrolling list the list scrolls along.
QtObject {
    id: drag

    property var pick: null            // the Pick a mouse press was on (none for touch: press-and-hold menus are touch's)
    property bool painting: false
    property bool carrying: false
    property var base: []              // the selection when painting began (painting adds to it)
    property int from: -1
    property real sceneX: 0            // the pointer, in the window
    property real sceneY: 0
    property real pressX: 0
    property real pressY: 0
    property bool swallowClick: false  // the release ending a drag isn't also a click
    property var _picks: new Map()      // delegate Item → its Pick (to find an item under the pointer)

    function register(item, p) { if (item) _picks.set(item, p) }
    function unregister(item, p) { if (item && _picks.get(item) === p) _picks.delete(item) }

    function press(p, area, mouse) {
        var real = mouse.source === undefined || mouse.source === Qt.MouseEventNotSynthesized
        pick = real && mouse.button === Qt.LeftButton && !(mouse.modifiers & (Qt.ControlModifier | Qt.ShiftModifier)) ? p : null
        painting = carrying = false
        swallowClick = false
        // a real mouse drags the selection, not the list (touch still scrolls it)
        area.preventStealing = pick !== null
        if (!pick) return
        var s = area.mapToItem(null, mouse.x, mouse.y)
        pressX = sceneX = s.x; pressY = sceneY = s.y
    }
    function move(area, mouse) {
        if (!pick) return
        var s = area.mapToItem(null, mouse.x, mouse.y)
        sceneX = s.x; sceneY = s.y
        if (!painting && !carrying) {
            if (Math.abs(sceneX - pressX) < Qt.styleHints.startDragDistance && Math.abs(sceneY - pressY) < Qt.styleHints.startDragDistance) return
            if (pick.selected && pick.carries) {
                carrying = true
            } else {
                painting = true
                base = Selection.items.slice()
                from = pick.index
                if (Selection.count && Selection.domainOf(pick.kind) !== Selection.domain) base = []
            }
        }
        if (painting) paintTo(sceneX, sceneY)
    }
    // Ends a drag; true when it was one (so the click that follows doesn't also act)
    function release(area) {
        if (area) area.preventStealing = false
        var was = painting || carrying
        if (carrying && dropAt) dropAt(sceneX, sceneY)
        painting = carrying = false
        pick = null
        swallowClick = was
        return was
    }
    function cancel(area) { release(area); swallowClick = false }
    // set by the window: drops what's carried on whatever takes it there
    property var dropAt: null

    // ---- painting -----------------------------------------------------------------------------------------
    function view() { return pick ? pick.view() : null }
    function indexAtScene(x, y) {
        var v = view()
        if (v) {
            var p = v.mapFromItem(null, x, y)
            p.y = Math.max(0, Math.min(v.height - 1, p.y)); p.x = Math.max(0, Math.min(v.width - 1, p.x))
            var c = v.mapToItem(v.contentItem, p.x, p.y)  // (a header or section labels offset the content)
            var i = v.indexAt(c.x, c.y)
            return i >= 0 ? i : -1
        }
        // a Repeater's items: the one under the pointer, or (between or past them) the nearest, of this list
        var name = pick.listName(), kind = pick.kind
        var best = null, bestD = 1e12
        _picks.forEach(function (cp, c) {
            if (!cp || cp.kind !== kind || !c.visible || cp.listName() !== name) return
            var q = c.mapFromItem(null, x, y)
            var dx = q.x < 0 ? -q.x : (q.x > c.width ? q.x - c.width : 0)
            var dy = q.y < 0 ? -q.y : (q.y > c.height ? q.y - c.height : 0)
            var d = dx * dx + dy * dy * 4
            if (d < bestD) { bestD = d; best = cp }
        })
        return best ? best.index : -1
    }
    function paintTo(x, y) {
        var i = indexAtScene(x, y)
        if (i < 0 || !pick) return
        Selection.selectRange(pick.listName(), pick.source, from, i, pick.kind, base, pick.origin)
        Selection.anchorList = pick.listName()
        Selection.anchor = from
    }

    // ---- scrolling along -------------------------------------------------------------------------------
    property Timer scroller: Timer {
        interval: 30; repeat: true
        running: drag.painting || drag.carrying
        onTriggered: {
            var f = drag.pick ? drag.pick.flickable() : null
            if (!f || !drag.painting) return
            var p = f.mapFromItem(null, drag.sceneX, drag.sceneY)
            var edge = 48
            var step = p.y < edge ? -Math.min(30, (edge - p.y) / 2 + 4) : (p.y > f.height - edge ? Math.min(30, (p.y - f.height + edge) / 2 + 4) : 0)
            if (!step) return
            var top = f.originY !== undefined ? f.originY : 0
            f.contentY = Math.max(top, Math.min(top + f.contentHeight - f.height, f.contentY + step))
            drag.paintTo(drag.sceneX, drag.sceneY)
        }
    }
}
