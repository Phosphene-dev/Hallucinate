import QtQuick
import "."

// Makes an item selectable (see Selection): put one in a list's delegate, hand it the delegate (`target`), what it
// is (`kind`, `entry`: the track, album, artist… it shows) and where (`source`: the list's model or array, `index`).
// The delegate's mouse area then calls press/move/release/click, and its keys keys(). A click with Ctrl or Shift,
// or one ending a drag, selects instead of acting: click() says so.
QtObject {
    id: pick
    property Item target
    property string kind: "song"
    property var entry: null
    property var source: null
    property int index: -1
    property string list: ""      // a name for the list (default: the view or column holding the target)
    property string origin: ""    // see Selection.origin
    property bool carries: Selection.domainOf(kind) === "music"  // a drag from a selected item carries the selection

    readonly property var item: Selection.itemOf(kind, entry)
    readonly property string key: item ? item.key : ""
    readonly property bool selected: key.length > 0 && Selection.count > 0 && Selection._index[Selection.id(kind, key)] === true

    // The ListView/GridView the target is a delegate of, if any
    function view() {
        for (var a = target; a; a = a.parent) {
            var v = a.parent ? a.parent.parent : null
            if (v && typeof v.indexAt === "function" && v.contentItem === a.parent) return v
        }
        return null
    }
    // What scrolls: the view, or the page (a Flickable) the target's column is in
    function flickable() {
        var v = view()
        if (v) return v
        for (var f = target ? target.parent : null; f; f = f.parent)
            if (f.contentY !== undefined && f.flickableDirection !== undefined) return f
        return null
    }
    function listName() {
        if (list.length) return list
        var v = view()
        return v ? v.toString() : (target && target.parent ? target.parent.toString() : "")
    }

    // A click: true when it selected (Ctrl or Shift held, or a drag just ended) and the item shouldn't also act
    function click(mouse) {
        if (PickDrag.swallowClick) { PickDrag.swallowClick = false; return true }
        if (!mouse || mouse.button !== Qt.LeftButton || !item) return false
        if (mouse.modifiers & Qt.ControlModifier) { Selection.toggle(listName(), index, item, origin); return true }
        if (mouse.modifiers & Qt.ShiftModifier) {
            if (source) Selection.extend(listName(), source, index, kind, origin)
            else Selection.toggle(listName(), index, item, origin)
            return true
        }
        return false
    }
    function toggle() { if (item) Selection.toggle(listName(), index, item, origin) }
    function press(area, mouse) { PickDrag.press(pick, area, mouse) }
    function move(area, mouse) { PickDrag.move(area, mouse) }
    function release(area) { return PickDrag.release(area) }
    function cancel(area) { PickDrag.cancel(area) }

    // Ctrl+A (the whole list), Ctrl+Space (this one) and Shift+arrows (extend while moving): true when handled
    function keys(event, moveBy) {
        var ctrl = (event.modifiers & Qt.ControlModifier) !== 0
        if (ctrl && event.key === Qt.Key_A && source) { Selection.selectAll(listName(), source, kind, origin); event.accepted = true; return true }
        if (ctrl && event.key === Qt.Key_Space) { toggle(); event.accepted = true; return true }
        return false
    }

    Component.onCompleted: PickDrag.register(target, pick)
    Component.onDestruction: PickDrag.unregister(target, pick)
    onTargetChanged: PickDrag.register(target, pick)
}
