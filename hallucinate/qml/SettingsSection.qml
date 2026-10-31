import QtQuick
import "."
import "SettingsFilter.js" as Filter

// One group of settings in a card. It hides itself when the Settings search matches nothing in it: its title,
// its keywords or any text of its controls.
Rectangle {
    id: section
    property string title: ""
    property string keywords: ""
    property string query: ""
    default property alias content: body.data
    property string searchText: ""

    readonly property bool matches: {
        var q = query.trim().toLowerCase()
        if (!q.length) return true
        var hay = (title + " " + keywords + " " + searchText).toLowerCase()
        return q.split(/\s+/).every(function (w) { return hay.indexOf(w) >= 0 })
    }
    visible: matches
    width: parent ? parent.width : 600
    height: visible ? body.implicitHeight + 64 : 0
    radius: Theme.round(22)
    color: Theme.glass
    border.width: 1
    border.color: Theme.stroke

    function collect(item) {
        var out = []
        if (item.text !== undefined && typeof item.text === "string") out.push(item.text)
        var kids = item.children || []
        for (var i = 0; i < kids.length; i++) out = out.concat(collect(kids[i]))
        return out
    }
    Component.onCompleted: searchText = collect(body).join(" ")
    // while searching, only the matching rows show (#147); the section's own name shows all of it
    property var _rows: null
    property string _rowQuery: ""
    onQueryChanged: {
        _rowQuery = Filter.words(query).every(w => title.toLowerCase().indexOf(w) >= 0) ? "" : query
        _rows = Filter.apply(body, hidden, _rows, _rowQuery)
        Qt.callLater(section.mark)  // after its subsections have filtered themselves
    }
    Item { id: hidden; visible: false; width: body.width }

    // the matching settings, each with a bar beside it; a subsection lends its own matching rows (or itself)
    property var marked: []
    function mark() {
        var own = Filter.hits(body, _rowQuery), out = []
        var rows = body.children
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i]
            if (r.found !== undefined) { if (r.hits.length) out = out.concat(r.hits); else if (own.indexOf(r) >= 0) out.push(r) }
            else if (own.indexOf(r) >= 0) out.push(r)
        }
        marked = out
    }
    function firstMatch() { return marked.length ? marked[0] : null }
    Repeater {
        model: section.marked
        Rectangle {
            required property var modelData
            objectName: "settingsMatchMark"
            x: 10; width: 3; radius: 1.5
            color: Theme.accent
            // (re-read as the section lays out: its height changes with every row that moves)
            y: { section.height; return modelData.mapToItem(section, 0, 0).y }
            height: modelData.height
        }
    }

    Text {
        textFormat: Text.PlainText
        id: heading
        x: 24; y: 18
        text: section.title
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: (Theme.fontSize(18)) * Theme.displayScale
        font.weight: Font.DemiBold
    }
    Column {
        id: body
        x: 24
        anchors.top: heading.bottom
        anchors.topMargin: 14
        width: section.width - 48
        spacing: 14
    }
}
