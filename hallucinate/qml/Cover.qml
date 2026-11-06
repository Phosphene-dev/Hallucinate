import QtQuick
import QtQuick.Effects
import "."

Rectangle {
    id: cover
    property url source
    property string fallback: "♪"
    color: "transparent"
    // Shader masking is unavailable with the software renderer; fall back to square corners.
    readonly property bool useMask: GraphicsInfo.api !== GraphicsInfo.Software
    // Covers are served by the cached "art" image provider in size buckets, decoded off the GUI thread.
    readonly property real wantedPx: Math.max(width, height) * Screen.devicePixelRatio
    readonly property int bucketPx: wantedPx <= 64 ? 64 : wantedPx <= 128 ? 128 : wantedPx <= 256 ? 256 : 512
    readonly property string sourceText: source.toString()
    // A cover that didn't load (the provider sends a 1-pixel placeholder, which the image cache would keep
    // showing as a blank square: #115) shows the ♪ and is asked for again a little later. Each try has an address
    // of its own (the time it was made), so Qt's image cache can't hand back a placeholder kept from an earlier
    // failure: rows made again while scrolling were getting those, and stayed blank until the cache let go of them
    property int attempt: 0
    property string tryTag: ""
    // covers that may have changed on disk (after a scan, or Library health → Repair covers) are asked for again
    readonly property int revision: typeof library !== "undefined" && library ? library.artRevision : 0
    // (a load that failed outright counts too: it's tried again the same way)
    readonly property bool missing: (img.status === Image.Ready && img.sourceSize.width <= 1) || img.status === Image.Error
    readonly property string resolved: sourceText.length === 0 ? ""
        : sourceText.indexOf("file:") === 0 ? "image://art/" + bucketPx + (attempt ? "~" + tryTag : "") + (revision ? "~r" + revision : "")
                                              + "/" + encodeURIComponent(sourceText)
        : sourceText
    onSourceTextChanged: { attempt = 0; retry.stop() }
    onRevisionChanged: attempt = 0  // (covers were read again: a fresh set of quick tries)
    onMissingChanged: if (missing && sourceText.indexOf("file:") === 0) retry.restart()
    // The first try again comes quickly (it's usually the image cache's old placeholder), then further apart. It
    // never gives up for good: a cover a scan writes a minute later still turns up, without scrolling away and
    // back (a tester: random songs stayed blank until their row was made again). After the quick tries, a missing
    // cover is looked for every 10 s, then 30 s: a cheap check while it's on screen.
    Timer {
        id: retry
        interval: cover.attempt === 0 ? 250 : cover.attempt < 6 ? 1200 * cover.attempt : cover.attempt < 12 ? 10000 : 30000
        onTriggered: cover.again()
    }
    function again() { tryTag = attempt + 1 + "-" + Date.now(); attempt++ }
    // a picture still loading after a long while (its request lost while rows came and went) is asked for again
    Timer {
        interval: 10000
        running: img.status === Image.Loading
        onTriggered: cover.again()
    }

    Rectangle {
        anchors.fill: parent
        radius: cover.radius
        color: Theme.surface
    }
    Text {
        textFormat: Text.PlainText
        anchors.centerIn: parent
        text: cover.fallback
        color: Theme.textDim  // readable on the placeholder in every theme
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSize(Math.max(12, cover.width * 0.4))
        visible: img.status !== Image.Ready || cover.missing
    }
    Image {
        id: img
        anchors.fill: parent
        source: cover.resolved
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        opacity: status === Image.Ready && !cover.missing ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        visible: !cover.useMask
        layer.enabled: cover.useMask
        layer.smooth: true
    }
    Rectangle {
        id: mask
        anchors.fill: parent
        radius: cover.radius
        visible: false
        antialiasing: true
        // A hard-edged, screen-sized mask turns small circles into octagons and stair-steps the corners.
        // Render it at twice the size and let its edge fade over the threshold below.
        layer.enabled: cover.useMask
        layer.smooth: true
        layer.textureSize: Qt.size(Math.ceil(width * 2 * Screen.devicePixelRatio), Math.ceil(height * 2 * Screen.devicePixelRatio))
    }
    MultiEffect {
        anchors.fill: parent
        source: img
        maskEnabled: true
        maskSource: mask
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
        visible: cover.useMask && img.status === Image.Ready && !cover.missing
    }
}
