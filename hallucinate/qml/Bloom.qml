import QtQuick
import QtQuick.Shapes
import "."

// A soft round glow of one colour, fading to nothing at its edge: a page lit by its cover's colours.
Shape {
    id: bloom
    readonly property bool decoration: true  // a glow, meant to spill past edges (see main.qml pastTheEdge)
    property color tint
    property real size: 700
    width: size; height: size
    preferredRendererType: Shape.CurveRenderer
    ShapePath {
        strokeWidth: 0; strokeColor: "transparent"
        fillGradient: RadialGradient {
            centerX: bloom.size / 2; centerY: bloom.size / 2; centerRadius: bloom.size / 2
            focalX: bloom.size / 2; focalY: bloom.size / 2
            GradientStop { position: 0; color: Qt.rgba(bloom.tint.r, bloom.tint.g, bloom.tint.b, Theme.light ? 0.22 : 0.32) }
            GradientStop { position: 1; color: Qt.rgba(bloom.tint.r, bloom.tint.g, bloom.tint.b, 0) }
        }
        PathRectangle { x: 0; y: 0; width: bloom.size; height: bloom.size }
    }
}
