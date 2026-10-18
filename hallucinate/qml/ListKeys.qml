import QtQuick

// Keyboard moves for a row in a list: Up/Down, Page Up/Down, Home/End go to other rows, and the Menu key (or
// Shift+F10) opens the row's menu. In a ListView the rows are the view's; rows laid out by a Repeater (search
// results, an artist's or genre's songs) move among the rows of their kind beside them. While a row has the
// focus these keys are its own, not the window's shortcuts (Up and Down change the volume elsewhere), but only
// the ones it can act on: a row with nowhere to go leaves the arrows to the window.
QtObject {
    id: keys
    property Item row
    signal menu()

    function view() { return row && row.ListView.view ? row.ListView.view : null }
    // Rows of the same kind beside this one (a Repeater's), top to bottom; used when there's no ListView
    function siblings() {
        if (!row || !row.parent || view()) return []
        var out = []
        var kids = row.parent.children
        for (var i = 0; i < kids.length; i++)
            if (kids[i].objectName === row.objectName && kids[i].visible && kids[i].activeFocusOnTab) out.push(kids[i])
        return out.sort(function (a, b) { return a.y - b.y })
    }
    function count() { var v = view(); return v ? v.count : siblings().length }
    // The page (a Flickable) a Repeater's row scrolls in
    function flickOf(item) {
        for (var f = item ? item.parent : null; f; f = f.parent)
            if (f.contentY !== undefined && f.flickableDirection !== undefined) return f
        return null
    }
    // Scrolls that page so the row is in sight
    function reveal(item) {
        var f = flickOf(item)
        if (f) {
            var top = item.mapToItem(f.contentItem, 0, 0).y
            if (top < f.contentY) f.contentY = Math.max(0, top - 8)
            else if (top + item.height > f.contentY + f.height)
                f.contentY = Math.min(Math.max(0, f.contentHeight - f.height), top + item.height - f.height + 8)
        }
    }
    function go(index) {
        var v = view()
        if (v) {
            if (v.count === 0) return
            index = Math.max(0, Math.min(v.count - 1, index))
            v.currentIndex = index
            v.positionViewAtIndex(index, ListView.Contain)
            if (v.currentItem) v.currentItem.forceActiveFocus(Qt.TabFocusReason)
            return
        }
        var rows = siblings()
        if (!rows.length) return
        var target = rows[Math.max(0, Math.min(rows.length - 1, index))]
        reveal(target)
        target.forceActiveFocus(Qt.TabFocusReason)
    }
    function page() {
        var v = view()
        var f = v || flickOf(row)
        var h = f ? f.height : 500
        return Math.max(1, Math.floor(h / Math.max(1, row.height)))
    }
    function handles(event) {
        var plain = (event.modifiers & ~Qt.KeypadModifier) === Qt.NoModifier
        if (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier)) return true
        if (!plain) return false
        if (event.key === Qt.Key_Menu) return true
        // the moves, only with other rows to move to
        return [Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End].indexOf(event.key) >= 0
               && count() > 1
    }
    // index: the row's place in its ListView (a Repeater's row finds its own place among its siblings)
    function press(event, index) {
        if (!view()) index = siblings().indexOf(row)
        switch (event.key) {
        case Qt.Key_Up: go(index - 1); break
        case Qt.Key_Down: go(index + 1); break
        case Qt.Key_PageUp: go(index - page()); break
        case Qt.Key_PageDown: go(index + page()); break
        case Qt.Key_Home: go(0); break
        case Qt.Key_End: go(count() - 1); break
        default: keys.menu()
        }
        event.accepted = true
    }
}
