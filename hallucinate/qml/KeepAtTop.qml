import QtQuick

// A list with a header that grows or shrinks (the window narrows, a panel wraps to two rows) keeps its scroll
// position while the top moves, so a page nobody scrolled ended up part way down, its cover cut off. This keeps
// a list that was at the top at the top; one you've scrolled stays where you left it.
//     KeepAtTop { target: list }
Connections {
    property real gap: 0   // how far from the top it was, as last seen
    function onOriginYChanged() {
        if (gap < 1) target.contentY = target.originY
        gap = target.contentY - target.originY
    }
    function onContentYChanged() { gap = target.contentY - target.originY }
}
