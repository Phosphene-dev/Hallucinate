import QtQuick
import QtQuick.Controls
import "."

// Create or edit a smart playlist: a name plus rules that are evaluated live against the library.
Dialog {
    id: dlg
    objectName: "smartEditor"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(760, parent ? parent.width - 40 : 760)
    modal: true
    title: smartId >= 0 ? qsTr("Edit smart playlist") : qsTr("New smart playlist")
    standardButtons: Dialog.Save | Dialog.Cancel

    property int smartId: -1
    property string matchMode: "all"
    property string sortKey: "artist"
    readonly property var schema: userLib.smartRuleSchema
    property string rulesJson: "{}"
    // songs the rules match now: counted on the library's worker a moment after you stop typing, so a big
    // library never makes each keystroke wait (-1: the rules can't be read)
    property int matches: 0
    signal saved(int id, string name)

    onRulesJsonChanged: if (visible) countTimer.restart()
    onVisibleChanged: if (visible) countTimer.restart()
    Timer { id: countTimer; interval: 250; onTriggered: userLib.countRulesAsync(dlg.rulesJson) }
    Connections {
        target: userLib
        function onRulesCounted(json, n) { if (json === dlg.rulesJson) dlg.matches = n }
    }

    ListModel { id: rulesModel }

    function fieldKind(field) {
        for (var i = 0; i < schema.fields.length; i++)
            if (schema.fields[i].key === field) return schema.fields[i].kind
        return "text"
    }
    function needsValue(field, op) {
        return fieldKind(field) !== "bool" && op !== "never" && op !== "is_empty" && op !== "is_not_empty"
    }
    function opsFor(field) {
        var ops = schema.ops[fieldKind(field)]
        return field === "last_played" ? ops : ops.filter(o => o.key !== "never")
    }
    function addRule(field, op, value, value2) {
        field = field || "artist"
        rulesModel.append({ field: field, op: op || opsFor(field)[0].key,
                            value: value === undefined ? "" : String(value), value2: value2 === undefined ? "" : String(value2) })
        update()
    }
    function build() {
        var rules = []
        for (var i = 0; i < rulesModel.count; i++) {
            var r = rulesModel.get(i)
            var kind = fieldKind(r.field)
            var rule = { field: r.field, op: r.op }
            if (r.op === "between") rule.value = [Number(r.value), Number(r.value2)]
            else if (kind === "text") rule.value = r.value
            else if (needsValue(r.field, r.op)) rule.value = Number(r.value)
            rules.push(rule)
        }
        return JSON.stringify({ match: matchMode, rules: rules, sort: sortKey, limit: Number(limitField.text) || 0 })
    }
    function update() { rulesJson = build() }
    function openNew() {
        smartId = -1; nameField.text = ""; matchMode = "all"; sortKey = "artist"; limitField.text = ""
        rulesModel.clear(); addRule("liked", "is_true"); open()
        nameField.forceActiveFocus()
    }
    function openEdit(id, name) {
        var parsed = {}
        try { parsed = JSON.parse(userLib.smartRules(id) || "{}") } catch (e) { parsed = {} }
        smartId = id; nameField.text = name
        matchMode = parsed.match || "all"; sortKey = parsed.sort || "artist"
        limitField.text = parsed.limit ? String(parsed.limit) : ""
        rulesModel.clear()
        for (var rule of (parsed.rules || [])) {
            var v = rule.value, v2 = ""
            if (Array.isArray(v)) { v2 = v[1]; v = v[0] }
            addRule(rule.field, rule.op, v === null || v === undefined ? "" : v, v2)
        }
        update(); open()
    }

    onAccepted: {
        var name = nameField.text.trim()
        if (!name.length) return
        var json = build()
        if (smartId >= 0) {
            if (userLib.updateSmartPlaylist(smartId, name, json)) saved(smartId, name)
        } else {
            var id = userLib.createSmartPlaylist(name, json)
            if (id >= 0) saved(id, name)
        }
    }

    Column {
        width: dlg.availableWidth
        spacing: 12
        TextField {
            id: nameField
            objectName: "smartName"
            width: parent.width
            placeholderText: qsTr("Playlist name")
            selectByMouse: true
            // a smart playlist needs a name: Save waits for one rather than closing and losing the rules
            onTextChanged: { var b = dlg.standardButton(Dialog.Save) || dlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
            onVisibleChanged: if (visible) { var b = dlg.standardButton(Dialog.Save) || dlg.standardButton(Dialog.Ok); if (b) b.enabled = text.trim().length > 0 }
        }
        Row {
            spacing: 8
            Text { anchors.verticalCenter: parent.verticalCenter; text: qsTr("Songs matching"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
            StyledCombo {
                width: 110
                model: [{ k: "all", t: qsTr("all") }, { k: "any", t: qsTr("any") }]
                textRole: "t"
                currentIndex: dlg.matchMode === "any" ? 1 : 0
                onActivated: { dlg.matchMode = currentIndex === 1 ? "any" : "all"; dlg.update() }  // i18n: keep
            }
            Text { anchors.verticalCenter: parent.verticalCenter; text: qsTr("of these rules:"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
        }
        Repeater {
            model: rulesModel
            Row {
                id: ruleRow
                required property int index
                required property string field
                required property string op
                required property string value
                required property string value2
                spacing: 8
                StyledCombo {
                    width: 180
                    model: dlg.schema.fields
                    textRole: "label"
                    currentIndex: dlg.schema.fields.findIndex(f => f.key === ruleRow.field)
                    onActivated: {
                        var f = dlg.schema.fields[currentIndex].key
                        var kindChanged = dlg.fieldKind(f) !== dlg.fieldKind(ruleRow.field)
                        rulesModel.setProperty(ruleRow.index, "field", f)
                        if (kindChanged || !dlg.opsFor(f).some(o => o.key === ruleRow.op)) {
                            rulesModel.setProperty(ruleRow.index, "op", dlg.opsFor(f)[0].key)
                            rulesModel.setProperty(ruleRow.index, "value", "")
                        }
                        dlg.update()
                    }
                }
                StyledCombo {
                    width: 190
                    model: dlg.opsFor(ruleRow.field)
                    textRole: "label"
                    currentIndex: model.findIndex(o => o.key === ruleRow.op)
                    onActivated: { rulesModel.setProperty(ruleRow.index, "op", model[currentIndex].key); dlg.update() }
                }
                TextField {
                    visible: dlg.needsValue(ruleRow.field, ruleRow.op)
                    width: ruleRow.op === "between" ? 90 : 200
                    height: 38
                    text: ruleRow.value
                    selectByMouse: true
                    inputMethodHints: dlg.fieldKind(ruleRow.field) === "text" ? Qt.ImhNone : Qt.ImhFormattedNumbersOnly
                    onTextEdited: { rulesModel.setProperty(ruleRow.index, "value", text); dlg.update() }
                }
                Text { visible: ruleRow.op === "between"; anchors.verticalCenter: parent.verticalCenter; text: qsTr("and"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
                TextField {
                    visible: ruleRow.op === "between"
                    width: 90
                    height: 38
                    text: ruleRow.value2
                    selectByMouse: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    onTextEdited: { rulesModel.setProperty(ruleRow.index, "value2", text); dlg.update() }
                }
                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    icon: "close"; size: 14; tip: qsTr("Remove rule")
                    onClicked: { rulesModel.remove(ruleRow.index); dlg.update() }
                }
            }
        }
        PillButton { text: qsTr("Add rule"); height: 32; onClicked: dlg.addRule() }
        Row {
            spacing: 8
            Text { anchors.verticalCenter: parent.verticalCenter; text: qsTr("Order"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
            StyledCombo {
                width: 200
                model: dlg.schema.sorts
                textRole: "label"
                currentIndex: dlg.schema.sorts.findIndex(s => s.key === dlg.sortKey)
                onActivated: { dlg.sortKey = dlg.schema.sorts[currentIndex].key; dlg.update() }
            }
            Text { anchors.verticalCenter: parent.verticalCenter; text: qsTr("Limit to"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
            TextField {
                id: limitField
                width: 80
                height: 38
                placeholderText: qsTr("no limit")
                selectByMouse: true
                validator: IntValidator { bottom: 0; top: 100000 }
                onTextEdited: dlg.update()
            }
            Text { anchors.verticalCenter: parent.verticalCenter; text: qsTr("songs"); color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); textFormat: Text.PlainText }
        }
        Text {
            textFormat: Text.PlainText
            objectName: "smartPreview"
            width: parent.width
            wrapMode: Text.WordWrap
            readonly property int matches: dlg.matches
            text: matches < 0 ? userLib.describeRules(dlg.rulesJson)
                              : userLib.describeRules(dlg.rulesJson) + " — " + Theme.counted(qsTr("%n song(s) now", "", matches), matches)
            color: matches < 0 ? Theme.error : Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSize(13)
        }
    }
}
