import QtQuick
import QtQuick.Layouts

import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasmoid


PlasmaExtras.Representation {
    id: full

    readonly property bool trayDrawsHeading: (Plasmoid.containmentDisplayHints & PlasmaCore.Types.ContainmentDrawsPlasmoidHeading) !== 0

    Layout.minimumWidth: Kirigami.Units.gridUnit * 20
    Layout.minimumHeight: Kirigami.Units.gridUnit * 10
    Layout.preferredWidth: Kirigami.Units.gridUnit * 26
    Layout.preferredHeight: Kirigami.Units.gridUnit * 20

    collapseMarginsHint: true

    // In the system tray the tray draws the heading and shows Plasmoid.contextualActions there.
    header: PlasmaExtras.PlasmoidHeading {
        visible: !full.trayDrawsHeading

        contentItem: RowLayout {
            spacing: Kirigami.Units.smallSpacing

            PlasmaExtras.Heading {
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.largeSpacing
                level: 1
                text: "下载"
            }

            PlasmaComponents3.ToolButton {
                text: "清除已结束"
                icon.name: "edit-clear-history"
                enabled: root.hasClearable
                onClicked: root.clearFinished()
            }
        }
    }

    footer: PlasmaComponents3.Label {
        visible: root.errors.length > 0
        padding: Kirigami.Units.smallSpacing
        text: root.errors.length + " 个状态文件无法读取：" + root.errors.join("；")
        color: Kirigami.Theme.negativeTextColor
        font: Kirigami.Theme.smallFont
        wrapMode: Text.Wrap
        maximumLineCount: 3
        elide: Text.ElideRight
    }

    PlasmaComponents3.ScrollView {
        anchors.fill: parent

        // HACK: workaround for https://bugreports.qt.io/browse/QTBUG-83890 (as in Plasma's own applets)
        PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

        contentWidth: availableWidth - jobList.leftMargin - jobList.rightMargin

        contentItem: ListView {
            id: jobList

            model: root.jobs
            clip: true
            spacing: Kirigami.Units.smallSpacing
            topMargin: Kirigami.Units.largeSpacing
            leftMargin: Kirigami.Units.largeSpacing
            rightMargin: Kirigami.Units.largeSpacing
            bottomMargin: Kirigami.Units.largeSpacing

            delegate: JobDelegate {}

            PlasmaExtras.PlaceholderMessage {
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.gridUnit * 4
                visible: jobList.count === 0
                iconName: root.helperError !== "" ? "dialog-error" : "download"
                text: root.helperError !== "" ? "无法读取下载状态" : "没有下载任务"
                explanation: root.helperError !== ""
                    ? root.helperError
                    : "下载程序把状态写到 ~/.local/state/dlmon/jobs/ 后会显示在这里"
            }
        }
    }
}
