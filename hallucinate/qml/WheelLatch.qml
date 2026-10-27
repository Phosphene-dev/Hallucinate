pragma Singleton
import QtQuick

// When the mouse wheel last scrolled a page (see WheelScroll): a page scroll already under way carries on over a
// row of albums instead of being caught by it, while a turn of the wheel that starts over the row moves the row.
QtObject {
    property real pageAt: 0
    readonly property int settle: 700  // ms without the page scrolling before a row takes the wheel
}
