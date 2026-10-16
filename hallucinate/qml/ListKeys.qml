import QtQuick

// Keyboard moves for a row inside a ListView: Up/Down, Page Up/Down, Home/End go to other rows, and the Menu key
// (or Shift+F10) opens the row's menu. While a row has the focus these keys are its own, not the window's
// shortcuts (Up and Down change the volume elsewhere).
QtObject {
    id: keys
    property Item row
    signal menu()

    function view() { return row && row.ListView.view ? row.ListView.view : null }
    function go(index) {
        var v = view()
        if (!v || v.count === 0) return
        index = Math.max(0, Math.min(v.count - 1, index))
        v.currentIndex = index
        v.positionViewAtIndex(index, ListView.Contain)
        if (v.currentItem) v.currentItem.forceActiveFocus(Qt.TabFocusReason)
    }
    function page() { var v = view(); return v ? Math.max(1, Math.floor(v.height / Math.max(1, row.height))) : 10 }
    function handles(event) {
        var plain = (event.modifiers & ~Qt.KeypadModifier) === Qt.NoModifier
        return (plain && [Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End,
                          Qt.Key_Menu].indexOf(event.key) >= 0)
            || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))
    }
    function press(event, index) {
        switch (event.key) {
        case Qt.Key_Up: go(index - 1); break
        case Qt.Key_Down: go(index + 1); break
        case Qt.Key_PageUp: go(index - page()); break
        case Qt.Key_PageDown: go(index + page()); break
        case Qt.Key_Home: go(0); break
        case Qt.Key_End: { var v = view(); if (v) go(v.count - 1); break }
        default: keys.menu()
        }
        event.accepted = true
    }
}
