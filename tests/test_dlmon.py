import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "contents" / "scripts"))

import dlmon  # noqa: E402

NOW = 1_800_000_000.0


def alive_all(pid: int) -> bool:
    return True


def alive_none(pid: int) -> bool:
    return False


def job(**fields):
    base = {"v": 1, "id": "j", "title": "Job", "state": "running", "updated": NOW}
    return {**base, **fields}


class JobsDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "jobs"

    def tearDown(self) -> None:
        self._tmp.cleanup()


class WriteAndLoadTest(JobsDirTest):
    def test_write_job_stamps_version_and_heartbeat_and_leaves_no_temp_file(self) -> None:
        path = dlmon.write_job({"id": "a", "title": "A", "state": "queued"}, self.dir, now=NOW)
        record = json.loads(path.read_text())
        self.assertEqual(record["v"], 1)
        self.assertEqual(record["updated"], NOW)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["a.json"])

    def test_write_job_rejects_path_like_id_and_unknown_state(self) -> None:
        with self.assertRaises(dlmon.InvalidJob):
            dlmon.write_job({"id": "../x", "title": "A", "state": "running"}, self.dir)
        with self.assertRaises(dlmon.InvalidJob):
            dlmon.write_job({"id": "x", "title": "A", "state": "stale"}, self.dir)

    def test_load_reports_malformed_files_and_keeps_good_ones(self) -> None:
        dlmon.write_job({"id": "good", "title": "G", "state": "running"}, self.dir, now=NOW)
        (self.dir / "broken.json").write_text("{not json")
        (self.dir / "renamed.json").write_text(json.dumps(job(id="other")))
        (self.dir / "badtype.json").write_text(json.dumps(job(id="badtype", done_bytes="12")))
        jobs, errors = dlmon.load_jobs(self.dir)
        self.assertEqual([j["id"] for j in jobs], ["good"])
        self.assertEqual(sorted(e.split(":")[0] for e in errors), ["badtype.json", "broken.json", "renamed.json"])

    def test_missing_directory_is_empty(self) -> None:
        self.assertEqual(dlmon.load_jobs(self.dir), ([], []))


class EffectiveStateTest(unittest.TestCase):
    def test_running_with_dead_pid_is_stale(self) -> None:
        self.assertEqual(dlmon.effective_state(job(pid=42), NOW, alive_none), (dlmon.State.STALE, "进程已退出"))

    def test_running_without_heartbeat_is_stale_after_default_window(self) -> None:
        state, note = dlmon.effective_state(job(updated=NOW - 301), NOW, alive_all)
        self.assertEqual(state, dlmon.State.STALE)
        self.assertEqual(note, "5 分钟未更新")
        self.assertEqual(dlmon.effective_state(job(updated=NOW - 299), NOW, alive_all)[0], dlmon.State.RUNNING)

    def test_producer_can_widen_the_stale_window(self) -> None:
        state, _ = dlmon.effective_state(job(updated=NOW - 1000, stale_after_s=3600), NOW, alive_all)
        self.assertEqual(state, dlmon.State.RUNNING)

    def test_paused_job_never_goes_stale(self) -> None:
        state, _ = dlmon.effective_state(job(state="paused", pid=42, updated=NOW - 10**6), NOW, alive_none)
        self.assertEqual(state, dlmon.State.PAUSED)


