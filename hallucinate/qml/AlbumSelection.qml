pragma Singleton
import QtQuick

// The albums selected in a grid (Ctrl+click toggles, Shift+click extends from the last click), like Selection does
// for songs. Selecting in another grid starts over; a plain click, Esc or leaving the page clears it.
QtObject {
    property var keys: []
    property var source: null      // the grid's model (with get(i)) or an array of albums
    property int anchor: -1
    readonly property int count: keys.length

    function has(key) { return keys.indexOf(key) >= 0 }
    function clear() { if (keys.length || source) { keys = []; source = null; anchor = -1 } }

    function keyAt(src, i) {
        if (!src || i < 0) return ""
        var a = Array.isArray(src) ? src[i] : (src.get ? src.get(i) : null)
        return a && a.album_key ? a.album_key : ""
    }
    function lengthOf(src) {
        if (!src) return 0
        return Array.isArray(src) ? src.length : (src.count !== undefined ? src.count : 0)
    }

    function toggle(src, index, key) {
        var list = src === source ? keys.slice() : []
        var at = list.indexOf(key)
        if (at >= 0) list.splice(at, 1)
        else list.push(key)
        source = list.length ? src : null
        anchor = list.length ? index : -1
        keys = list
    }

    function extend(src, index, key) {
        if (src !== source || anchor < 0 || !src) {
            toggle(src, index, key)
            return
        }
        var list = keys.slice()
        var lo = Math.min(anchor, index), hi = Math.max(anchor, index)
        for (var i = lo; i <= hi && i < lengthOf(src); i++) {
            var k = keyAt(src, i)
            if (k && list.indexOf(k) < 0) list.push(k)
        }
        keys = list
    }
}
