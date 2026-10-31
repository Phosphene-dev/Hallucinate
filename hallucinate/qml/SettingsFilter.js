.pragma library
// Settings search, row by row (#147): while searching, a section (or subsection) shows only the rows that match,
// not the whole card. A row that doesn't match moves to a hidden holder and comes back, in its place, when the
// search changes or clears. Moving rows (rather than setting `visible`) leaves their own visibility rules alone.
// A paragraph of explanation goes with the row above it: either matching shows both.

function words(query) {
    return String(query || "").trim().toLowerCase().split(/\s+/).filter(function (w) { return w.length > 0 })
}

function textOf(item) {
    var out = []
    if (item.text !== undefined && typeof item.text === "string") out.push(item.text)
    if (item.title !== undefined && typeof item.title === "string") out.push(item.title)
    var kids = item.children || []
    for (var i = 0; i < kids.length; i++) out = out.concat(textOf(kids[i]))
    return out
}

function matches(item, ws) {
    var hay = textOf(item).join(" ").toLowerCase()
    return ws.every(function (w) { return hay.indexOf(w) >= 0 })
}

// A paragraph of explanation rather than a control: plain wrapping text.
function isNote(item) {
    return item.wrapMode !== undefined && item.textFormat !== undefined && item.wrapMode !== 0 && !item.activeFocusOnTab
}

// Put every row back, in order. Returns null (no saved order).
function restore(body, holder, order) {
    if (!order) return null
    for (var i = 0; i < order.length; i++) order[i].parent = holder
    for (var j = 0; j < order.length; j++) order[j].parent = body
    return null
}

// The rows of `body` that match by their own text, not just by the explanation under them: the ones marked.
function hits(body, query) {
    var ws = words(query)
    if (!ws.length) return []
    return Array.prototype.slice.call(body.children).filter(function (r) { return !isNote(r) && matches(r, ws) })
}

// Show only the matching rows of `body`. Returns the saved row order (pass it back next time), or null when
// every row shows: no search, or nothing in here matches row by row (the section matched by its title or
// keywords as a whole).
function apply(body, holder, order, query) {
    var ws = words(query)
    order = restore(body, holder, order)
    if (!ws.length) return null
    var rows = Array.prototype.slice.call(body.children)
    var keep = rows.map(function (r) { return matches(r, ws) })
    var owner = [], last = -1
    for (var i = 0; i < rows.length; i++) {
        owner.push(isNote(rows[i]) ? last : -1)
        if (!isNote(rows[i])) last = i
    }
    for (var a = 0; a < rows.length; a++) if (keep[a] && owner[a] >= 0) keep[owner[a]] = true
    for (var b = 0; b < rows.length; b++) if (owner[b] >= 0 && keep[owner[b]]) keep[b] = true
    if (!keep.some(function (k) { return k })) return null
    for (var c = 0; c < rows.length; c++) rows[c].parent = holder
    for (var d = 0; d < rows.length; d++) if (keep[d]) rows[d].parent = body
    return rows
}
