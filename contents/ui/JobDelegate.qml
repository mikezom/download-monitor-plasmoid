import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts

import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents3


PlasmaComponents3.ItemDelegate {
    id: delegate

    required property string jobId
    required property string title
    required property string jobState
    required property string stateLabel
    required property real percent
    required property string detail
    required property string itemsText
    required property string message
    required property string openTarget

    readonly property bool active: jobState === "running" || jobState === "queued"
    readonly property bool troubled: jobState === "failed" || jobState === "stale"
    readonly property color stateColor: {
        if (troubled) {
            return Kirigami.Theme.negativeTextColor
        }
        if (jobState === "done") {
            return Kirigami.Theme.positiveTextColor
        }
        if (jobState === "paused" || jobState === "queued") {
            return Kirigami.Theme.neutralTextColor
        }
        return Kirigami.Theme.textColor
    }

    width: ListView.view.width - ListView.view.leftMargin - ListView.view.rightMargin
    hoverEnabled: openTarget !== ""

    onClicked: {
        if (openTarget !== "") {
            Qt.openUrlExternally(openTarget.startsWith("/") ? "file://" + openTarget : openTarget)
        }
    }

    QQC2.ToolTip.text: openTarget !== "" ? "打开 " + openTarget : ""
    QQC2.ToolTip.visible: hovered && openTarget !== ""
    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Label {
                Layout.fillWidth: true
                text: delegate.title
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            PlasmaComponents3.Label {
                text: delegate.stateLabel
                    + (delegate.percent >= 0 && delegate.jobState !== "done" ? " · " + delegate.percent.toFixed(1) + "%" : "")
                color: delegate.stateColor
                font.features: ({ "tnum": 1 })
            }
        }

        PlasmaComponents3.ProgressBar {
            Layout.fillWidth: true
            visible: delegate.jobState !== "done"
            from: 0
            to: 100
            value: Math.max(0, delegate.percent)
            indeterminate: delegate.percent < 0 && delegate.active
        }

        PlasmaComponents3.Label {
            Layout.fillWidth: true
            visible: text !== ""
            text: [delegate.detail, delegate.itemsText].filter(s => s !== "").join(" · ")
            font: Kirigami.Theme.smallFont
            opacity: 0.8
            elide: Text.ElideRight
        }

        PlasmaComponents3.Label {
            Layout.fillWidth: true
            visible: text !== ""
            text: delegate.message
            font: Kirigami.Theme.smallFont
            color: delegate.troubled ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }
    }
}