class SummarizeTest(unittest.TestCase):
    def test_ring_uses_total_bytes_across_active_jobs(self) -> None:
        jobs = [job(id="a", done_bytes=10, total_bytes=100, rate_bps=1000),
                job(id="b", done_bytes=90, total_bytes=100, rate_bps=500),
                job(id="c", state="done", done_bytes=5, total_bytes=5, updated=NOW - 10)]
        out = dlmon.summarize(jobs, [], NOW, alive_all)
        self.assertEqual(out["ring"], {"mode": "progress", "percent": 50.0, "label": "50%"})
        self.assertEqual(out["active"], 2)
        self.assertEqual(out["rateText"], "2 KB/s")
        self.assertEqual([j["jobId"] for j in out["jobs"]], ["a", "b", "c"])

    def test_ring_falls_back_to_item_progress_then_indeterminate(self) -> None:
        items = dlmon.summarize([job(done_items=1, total_items=4)], [], NOW, alive_all)
        self.assertEqual(items["ring"]["percent"], 25.0)
        unknown = dlmon.summarize([job()], [], NOW, alive_all)
        self.assertEqual(unknown["ring"]["mode"], "indeterminate")

    def test_ring_flags_attention_when_only_stale_or_failed_jobs_remain(self) -> None:
        out = dlmon.summarize([job(pid=7), job(id="d", state="done")], [], NOW, alive_none)
        self.assertEqual(out["ring"]["mode"], "attention")
        self.assertEqual(out["attention"], 1)

    def test_idle_when_nothing_needs_watching(self) -> None:
        out = dlmon.summarize([job(state="paused")], [], NOW, alive_all)
        self.assertEqual(out["ring"]["mode"], "idle")
        self.assertEqual(out["active"], 0)

    def test_job_view_texts(self) -> None:
        view = dlmon.summarize([job(done_bytes=3_210_000_000, total_bytes=21_260_000_000, rate_bps=280_000,
                                    done_items=22, total_items=481, failed_items=1)], [], NOW, alive_all)["jobs"][0]
        self.assertEqual(view["detail"], "3.21 / 21.26 GB · 280 KB/s · 剩 17 小时 54 分")
        self.assertEqual(view["itemsText"], "文件 22/481 · 失败 1")
        self.assertEqual(view["stateLabel"], "下载中")

    def test_unknown_percent_is_a_number_for_qml_list_models(self) -> None:
        view = dlmon.summarize([job()], [], NOW, alive_all)["jobs"][0]
        self.assertEqual(view["percent"], dlmon.UNKNOWN_PERCENT)


class FormattingTest(unittest.TestCase):
    def test_bytes_pair_uses_one_unit_chosen_by_total(self) -> None:
        self.assertEqual(dlmon.fmt_bytes_pair(500_000, 4_200_000), "0.5 / 4.2 MB")
        self.assertEqual(dlmon.fmt_bytes_pair(None, 2_000), "2 KB")
        self.assertEqual(dlmon.fmt_bytes_pair(None, None), "")

    def test_duration(self) -> None:
        self.assertEqual(dlmon.fmt_duration(59), "不到 1 分钟")
        self.assertEqual(dlmon.fmt_duration(3599), "59 分钟")
        self.assertEqual(dlmon.fmt_duration(3 * 86400 + 7200), "3 天 2 小时")


class MaintenanceTest(JobsDirTest):
    def test_prune_deletes_only_finished_jobs_past_retention(self) -> None:
        old = NOW - dlmon.FINISHED_RETENTION_S - 1
        for jid, state in (("done-old", "done"), ("failed-old", "failed"), ("paused-old", "paused")):
            dlmon.write_job({"id": jid, "title": jid, "state": state}, self.dir, now=old)
        dlmon.write_job({"id": "done-new", "title": "n", "state": "done"}, self.dir, now=NOW)
        jobs, _ = dlmon.load_jobs(self.dir)
        kept = dlmon.prune(self.dir, jobs, NOW)
        self.assertEqual(sorted(j["id"] for j in kept), ["done-new", "paused-old"])
        self.assertEqual(sorted(p.stem for p in self.dir.glob("*.json")), ["done-new", "paused-old"])

    def test_clear_keeps_running_and_paused(self) -> None:
        for jid, state, pid in (("r", "running", 1), ("p", "paused", None), ("d", "done", None),
                                ("f", "failed", None), ("s", "running", 2)):
            dlmon.write_job({"id": jid, "title": jid, "state": state, "pid": pid}, self.dir, now=NOW)
        removed = dlmon.clear(self.dir, NOW, lambda pid: pid == 1)
        self.assertEqual(removed, 3)
        self.assertEqual(sorted(p.stem for p in self.dir.glob("*.json")), ["p", "r"])

    def test_report_merges_into_existing_job(self) -> None:
        dlmon.report(self.dir, {"id": "x", "title": "X", "state": "running", "total_bytes": 100}, NOW)
        dlmon.report(self.dir, {"id": "x", "done_bytes": 40, "title": None}, NOW + 5)
        record = json.loads((self.dir / "x.json").read_text())
        self.assertEqual((record["title"], record["total_bytes"], record["done_bytes"]), ("X", 100, 40))
        self.assertEqual((record["started"], record["updated"]), (NOW, NOW + 5))

    def test_cli_report_then_status(self) -> None:
        self.assertEqual(dlmon.main(["--dir", str(self.dir), "report", "--id", "cli", "--title", "CLI",
                                     "--state", "running", "--done-bytes", "1", "--total-bytes", "4"]), 0)
        self.assertEqual(dlmon.main(["--dir", str(self.dir), "report", "--id", "nope"]), 2)


if __name__ == "__main__":
    unittest.main()
