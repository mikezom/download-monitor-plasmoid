import QtQuick
import QtQuick.Shapes

import org.kde.kirigami as Kirigami


Item {
    id: ring

    // "progress" | "indeterminate" | "attention" | "idle" (from dlmon.py status → ring.mode)
    property string mode: "idle"
    property real percent: 0
    property real spin: 0

    readonly property real thickness: Math.max(2, Math.round(Math.min(width, height) * 0.09))
    readonly property real radius: (Math.min(width, height) - thickness) / 2
    readonly property color trackColor: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g,
                                                Kirigami.Theme.textColor.b, 0.2)
    readonly property color barColor: mode === "attention"
        ? Kirigami.Theme.negativeTextColor
        : Kirigami.Theme.highlightColor
    readonly property real sweep: {
        if (mode === "indeterminate") {
            return 90
        }
        return 360 * Math.max(0, Math.min(percent, 100)) / 100
    }

    visible: mode !== "idle"

    Behavior on percent {
        NumberAnimation {
            duration: Kirigami.Units.longDuration
            easing.type: Easing.OutCubic
        }
    }

    NumberAnimation on spin {
        from: 0
        to: 360
        duration: 1200
        loops: Animation.Infinite
        running: ring.visible && ring.mode === "indeterminate"
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: ring.trackColor
            strokeWidth: ring.thickness
            fillColor: "transparent"

            PathAngleArc {
                centerX: ring.width / 2
                centerY: ring.height / 2
                radiusX: ring.radius
                radiusY: ring.radius
                startAngle: 0
                sweepAngle: 360
            }
        }

        ShapePath {
            strokeColor: ring.barColor
            strokeWidth: ring.thickness
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap

            PathAngleArc {
                centerX: ring.width / 2
                centerY: ring.height / 2
                radiusX: ring.radius
                radiusY: ring.radius
                startAngle: -90 + (ring.mode === "indeterminate" ? ring.spin : 0)
                sweepAngle: ring.sweep
            }
        }
    }
}
