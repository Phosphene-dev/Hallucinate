import QtQuick
import "."

// Middle-click autoscroll (#165), as in a web browser: middle-click a list or page and it scrolls by itself
// towards the pointer, faster the further the pointer is from where you clicked; any click, the wheel or Esc
// stops it. Settings → Appearance can switch it off. main.qml starts it (start(view, x, y)) from a middle click
// nothing else took (the volume button's middle click still mutes).
Item {
    id: auto
    objectName: "autoScroll"
    property var view: null  // the list or page being scrolled
    property point anchor: Qt.point(0, 0)
    property point pointer: Qt.point(0, 0)
    readonly property bool active: view !== null
    readonly property real dead: 14  // pixels around the anchor where it stays still
    visible: active
    z: 9000

    // The list or page under (x, y) (in `root`) that scrolls up and down, or null: the innermost one, looking
    // through what's under the point topmost first (a decoration over the whole window has nothing in it)
    function scrollableAt(root, x, y) {
        function canScroll(q) {
            return q.contentY !== undefined && q.originY !== undefined && q.flickableDirection !== undefined
                   && q.flickableDirection !== Flickable.HorizontalFlick && q.interactive !== false
                   && q.contentHeight + (q.topMargin || 0) + (q.bottomMargin || 0) > q.height + 1
        }
        function find(item, depth) {
            if (depth > 40) return null
            var kids = item.children
            for (var i = kids.length - 1; i >= 0; i--) {
                var c = kids[i]
                if (!c.visible || c.opacity === 0 || c === auto) continue
                var p = root.mapToItem(c, x, y)
                if (p.x < 0 || p.y < 0 || p.x > c.width || p.y > c.height) continue
                var hit = find(c, depth + 1)
                if (hit) return hit
            }
            return canScroll(item) ? item : null
        }
        return find(root, 0)
    }
    function start(target, x, y) {
        if (!target) return
        view = target
        anchor = Qt.point(x, y)
        pointer = anchor
        forceActiveFocus()
    }
    function stop() { view = null }

    Timer {
        interval: 16
        repeat: true
        running: auto.active
        onTriggered: {
            var v = auto.view
            if (!v) return
            var d = auto.pointer.y - auto.anchor.y
            var off = Math.abs(d) - auto.dead
            if (off <= 0) return
            // gentle near the anchor, quick far from it: about 2 px a frame at 40 px away, 40 at 300
            var step = Math.pow(off / 10, 1.35) * 0.45 * shell.scrollSpeed * (d < 0 ? -1 : 1)
            var top = v.originY - (v.topMargin || 0)
            var bottom = Math.max(top, v.originY + v.contentHeight + (v.bottomMargin || 0) - v.height)
            v.contentY = Math.max(top, Math.min(bottom, v.contentY + step))
        }
    }
    // While it runs: the pointer steers it, and anything else stops it
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.AllButtons
        cursorShape: Math.abs(auto.pointer.y - auto.anchor.y) > auto.dead ? Qt.SizeVerCursor : Qt.SizeAllCursor
        onPositionChanged: function (mouse) { auto.pointer = Qt.point(mouse.x, mouse.y) }
        onPressed: function (mouse) { mouse.accepted = true; auto.stop() }
        onWheel: function (wheel) { wheel.accepted = true; auto.stop() }
    }
    Keys.onEscapePressed: stop()
    // the anchor: a small ring with arrows, where the middle click was
    Rectangle {
        objectName: "autoScrollAnchor"
        x: auto.anchor.x - width / 2; y: auto.anchor.y - height / 2
        width: 30; height: 30; radius: 15
        color: Theme.surface
        opacity: 0.92
        border.width: 1.5
        border.color: Theme.accent
        Text { anchors.horizontalCenter: parent.horizontalCenter; y: 1; text: "▴"; color: Theme.accent; font.pixelSize: 12; textFormat: Text.PlainText }
        Text { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 1; text: "▾"; color: Theme.accent; font.pixelSize: 12; textFormat: Text.PlainText }
        Rectangle { anchors.centerIn: parent; width: 4; height: 4; radius: 2; color: Theme.accent }
    }
}
