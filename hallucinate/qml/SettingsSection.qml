import QtQuick
import "."

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
