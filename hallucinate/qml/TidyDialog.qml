import QtQuick
import QtQuick.Controls
import "."

// Library health's "Tidy up": the clean-up steps in the order that works best, each with what it would do and its
// own button: identify songs by their sound, fill in missing tags, merge duplicates, then organize the files (by
// the tags the first steps put right). Nothing happens on its own: every step shows what it found before saving.
Dialog {
    id: dlg
    objectName: "tidyDialog"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(720, (parent ? parent.width : 720) - 40)
    height: Math.min(640, (parent ? parent.height : 640) - 60)
    modal: true
    title: qsTr("Tidy up your library")
    property var checks: []
    signal reviewFixes(string kind)  // the page opens its review
    signal mergeDuplicates()

    function count(id) {
        for (var i = 0; i < checks.length; i++) if (checks[i].id === id) return id === "duplicates" ? (checks[i].extra || 0) : checks[i].count
        return 0
    }

    footer: Row {
        padding: 16
        layoutDirection: Qt.RightToLeft
        PillButton { text: qsTr("Close"); onClicked: dlg.close() }
    }

    Flickable {
        WheelScroll {}  // the mouse wheel: even notches, hi-res wheels too
        anchors.fill: parent
        contentHeight: steps.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        Column {
            id: steps
            width: parent.width - 12
            spacing: 14
            Text {
                textFormat: Text.PlainText
                width: parent.width
                wrapMode: Text.WordWrap
                text: qsTr("Step by step, in this order: each shows what it found before anything is saved, and you can skip any of them.")
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Step {
                number: 1
                visible: sources.acoustidBuiltIn  // (on hold until Hallucinate has its own AcoustID key)
                title: qsTr("Identify songs by their sound")
                detail: !sources.acoustid ? qsTr("Off: switch it on in Settings → Online & privacy (each song's fingerprint and length go to AcoustID).")
                        : qsTr("For songs with no title tag, or no artist or album: AcoustID tells what they are from how they sound.")
                fixKinds: ["identify"]
                setUp: sources.acoustid
            }
            Step {
                number: sources.acoustidBuiltIn ? 2 : 1
                title: qsTr("Fill in missing tags")
                detail: qsTr("Artists and albums from folder names, then years and track numbers from names and MusicBrainz.")
                fixKinds: ["untagged", "year", "numbers"]
            }
            Step {
                number: sources.acoustidBuiltIn ? 3 : 2
                title: qsTr("Merge duplicates")
                detail: qsTr("The best copy of each song stays and gets the others' likes, plays and playlist places.")
                count: dlg.count("duplicates")
                action: qsTr("Review and merge…")
                onAct: dlg.mergeDuplicates()
            }
            Step {
                number: sources.acoustidBuiltIn ? 4 : 3
                title: qsTr("Organize the files")
                detail: qsTr("Folders and file names made from the tags, now that they're right. Every move is shown first, and it can be undone.")
                count: -1
                action: qsTr("Organize files…")
                actionEnabled: !library.scanning
                onAct: { dlg.close(); Nav.organizeFiles([]) }
            }
        }
    }

    // One step: its number, what it does, and a button (or, for tag fixes, one per kind of fix)
    component Step: Row {
        id: step
        property int number
        property string title
        property string detail
        property var fixKinds: []
        property bool setUp: true
        property int count: 0  // -1: no count (always worth offering)
        property string action
        property bool actionEnabled: true
        signal act()
        readonly property int fixCount: {
            var n = 0
            for (var i = 0; i < fixKinds.length; i++) n += dlg.count(fixKinds[i])
            return n
        }
        readonly property bool done: fixKinds.length ? fixCount === 0 : count === 0
        width: steps.width
        spacing: 12
        Rectangle {
            width: 30; height: 30; radius: 15
            color: step.done ? Theme.hoverTint : Theme.accent
            Text {
                textFormat: Text.PlainText
                anchors.centerIn: parent
                text: step.done ? "✓" : step.number
                color: step.done ? Theme.accent : Theme.onAccent
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(13); font.weight: Font.Bold
            }
        }
        Column {
            width: step.width - 42
            spacing: 6
            Text {
                textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight
                text: step.title
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
            }
            Text {
                textFormat: Text.PlainText; width: parent.width; wrapMode: Text.WordWrap
                text: step.detail
                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Text {
                textFormat: Text.PlainText
                visible: step.done
                text: qsTr("Nothing to do here")
                color: Theme.accent; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12)
            }
            Flow {
                width: parent.width
                spacing: 8
                visible: !step.done
                Repeater {
                    model: step.fixKinds
                    PillButton {
                        id: fixButton
                        required property string modelData
                        readonly property int n: dlg.count(modelData)
                        readonly property bool mine: metaEditor.fixKind === modelData
                        readonly property bool working: mine && (metaEditor.fixesBusy || metaEditor.fixesSaving)
                        readonly property int found: metaEditor.fixCounts[modelData] || 0
                        objectName: "tidy_" + modelData
                        visible: n > 0 || working || found > 0
                        height: 32
                        primary: !working
                        enabled: working || !(metaEditor.fixesBusy || metaEditor.fixesSaving)
                        text: !step.setUp ? qsTr("Set up…")
                              : working ? (metaEditor.fixesSaving ? qsTr("Stop saving") : qsTr("Stop · %1 of %2").arg(Theme.num(metaEditor.fixesDone)).arg(Theme.num(metaEditor.fixesTotal)))
                              : found > 0 && !(mine && metaEditor.fixesBusy) ? qsTr("Review %1 found…").arg(Theme.num(found))
                              : modelData === "identify" ? Theme.counted(qsTr("Identify %n song(s)", "", n), n)
                              : modelData === "untagged" ? Theme.counted(qsTr("Guess artist and album for %n song(s)", "", n), n)
                              : modelData === "year" ? Theme.counted(qsTr("Find years for %n album(s)", "", n), n)
                              : Theme.counted(qsTr("Find track numbers for %n album(s)", "", n), n)
                        onClicked: {
                            if (!step.setUp) { dlg.close(); Nav.openSettingsAt("sharing"); return }
                            if (metaEditor.fixesSaving) { metaEditor.stopSavingFixes(); return }
                            if (metaEditor.fixesBusy) { metaEditor.cancelFixes(); return }
                            if (found > 0) { dlg.reviewFixes(modelData); return }
                            metaEditor.findFixes(modelData)
                        }
                    }
                }
                PillButton {
                    visible: step.fixKinds.length === 0
                    objectName: "tidyStep" + step.number
                    height: 32
                    primary: true
                    enabled: step.actionEnabled
                    text: step.count > 0 ? step.action + "  (" + Theme.num(step.count) + ")" : step.action
                    onClicked: step.act()
                }
            }
        }
    }
}
