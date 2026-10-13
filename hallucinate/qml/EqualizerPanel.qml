import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "."

Column {
    id: panel
    spacing: 12
    StyledCheck {
        text: "Enable equalizer"
        enabled: player.eqAvailable
        checked: player.eqEnabled
        onToggled: player.setEqEnabled(checked)
    }
    Text {
        textFormat: Text.PlainText
        visible: !player.eqAvailable
        text: "The equalizer needs the numpy Python package."
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(12)
    }
    Row {
        spacing: 12
        opacity: player.eqEnabled ? 1 : 0.5
        Text { anchors.verticalCenter: parent.verticalCenter; text: "Preset"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
        StyledCombo {
            id: presetBox
            model: player.eqPresets.concat(["Custom"])
            currentIndex: Math.max(0, model.indexOf(player.eqPreset))
            onActivated: if (currentText !== "Custom") player.setEqPreset(currentText)
        }
    }
    Row {
        spacing: 6
        opacity: player.eqEnabled ? 1 : 0.5
        Repeater {
            model: player.eqBands
            Column {
                required property int index
                required property string modelData
                spacing: 4
                width: 44
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: (player.eqGains[index] > 0 ? "+" : "") + Math.round(player.eqGains[index]) ; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); textFormat: Text.PlainText }
                Slider {
                    id: sl
                    orientation: Qt.Vertical
                    height: 120
                    anchors.horizontalCenter: parent.horizontalCenter
                    from: -12; to: 12; stepSize: 1
                    Accessible.name: modelData + "Hz band"
                    value: player.eqGains[index]
                    onMoved: player.setEqBand(index, value)
                    background: Rectangle {
                        x: sl.leftPadding + sl.availableWidth / 2 - width / 2
                        y: sl.topPadding
                        width: 4; height: sl.availableHeight; radius: 2
                        color: Theme.surfaceHi
                    }
                    handle: Rectangle {
                        x: sl.leftPadding + sl.availableWidth / 2 - width / 2
                        y: sl.topPadding + sl.visualPosition * (sl.availableHeight - height)
                        width: 14; height: 14; radius: 7
                        color: sl.pressed ? Theme.accentHi : Theme.accent
                    }
                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: player.setEqBand(index, 0) }
                }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: modelData; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(11); textFormat: Text.PlainText }
            }
        }
    }

    // Headphone correction (AutoEQ): search a model or import a profile file
    Item { width: 1; height: 10 }
    Text {
        textFormat: Text.PlainText
        text: "Headphone correction"
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(15)
        font.weight: Font.DemiBold
    }
    Text {
        textFormat: Text.PlainText
        width: 560
        wrapMode: Text.Wrap
        text: "Make your headphones sound neutral with an AutoEQ profile. It's applied under the bands above; the "
              + "volume is lowered a little so the correction can't clip."
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(12)
    }
    Row {
        spacing: 14
        visible: player.headphoneName.length > 0
        Canvas {
            id: curvePreview
            objectName: "headphoneCurve"
            width: 220; height: 64
            readonly property var points: player.headphoneCurve
            onPointsChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                ctx.strokeStyle = Theme.stroke
                ctx.beginPath(); ctx.moveTo(0, height / 2); ctx.lineTo(width, height / 2); ctx.stroke()
                if (points.length < 2) return
                var lo = Math.log(20), hi = Math.log(20000)
                ctx.strokeStyle = Theme.accent
                ctx.lineWidth = 2
                ctx.beginPath()
                for (var i = 0; i < points.length; i++) {
                    var x = (Math.log(points[i][0]) - lo) / (hi - lo) * width
                    var y = height / 2 - Math.max(-12, Math.min(12, points[i][1])) / 12 * (height / 2 - 3)
                    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
                }
                ctx.stroke()
            }
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Text {
                textFormat: Text.PlainText
                objectName: "headphoneName"
                text: "Correcting for " + player.headphoneName
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(14)
                font.weight: Font.DemiBold
            }
            PillButton { text: "Remove"; height: 30; onClicked: player.clearHeadphone() }
        }
    }
    Row {
        spacing: 10
        TextField {
            id: hpSearch
            objectName: "headphoneSearch"
            width: 300
            height: 36
            placeholderText: "Search your headphones (e.g. HD 600)"
            placeholderTextColor: Theme.textDim
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(13)
            leftPadding: 14
            selectByMouse: true
            background: Rectangle {
                radius: height / 2
                color: hpSearch.activeFocus ? Theme.glassStrong : Theme.glass
                border.width: 1
                border.color: hpSearch.activeFocus ? Theme.strokeHi : Theme.stroke
            }
            onTextEdited: hpTimer.restart()
            onAccepted: headphones.find(text)
            Timer { id: hpTimer; interval: 350; onTriggered: headphones.find(hpSearch.text) }
        }
        PillButton { text: "Import file…"; onClicked: hpFile.open() }
    }
    Text {
        textFormat: Text.PlainText
        visible: headphones.status.length > 0 || hpError.length > 0
        property string hpError: ""
        id: hpStatus
        text: hpError.length ? hpError : headphones.status
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(12)
    }
    ListView {
        id: hpResults
        objectName: "headphoneResults"
        width: 560
        height: Math.min(count, 6) * 38
        visible: count > 0
        clip: true
        model: headphones.results
        ScrollBar.vertical: ScrollBar {}
        delegate: Rectangle {
            required property var modelData
            required property int index
            width: hpResults.width - 8
            height: 38
            radius: 10
            color: rowMouse.containsMouse ? Theme.glassHover : "transparent"
            Text {
                textFormat: Text.PlainText
                x: 12
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - sourceText.width - 36
                text: modelData.name
                color: Theme.text
                elide: Text.ElideRight
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(13)
            }
            Text {
                textFormat: Text.PlainText
                id: sourceText
                anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                text: "measured by " + modelData.source
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSize(11)
            }
            MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: { headphones.choose(index); hpSearch.text = "" }
            }
        }
    }
    FileDialog {
        id: hpFile
        title: "Import an AutoEQ profile (ParametricEQ.txt or GraphicEQ.txt)"
        nameFilters: ["EQ profiles (*.txt)", "All files (*)"]
        onAccepted: hpStatus.hpError = headphones.importFile(selectedFile.toString())
    }
}
