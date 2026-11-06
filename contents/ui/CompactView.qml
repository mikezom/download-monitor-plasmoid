import QtQuick
import QtQuick.Layouts

import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid


MouseArea {
    id: compact

    readonly property bool inTray: (Plasmoid.containmentDisplayHints & PlasmaCore.Types.ContainmentForcesSquarePlasmoids) !== 0
    readonly property bool horizontal: Plasmoid.formFactor === PlasmaCore.Types.Horizontal
    readonly property bool showLabel: !inTray && horizontal && root.ring.label !== ""
    // The tray cell is taller than it is wide; a height-sized badge pinned left sat 4 px right of
    // centre. Without a label the badge is the largest square that fits, centred in the cell.
    readonly property real badgeSize: showLabel ? height : Math.min(width, height)
    // The tray cell is larger than the icons drawn in it; sizing the ring to the cell made it
    // ~1.4× its neighbours, so in the tray it follows the tray's icon size instead.
    readonly property real ringSize: inTray
        ? Math.min(badgeSize, Math.round(Kirigami.Units.iconSizes.smallMedium * 1.2))
        : Math.round(badgeSize * 0.85)
    readonly property real idleIconSize: inTray
        ? Math.min(badgeSize, Kirigami.Units.iconSizes.smallMedium)
        : Math.round(badgeSize * 0.7)
    property bool wasExpanded: false

    // Sized from the panel thickness, never from badgeSize, so width and badgeSize cannot bind in a loop.
    Layout.minimumWidth: horizontal ? (showLabel ? row.implicitWidth : height) : -1
    Layout.preferredWidth: Layout.minimumWidth
    Layout.minimumHeight: horizontal ? -1 : width

    hoverEnabled: true
    onPressed: wasExpanded = root.expanded
    onClicked: root.expanded = !wasExpanded

    RowLayout {
        id: row

        anchors.centerIn: parent
        spacing: Kirigami.Units.smallSpacing

        Item {
            Layout.preferredWidth: compact.badgeSize
            Layout.preferredHeight: compact.badgeSize

            ProgressRing {
                anchors.centerIn: parent
                width: compact.ringSize
                height: compact.ringSize
                mode: root.ring.mode
                percent: Math.max(0, root.ring.percent)
            }

            Kirigami.Icon {
                anchors.centerIn: parent
                width: root.ring.mode === "idle" ? compact.idleIconSize : Math.round(compact.ringSize * 0.6)
                height: width
                source: "download-symbolic"
                fallback: "download"
                active: compact.containsMouse
            }
        }

        PlasmaComponents3.Label {
            visible: compact.showLabel
            text: root.ring.label
            color: root.ring.mode === "attention" ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
            font.features: ({ "tnum": 1 })
            Layout.rightMargin: Kirigami.Units.smallSpacing
        }
    }
}
