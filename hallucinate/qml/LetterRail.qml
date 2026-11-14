import QtQuick
import "."

// The A–Z rail beside a long list kept in alphabetical order (Albums, Artists, Songs, Genres): click or drag
// along it to jump to a letter, which shows large while you do. Only the letters the list has are on it.
// Settings → Appearance can switch it off. The page leaves it a gutter of its own (`shown` and `width`), so it
// never covers a row's buttons.
//     LetterRail { view: list; model: library.songs; field: "title"; active: library.songSort === "title" }
Item {
    id: rail
    objectName: "letterRail"
    property var view: null       // the ListView or GridView it moves
    property var model: null      // a DictModel (see letterIndex)
    property string field: ""     // what the list is in A–Z order of
    property bool active: true    // the list is in A–Z order now
    property var marks: []        // [{letter, row}]
    readonly property bool shown: active && shell.ui.letterRail !== "0" && marks.length > 2  // i18n: keep
                                  && view !== null && view.contentHeight > view.height * 3
    property string current: ""
    width: 22
    visible: shown

    function refresh() { marks = rail.model && rail.model.letterIndex ? rail.model.letterIndex(rail.field) : [] }
    onModelChanged: later.restart()
    onFieldChanged: later.restart()
    onActiveChanged: if (active) later.restart()
    Component.onCompleted: later.restart()
    // (the list fills in as a scan goes: read again once it settles, not on every song added)
    Timer { id: later; interval: 250; onTriggered: if (rail.active) rail.refresh() }
    Connections {
        target: rail.model
        ignoreUnknownSignals: true
        function onCountChanged() { later.restart() }
        function onModelReset() { later.restart() }
    }

    function jumpAt(y) {
        if (!marks.length || !view) return
        var i = Math.max(0, Math.min(marks.length - 1, Math.floor(y / (height / marks.length))))
        current = marks[i].letter
        view.positionViewAtIndex(marks[i].row, 0)  // (ListView.Beginning and GridView.Beginning: the top)
    }

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: Theme.glassHover
        opacity: railMouse.containsMouse || railMouse.pressed ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }
    Column {
        anchors.fill: parent
        Repeater {
            model: rail.marks
            Text {
                required property var modelData
                required property int index
                width: rail.width
                height: rail.height / Math.max(1, rail.marks.length)
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: modelData.letter
                // a long list of letters in a short window: every other one shown, all still reachable
                visible: rail.height / rail.marks.length >= 11 || index % 2 === 0
                color: rail.current === modelData.letter && railMouse.pressed ? Theme.accent : Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Math.max(8, Math.min(Theme.fontSize(11), rail.height / Math.max(1, rail.marks.length) - 1))
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
        }
    }
    MouseArea {
        id: railMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        preventStealing: true
        onPressed: function (mouse) { rail.jumpAt(mouse.y) }
        onPositionChanged: function (mouse) { if (pressed) rail.jumpAt(mouse.y) }
        Accessible.role: Accessible.ScrollBar
        Accessible.name: qsTr("Jump to a letter")
    }
    // the letter being jumped to, large beside the rail
    Rectangle {
        visible: railMouse.pressed && rail.current.length > 0
        width: 54; height: 54; radius: 14
        x: -width - 12
        y: Math.max(0, Math.min(rail.height - height, railMouse.mouseY - height / 2))
        color: Theme.surface
        border.width: 1
        border.color: Theme.accent
        Text {
            anchors.centerIn: parent
            text: rail.current
            color: Theme.accent
            font.family: Theme.displayFamily
            font.pixelSize: 28
            font.weight: Font.Bold
            textFormat: Text.PlainText
        }
    }
}
