import QtQuick
import "."

// A labelled dropdown for a setting with a few fixed values: `values` are what's stored, `labels` what's shown.
Row {
    id: opt
    property string label
    property var values: []
    property var labels: []
    property var current
    property int comboWidth: 220
    property int labelWidth: 230  // the dropdowns of a group line up
    signal picked(var value)
    spacing: 12
    Text {
        textFormat: Text.PlainText
        width: opt.labelWidth
        wrapMode: Text.WordWrap
        anchors.verticalCenter: parent.verticalCenter
        text: opt.label
        color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14)
    }
    StyledCombo {
        width: opt.comboWidth
        model: opt.labels
        currentIndex: Math.max(0, opt.values.indexOf(opt.current))
        onActivated: function (i) { opt.picked(opt.values[i]) }
        Accessible.name: opt.label
    }
}
