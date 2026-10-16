import QtQuick
import QtQuick.Controls
import "."

// When you listen: a heatmap of the last 26 weeks (columns are weeks, rows Monday to Sunday), your current
// streak, and this month's most played artists. Click a day to open it in History.
GlassPanel {
    id: card
    objectName: "listeningCard"
    readonly property var heat: userLib.home.heatmap || ({})
    readonly property var artists: userLib.home.topArtists || []
    implicitHeight: 248

    Column {
        anchors { fill: parent; margins: 22 }
        spacing: 12
        Row {
            width: parent.width
            Text {
                textFormat: Text.PlainText
                width: parent.width - streak.width
                text: "Listening"
                color: Theme.text
                font.family: Theme.displayFamily
                font.pixelSize: Theme.fontSize(16)
                font.weight: Font.DemiBold
                LinkArea { name: "Listening history"; onClicked: Nav.openHistory("") }
            }
            Text {
                textFormat: Text.PlainText
                id: streak
                text: (card.heat.streak || 0) > 1 ? card.heat.streak + "-day streak"
                    : (card.heat.activeDays || 0) + ((card.heat.activeDays || 0) === 1 ? " active day" : " active days")
                color: Theme.accent
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
                font.weight: Font.DemiBold
            }
        }
        Heatmap {
            id: grid
            objectName: "homeHeatmap"
            width: parent.width
            heat: card.heat
            onDayClicked: day => Nav.openHistory(day)
        }
        Text {
            textFormat: Text.PlainText
            text: card.artists.length ? "Top artists this month" : "Play some music and your listening shows up here."
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(12)
        }
        Row {
            id: topArtists
            objectName: "topArtists"
            width: parent.width
            spacing: 14
            clip: true
            // as many as fit at about 96 px each (up to five), sharing the width so none spills past the card
            readonly property int shown: Math.max(1, Math.min(5, card.artists.length, Math.floor((width + spacing) / (96 + spacing))))
            readonly property real slot: (width - spacing * (shown - 1)) / shown
            Repeater {
                model: card.artists.slice(0, topArtists.shown)
                Row {
                    required property var modelData
                    spacing: 8
                    Cover {
                        width: 28; height: 28; radius: 14
                        source: modelData.artUrl || ""
                        fallback: (modelData.name || "?").charAt(0)
                    }
                    Text {
                        textFormat: Text.PlainText
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.name
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSize(13)
                        width: Math.max(0, Math.min(implicitWidth, 110, topArtists.slot - 36))
                        elide: Text.ElideRight
                        LinkArea {
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onPressAndHold: Nav.artistMenu(modelData.name)
                            onClicked: function (mouse) { mouse && mouse.button === Qt.RightButton ? Nav.artistMenu(modelData.name) : Nav.openArtist(modelData.name) }
                        }
                    }
                }
            }
        }
    }
}
