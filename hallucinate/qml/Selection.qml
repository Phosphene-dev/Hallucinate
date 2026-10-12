pragma Singleton
import QtQuick

// The songs selected in a list (Ctrl+click toggles, Shift+click extends from the last click). Selecting in another
// list starts over; a plain click, Esc or leaving the page clears it. The selection bar acts on `paths`.
QtObject {
    id: sel
    property var paths: []
    property var source: null      // the list (a model with get(i), or an array of tracks) the selection is in
    property int anchor: -1
    readonly property int count: paths.length

    function has(path) { return paths.indexOf(path) >= 0 }
    function clear() { if (paths.length || source) { paths = []; source = null; anchor = -1 } }

    function pathAt(src, i) {
        if (!src || i < 0) return ""
        var t = Array.isArray(src) ? src[i] : (src.get ? src.get(i) : null)
        return t && t.path ? t.path : ""
    }
    function lengthOf(src) {
        if (!src) return 0
        return Array.isArray(src) ? src.length : (src.count !== undefined ? src.count : 0)
    }

    function toggle(src, index, path) {
        var list = src === source ? paths.slice() : []
        var at = list.indexOf(path)
        if (at >= 0) list.splice(at, 1)
        else list.push(path)
        source = list.length ? src : null
        anchor = list.length ? index : -1
        paths = list
    }

    function extend(src, index, path) {
        if (src !== source || anchor < 0 || !src) {
            toggle(src, index, path)
            return
        }
        var list = paths.slice()
        var lo = Math.min(anchor, index), hi = Math.max(anchor, index)
        for (var i = lo; i <= hi && i < lengthOf(src); i++) {
            var p = pathAt(src, i)
            if (p && list.indexOf(p) < 0) list.push(p)
        }
        paths = list
    }

    function selectAll(src) {
        var list = []
        for (var i = 0; i < lengthOf(src); i++) {
            var p = pathAt(src, i)
            if (p && list.indexOf(p) < 0) list.push(p)
        }
        source = list.length ? src : null
        anchor = list.length ? 0 : -1
        paths = list
    }
}
