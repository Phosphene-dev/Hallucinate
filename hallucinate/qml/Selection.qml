pragma Singleton
import QtQuick

// What's selected, anywhere in the app: songs, albums, artists, genres, composers, folders, history entries and
// playlists (all of them music: the selection bar acts on their songs), or queue entries, podcast episodes or radio
// stations (each a kind of its own, with their own actions). A selection stays while you browse, so songs from
// several pages can be gathered and acted on at once; it ends when the bar acts on it, or with Esc or ✕.
//
// Ctrl+click toggles an item, Shift+click selects from the last one clicked in the same list, dragging across a
// list paints a range, Ctrl+A selects a whole list. A list is named by a string (`list`): the same list read twice
// is often a new array, so lists are told apart by name, not by the object they come from.
QtObject {
    id: sel

    // [{kind, key, title, path}] in the order they were selected. `path`: a song's file, where the item is one song
    property var items: []
    readonly property int count: items.length
    // "music", "queue", "episode" or "station": what the selection bar offers
    readonly property string domain: count ? domainOf(items[0].kind) : ""
    // The songs selected as songs (their rows show it); the selection's every song is songPaths()
    readonly property var paths: _paths
    property var _paths: []
    property var _index: ({})   // "kind\u0001key" → true
    // Where Shift+click extends from: the list and the index last clicked in it
    property string anchorList: ""
    property int anchor: -1
    // What a song selection came from, when every song is from one playlist (so "Remove from this playlist")
    property string origin: ""

    signal changed()

    readonly property var musicKinds: ["song", "album", "artist", "genre", "composer", "folder", "history", "playlist", "smart", "liked"]
    function domainOf(kind) { return musicKinds.indexOf(kind) >= 0 ? "music" : kind }
    function id(kind, key) { return kind + "\u0001" + key }
    function has(kind, key) {
        if (key === undefined) { key = kind; kind = "song" }  // has(path): a song
        return count > 0 && _index[id(kind, key)] === true
    }
    function countOf(kind) {
        var n = 0
        for (var i = 0; i < items.length; i++) if (items[i].kind === kind) n++
        return n
    }

    function _set(list) {
        var index = {}, songs = []
        for (var i = 0; i < list.length; i++) {
            index[id(list[i].kind, list[i].key)] = true
            if (list[i].kind === "song") songs.push(list[i].key)
        }
        _index = index
        _paths = songs
        items = list
        if (!list.length) { anchorList = ""; anchor = -1; origin = "" }
        changed()
    }
    function clear() { if (items.length || anchorList.length) _set([]) }
    // A copy to put back (the bar's Undo)
    function snapshot() { return { items: items.slice(), origin: origin } }
    function restore(s) { if (s) { origin = s.origin || ""; _set(s.items.slice()) } }

    // The selection's every song (albums, artists, playlists… as all their songs), in order and once each
    function songPaths() { return domain === "music" || domain === "queue" ? userLib.selectionPaths(items) : [] }

    // ---- the items of a list -------------------------------------------------------------------------------
    function lengthOf(src) {
        if (!src) return 0
        return Array.isArray(src) ? src.length : (src.count !== undefined ? src.count : (src.length || 0))
    }
    function rawAt(src, i) {
        if (!src || i < 0) return null
        return Array.isArray(src) ? src[i] : (src.get ? src.get(i) : null)
    }
    // An item of `kind` from a list's entry (a track, an album, an artist…)
    function itemOf(kind, e) {
        if (!e) return null
        switch (kind) {
        case "song": return e.path ? { kind: kind, key: e.path, title: e.title || "", path: e.path } : null
        case "album": return e.album_key ? { kind: kind, key: e.album_key, title: e.album || "" } : null
        case "artist": case "genre": case "composer":
            var name = e.name || e[kind] || ""
            return name ? { kind: kind, key: name, title: name } : null
        case "folder": return e.path ? { kind: kind, key: e.path, title: e.name || e.path } : null
        case "history": return e.id !== undefined ? { kind: kind, key: String(e.id), title: e.title || "", path: e.path } : null
        case "playlist": case "smart": return e.id !== undefined ? { kind: kind, key: String(e.id), title: e.name || "" } : null
        case "queue": return { kind: kind, key: String(e.index !== undefined ? e.index : -1), title: e.title || "", path: e.path }
        case "episode": return e.id !== undefined ? { kind: kind, key: String(e.id), title: e.title || "" } : null
        case "station": return (e.id !== undefined || e.url) ? { kind: kind, key: String(e.id !== undefined ? e.id : e.url), title: e.name || "" } : null
        }
        return null
    }
    function itemAt(kind, src, i) {
        var e = rawAt(src, i)
        if (kind === "queue" && e) e = { index: i, title: e.title, path: e.path }
        return itemOf(kind, e)
    }

    // ---- choosing ----------------------------------------------------------------------------------------
    // Starts over when the new item is a different domain (songs and queue entries don't act together)
    function _base(kind) {
        return count && domainOf(kind) !== domain ? [] : items.slice()
    }
    function _note(list, origin_) {
        // a song selection made in one playlist can be taken out of it; anything else can't
        if (!items.length || origin === origin_) origin = origin_ || ""
        else origin = ""
        return list
    }

    // Ctrl+click: in or out. `item` from itemOf()/itemAt(); `list` names the list it's in, `index` its place there
    function toggle(list, index, item, origin_) {
        if (!item) return
        var next = _base(item.kind)
        var k = id(item.kind, item.key), at = -1
        for (var i = 0; i < next.length; i++) if (id(next[i].kind, next[i].key) === k) { at = i; break }
        if (at >= 0) next.splice(at, 1)
        else next.push(item)
        _note(next, origin_)
        anchorList = list || ""
        anchor = index
        _set(next)
    }
    // Shift+click: everything from the last item clicked in this list to this one
    function extend(list, src, index, kind, origin_) {
        if (!list || list !== anchorList || anchor < 0 || !src) {
            toggle(list, index, itemAt(kind, src, index), origin_)
            return
        }
        selectRange(list, src, anchor, index, kind, items, origin_)  // (the anchor stays where it was)
    }
    // A range of a list, on top of `base` (what was selected when a drag began)
    function selectRange(list, src, from, to, kind, base, origin_) {
        var next = base && base.length && domainOf(kind) === domainOf(base[0].kind) ? base.slice() : []
        var seen = {}
        for (var i = 0; i < next.length; i++) seen[id(next[i].kind, next[i].key)] = true
        var lo = Math.max(0, Math.min(from, to)), hi = Math.min(lengthOf(src) - 1, Math.max(from, to))
        for (var j = lo; j <= hi; j++) {
            var it = itemAt(kind, src, j)
            if (it && !seen[id(it.kind, it.key)]) { seen[id(it.kind, it.key)] = true; next.push(it) }
        }
        _note(next, origin_)
        _set(next)
    }
    // Ctrl+A: the whole list (on top of what's already selected)
    function selectAll(list, src, kind, origin_) {
        selectRange(list, src, 0, lengthOf(src) - 1, kind, _base(kind), origin_)
        anchorList = list || ""
        anchor = 0
    }
    // Drop one entry (an item that's gone: a deleted playlist, a queue that changed)
    function dropKind(kind) {
        if (!countOf(kind)) return
        _set(items.filter(function (i) { return i.kind !== kind }))
    }

    // How it reads: "3 albums, 12 songs"
    readonly property var nouns: ({ song: ["song", "songs"], album: ["album", "albums"], artist: ["artist", "artists"],
                                     genre: ["genre", "genres"], composer: ["composer", "composers"],
                                     folder: ["folder", "folders"], history: ["play", "plays"],
                                     playlist: ["playlist", "playlists"], smart: [qsTr("smart playlist"), qsTr("smart playlists")],
                                     liked: [qsTr("Liked Songs"), qsTr("Liked Songs")], queue: [qsTr("song in the queue"), qsTr("songs in the queue")],
                                     episode: ["episode", "episodes"], station: ["station", "stations"] })
    function summary(tight) {
        if (!count) return ""
        var order = ["album", "artist", "genre", "composer", "folder", "playlist", "smart", "liked", "song", "history", "queue", "episode", "station"]
        var parts = []
        for (var i = 0; i < order.length; i++) {
            var n = countOf(order[i])
            if (n) parts.push(n + " " + nouns[order[i]][n === 1 ? 0 : 1])
        }
        if (tight && parts.length > 1) return Theme.num(count) + " items"
        return parts.join(", ")
    }
}
