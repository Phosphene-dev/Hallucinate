import QtQuick
import "."

// Genres as links, "IDM, Drill and Bass, Electronic": each opens that genre's page.
Flow {
    id: links
    property var names: []
    property bool composers: false  // composers' names: each opens the composer's page
    property int pixelSize: Theme.fontSize(14)
    property color color: Theme.text
    signal picked(string name)  // a genre was clicked (its page opens next)
    spacing: 0
    Repeater {
        model: links.names
        Text {
            required property string modelData
            required property int index
            textFormat: Text.PlainText
            text: modelData + (index < links.names.length - 1 ? ", " : "")
            color: genreMouse.containsMouse ? Theme.accent : links.color
            font.family: Theme.fontFamily
            font.pixelSize: links.pixelSize
            font.underline: genreMouse.containsMouse
            LinkArea {
                id: genreMouse
                objectName: (links.composers ? qsTr("composerLink_") : qsTr("genreLink_")) + parent.modelData
                name: (links.composers ? qsTr("Composer: ") : qsTr("Genre: ")) + parent.modelData
                hoverEnabled: true
                onClicked: {
                    links.picked(parent.modelData)
                    if (links.composers) Nav.openComposer(parent.modelData); else Nav.openGenre(parent.modelData)
                }
            }
        }
    }
}
