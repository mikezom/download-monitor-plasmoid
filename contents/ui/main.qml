import QtQuick
import QtQuick.Layouts

import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.plasma.plasmoid


PlasmoidItem {
    id: root

    readonly property string helperPath: Qt.resolvedUrl("../scripts/dlmon.py")
        .toString().replace("file://", "")
    readonly property string helperCommand: "/usr/bin/python '" + helperPath + "'"
    readonly property string statusCommand: helperCommand + " status"
    readonly property string clearCommand: helperCommand + " clear"
    readonly property int activeIntervalMs: 3000
    readonly property int idleIntervalMs: 15000

    property var ring: ({ mode: "idle", percent: -1, label: "" })
    property int activeCount: 0
    property int attentionCount: 0
    property var errors: []
    property string helperError: ""
    property string tooltipMain: "下载"
    property string tooltipSub: "正在读取…"
    property bool hasClearable: false
    readonly property ListModel jobs: ListModel {}
    readonly property var clearableStates: ["done", "failed", "stale"]

    Plasmoid.icon: "download"
    Plasmoid.title: "下载监控"
    // Passive lets the system tray fold the icon away while nothing needs watching.
    Plasmoid.status: (activeCount > 0 || attentionCount > 0 || helperError !== "")
        ? PlasmaCore.Types.ActiveStatus
        : PlasmaCore.Types.PassiveStatus

    toolTipMainText: tooltipMain
    toolTipSubText: helperError !== "" ? helperError : tooltipSub

    compactRepresentation: CompactView {}
    fullRepresentation: FullView {}

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: "清除已结束的任务"
            icon.name: "edit-clear-history"
            enabled: root.hasClearable
            onTriggered: root.clearFinished()
        }
    ]

    function syncJobs(list) {
        let sameOrder = list.length === jobs.count
        for (let i = 0; sameOrder && i < list.length; ++i) {
            sameOrder = jobs.get(i).jobId === list[i].jobId
        }
        // Updating rows in place keeps the popup's scroll position and avoids delegate churn.
        if (sameOrder) {
            list.forEach((job, i) => jobs.set(i, job))
            return
        }
        jobs.clear()
        list.forEach(job => jobs.append(job))
    }

    function applyStatus(stdout, stderr) {
        let result
        try {
            result = JSON.parse(stdout.trim())
        } catch (error) {
            helperError = "dlmon.py 输出无效：" + (stderr.trim() || stdout.trim() || "无输出")
            return
        }
        helperError = ""
        ring = result.ring
        activeCount = result.active
        attentionCount = result.attention
        errors = result.errors
        tooltipMain = result.tooltipMain
        tooltipSub = result.tooltipSub
        hasClearable = result.jobs.some(job => clearableStates.includes(job.jobState))
        syncJobs(result.jobs)
    }

    function refresh() {
        executable.connectSource(statusCommand)
    }

    function clearFinished() {
        executable.connectSource(clearCommand)
    }

    Plasma5Support.DataSource {
        id: executable

        engine: "executable"

        onNewData: function(sourceName, data) {
            disconnectSource(sourceName)
            if (sourceName === root.statusCommand) {
                root.applyStatus(data.stdout ?? "", data.stderr ?? "")
            } else {
                root.refresh()
            }
        }
    }

    Timer {
        interval: (root.expanded || root.activeCount > 0) ? root.activeIntervalMs : root.idleIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    onExpandedChanged: {
        if (expanded) {
            refresh()
        }
    }
}
