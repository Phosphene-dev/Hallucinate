import QtQuick

// A click area over some text that makes it a link: a pointing cursor, and a screen reader announces it (by the
// text it covers, unless `name` says otherwise) and can follow it.
MouseArea {
    id: area
    property string name: parent && typeof parent.text === "string" ? parent.text : ""
    anchors.fill: parent
    cursorShape: Qt.PointingHandCursor
    Accessible.role: Accessible.Link
    Accessible.name: name
    Accessible.onPressAction: if (enabled) area.clicked(null)
}
