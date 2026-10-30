import QtQuick
import QtQuick.Controls
import "."

// A colour of your own (#129): a saturation/brightness square, a hue strip, red/green/blue and hex fields,
// and the last few colours you made. It shows the colour live (`picked` on every change) and goes back to the
// one you started from on Cancel or Esc.
//     ColorPicker { id: picker; onPicked: (c) => apply(c); onDone: (c) => keep(c) }   picker.openWith("#8f7bff")
Popup {
    id: cp
    objectName: "colorPicker"
    signal picked(string color)   // while choosing
    signal done(string color)     // Use: keep it ("" on Cancel, with the starting colour picked again)
    property string start: ""
    property real hue: 0
    property real sat: 1
    property real val: 1
    readonly property color current: Qt.hsva(hue, sat, val, 1)
    function hexOf(c) { return "#" + [c.r, c.g, c.b].map(function (x) { return ("0" + Math.round(x * 255).toString(16)).slice(-2) }).join("") }
    readonly property string hex: hexOf(current)
    readonly property var recent: (shell.ui.recentAccents || "").split(",").filter(function (c) { return /^#[0-9a-f]{6}$/i.test(c) })

    function setColor(c) {
        if (typeof c === "string" && !/^#([0-9a-f]{6}|[0-9a-f]{3})$/i.test(c.trim())) return false
        var q = Qt.lighter(c, 1)  // (a colour from a string or a colour)
        if (q.hsvSaturation > 0.001) hue = Math.max(0, q.hsvHue)  // (grey has no hue: keep the one there)
        sat = q.hsvSaturation
        val = q.hsvValue
        return true
    }
    function openWith(c) {
        start = c
        if (!c || !setColor(c)) setColor(Theme.accent)
        open()
    }
    onCurrentChanged: if (opened) picked(hexOf(current))  // (not `hex`: its binding may not have caught up yet)
    function use() {
        usedOrCancelled = true
        var list = [hex].concat(recent.filter(function (c) { return c.toLowerCase() !== hex })).slice(0, 8)
        shell.setUiValue("recentAccents", list.join(","))
        done(hex)
        close()
    }
    function cancel() { usedOrCancelled = true; picked(start); done(""); close() }
    onClosed: if (!usedOrCancelled) cancel()
    onOpened: usedOrCancelled = false
    property bool usedOrCancelled: false

    modal: true
    focus: true
    padding: 18
    width: 320
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: Rectangle { radius: Theme.round(16); color: Theme.popup; border.width: 1; border.color: Theme.border; Bevel {} }

    contentItem: Column {
        spacing: 12
        Text {
            textFormat: Text.PlainText
            text: "Your own accent colour"
            color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
        }
        // saturation (across) and brightness (up)
        Rectangle {
            id: square
            objectName: "colorSquare"
            width: 284; height: 170
            radius: Theme.round(8)
            color: Qt.hsva(cp.hue, 1, 1, 1)
            Rectangle {
                anchors.fill: parent; radius: parent.radius
                gradient: Gradient { orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "white" } GradientStop { position: 1; color: "transparent" } }
            }
            Rectangle {
                anchors.fill: parent; radius: parent.radius
                gradient: Gradient {
                    GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: "black" } }
            }
            Rectangle {  // where you are
                x: cp.sat * square.width - width / 2; y: (1 - cp.val) * square.height - height / 2
                width: 16; height: 16; radius: 8
                color: cp.current; border.width: 2; border.color: "white"
                Rectangle { anchors.fill: parent; anchors.margins: -1; radius: width / 2; color: "transparent"; border.color: "#80000000" }
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.CrossCursor
                preventStealing: true
                function at(m) { cp.sat = Math.max(0, Math.min(1, m.x / width)); cp.val = Math.max(0, Math.min(1, 1 - m.y / height)) }
                onPressed: function (m) { at(m) }
                onPositionChanged: function (m) { if (pressed) at(m) }
            }
            Accessible.role: Accessible.Slider
            Accessible.name: "Saturation and brightness"
        }
        // hue
        Rectangle {
            id: hueBar
            objectName: "colorHue"
            width: 284; height: 16; radius: 8
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0.000; color: "#ff0000" } GradientStop { position: 0.167; color: "#ffff00" }
                GradientStop { position: 0.333; color: "#00ff00" } GradientStop { position: 0.500; color: "#00ffff" }
                GradientStop { position: 0.667; color: "#0000ff" } GradientStop { position: 0.833; color: "#ff00ff" }
                GradientStop { position: 1.000; color: "#ff0000" } }
            Rectangle {
                x: cp.hue * hueBar.width - width / 2; anchors.verticalCenter: parent.verticalCenter
                width: 10; height: 22; radius: 5
                color: Qt.hsva(cp.hue, 1, 1, 1); border.width: 2; border.color: "white"
            }
            MouseArea {
                anchors.fill: parent; anchors.margins: -6
                preventStealing: true
                function at(m) { cp.hue = Math.max(0, Math.min(0.9999, (m.x - 6) / hueBar.width)) }
                onPressed: function (m) { at(m) }
                onPositionChanged: function (m) { if (pressed) at(m) }
                onWheel: function (w) { cp.hue = (cp.hue + (w.angleDelta.y > 0 ? 0.01 : 0.99)) % 1 }
            }
            Accessible.role: Accessible.Slider
            Accessible.name: "Hue"
        }
        // red, green, blue and hex
        Row {
            spacing: 8
            Repeater {
                model: [{ n: "R", k: "r" }, { n: "G", k: "g" }, { n: "B", k: "b" }]
                Column {
                    required property var modelData
                    spacing: 2
                    Text { textFormat: Text.PlainText; text: modelData.n; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11) }
                    TextField {
                        objectName: "color" + modelData.n
                        width: 56; height: 30
                        text: String(Math.round(cp.current[modelData.k] * 255))
                        validator: IntValidator { bottom: 0; top: 255 }
                        selectByMouse: true
                        horizontalAlignment: TextInput.AlignHCenter
                        Accessible.name: { return { R: "Red", G: "Green", B: "Blue" }[modelData.n] + ", 0 to 255" }
                        onEditingFinished: {
                            var c = cp.current, v = Math.max(0, Math.min(255, parseInt(text) || 0)) / 255
                            var rgb = { r: c.r, g: c.g, b: c.b }
                            rgb[modelData.k] = v
                            cp.setColor(Qt.rgba(rgb.r, rgb.g, rgb.b, 1))
                        }
                    }
                }
            }
            Column {
                spacing: 2
                Text { textFormat: Text.PlainText; text: "Hex"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11) }
                TextField {
                    objectName: "colorHex"
                    width: 92; height: 30
                    text: cp.hex
                    selectByMouse: true
                    Accessible.name: "Hex code"
                    onEditingFinished: cp.setColor(text.trim().charAt(0) === "#" ? text.trim() : "#" + text.trim())
                }
            }
        }
        // the last colours you made
        Flow {
            visible: cp.recent.length > 0
            width: 284
            spacing: 6
            Repeater {
                model: cp.recent
                Rectangle {
                    required property string modelData
                    width: 24; height: 24; radius: Theme.round(12)
                    color: modelData
                    border.width: 1; border.color: Theme.border
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: cp.setColor(modelData) }
                    Accessible.role: Accessible.Button
                    Accessible.name: "Recent colour " + modelData
                    Accessible.onPressAction: cp.setColor(modelData)
                }
            }
        }
        Row {
            spacing: 8
            layoutDirection: Qt.RightToLeft
            width: 284
            PillButton { objectName: "colorUse"; primary: true; text: "Use"; onClicked: cp.use() }
            PillButton { text: "Cancel"; onClicked: cp.cancel() }
        }
    }
}
