import QtQuick
import "."

// Your listening to stations or shows over a week, a month or all time: hours, a count, and where the time went.
// Kept apart from the music's stats. `source` is stations or podcasts (both have listening(days)).
Column {
    id: strip
    property var source
    property string countKey: "songs"        // "songs" (heard on the radio) or "finished" (episodes)
    property string countOne: "song heard"
    property string countMany: "songs heard"
    property int days: 7
    property var info: ({ hours: 0, top: [] })
    property int revision: 0
    signal openItem(int id)
    spacing: 10
    function refresh() { if (source) info = source.listening(days) }
    onDaysChanged: refresh()
    onRevisionChanged: refresh()
    Component.onCompleted: refresh()
    Connections {
        target: strip.source
        ignoreUnknownSignals: true
        function onListeningChanged() { strip.refresh() }
        function onLogChanged() { strip.refresh() }
    }

    Row {
        spacing: 6
        Repeater {
            model: [[7, "This week"], [30, "This month"], [0, "All time"]]
            Chip {
                required property var modelData
                text: modelData[1]
                selected: strip.days === modelData[0]
                onClicked: strip.days = modelData[0]
            }
        }
    }
    Flow {
        width: parent.width
        spacing: 22
        Column {
            spacing: 2
            Text {
                textFormat: Text.PlainText
                text: strip.info.hours < 1 && strip.info.hours > 0 ? "under an hour"
                      : strip.info.hours === 1 ? "1 hour" : Theme.num(strip.info.hours) + " hours"
                color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(20)) * Theme.displayScale; font.weight: Font.DemiBold
            }
            Text {
                textFormat: Text.PlainText
                text: "listened"
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
        Column {
            spacing: 2
            Text {
                textFormat: Text.PlainText
                text: String(strip.info[strip.countKey] || 0)
                color: Theme.text; font.family: Theme.displayFamily; font.pixelSize: (Theme.fontSize(20)) * Theme.displayScale; font.weight: Font.DemiBold
            }
            Text {
                textFormat: Text.PlainText
                text: (strip.info[strip.countKey] || 0) === 1 ? strip.countOne : strip.countMany
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
        }
        Repeater {
            model: strip.info.top || []
            Column {
                required property var modelData
                required property int index
                spacing: 2
                Text {
                    textFormat: Text.PlainText
                    width: Math.min(implicitWidth, 220)
                    elide: Text.ElideRight
                    text: (index + 1) + ". " + modelData.name
                    color: topMouse.containsMouse ? Theme.accentHi : Theme.text
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
                    LinkArea { id: topMouse; name: modelData.name; hoverEnabled: true; onClicked: strip.openItem(modelData.id) }
                }
                Text {
                    textFormat: Text.PlainText
                    text: modelData.hours < 0.1 ? "a few minutes" : modelData.hours + " h"
                    color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
                }
            }
        }
    }
}
