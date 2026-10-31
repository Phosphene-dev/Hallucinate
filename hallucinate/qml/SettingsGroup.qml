import QtQuick
import "."
import "SettingsFilter.js" as Filter

// A subsection of settings that opens and closes: the options people rarely need, out of the way until
// wanted. It remembers whether you left it open, and opens by itself while the Settings search matches
// something inside it. Its controls always exist (closed, they're only hidden), so the search still sees them.
Column {
    id: group
    property string title: ""
    property string summary: ""  // a hint of what's inside, shown beside the title
    property string key: title   // remembered under this name
    property string query: ""
    default property alias content: inner.data
    property bool open: shell.uiValue("settingsOpen/" + key, "0") === "1"
    onOpenChanged: shell.setUiValue("settingsOpen/" + key, open ? "1" : "0")
    property string searchText: ""
    Component.onCompleted: searchText = collect(inner).join(" ").toLowerCase()
    function collect(item) {
        var out = []
        if (item.text !== undefined && typeof item.text === "string") out.push(item.text)
        var kids = item.children || []
        for (var i = 0; i < kids.length; i++) out = out.concat(collect(kids[i]))
        return out
    }
    // while searching: open if a searched word is in here
    readonly property bool found: {
        var q = query.trim().toLowerCase()
        if (!q.length) return false
        var hay = (title + " " + summary + " " + searchText).toLowerCase()
        return q.split(/\s+/).some(function (w) { return w.length > 1 && hay.indexOf(w) >= 0 })
    }
    readonly property bool shown: open || found
    // while searching, only the matching rows inside show (#147); the title matching shows them all
    property var _rows: null
    onQueryChanged: {
        var q = Filter.words(query).every(w => title.toLowerCase().indexOf(w) >= 0) ? "" : query
        _rows = Filter.apply(inner, hidden, _rows, q)
        hits = Filter.hits(inner, q)
    }
    property var hits: []  // the rows in here that match, marked by the section
    Item { id: hidden; visible: false; width: inner.width }
    width: parent ? parent.width : 400
    spacing: 12

    Rectangle {
        id: header
        objectName: "group_" + group.key
        width: parent.width
        height: 40
        radius: Theme.radiusSmall
        color: headerHover.hovered ? Theme.glassHover : "transparent"
        border.width: 1
        border.color: Theme.stroke
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: group.title + (group.shown ? ", open" : ", closed")
        Accessible.onPressAction: group.open = !group.open
        Keys.onSpacePressed: group.open = !group.open
        Keys.onReturnPressed: group.open = !group.open
        Icon {
            id: chevron
            x: 12; anchors.verticalCenter: parent.verticalCenter
            width: 12; height: 12
            name: group.shown ? "down" : "next"
            color: Theme.textDim
        }
        Text {
            id: headerText
            textFormat: Text.PlainText
            anchors { left: chevron.right; leftMargin: 10; right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
            text: group.title
            elide: Text.ElideRight
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(14)
            font.weight: Font.DemiBold
        }
        Text {
            textFormat: Text.PlainText
            visible: group.summary.length > 0 && !group.shown
            anchors { left: headerText.left; leftMargin: headerText.implicitWidth + 12; right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
            text: group.summary
            elide: Text.ElideRight
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(12)
        }
        Rectangle { anchors.fill: parent; anchors.margins: -2; radius: parent.radius + 2; color: "transparent"; border.width: 2; border.color: Theme.accent; visible: header.activeFocus }
        HoverHandler { id: headerHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: group.open = !group.open }
    }
    Column {
        id: inner
        visible: group.shown
        x: 14
        width: parent.width - 14
        spacing: 14
    }
}
