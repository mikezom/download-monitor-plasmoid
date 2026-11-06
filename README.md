# Download Monitor (下载监控) for Plasma 6

A panel / system-tray widget that shows the progress of any download that reports to it.
The widget knows nothing about specific downloaders: each job writes a small JSON status file,
and the widget reads the directory every 3 s (every 15 s when idle and closed).

- Tray or panel icon: a download glyph inside a ring showing the combined progress of all running jobs.
  On a horizontal panel (outside the tray) the percentage is shown next to it.
- In the system tray the icon folds into the overflow when no job is running, stale or failed.
- Popup: one row per job with a progress bar, `done / total · speed · time left`, file counts, and a message.
  Clicking a row opens the job's `open` path or URL. "清除已结束" deletes finished, failed and stale jobs.

## Install

The package lives directly in `~/.local/share/plasma/plasmoids/com.mikezom.dlmon`.
Add **下载监控** from the widget explorer, or enable it under System Tray Settings → Entries.
After editing QML, restart the shell: `systemctl --user restart plasma-plasmashell.service`.
For a quick look without touching the panel: `plasmawindowed com.mikezom.dlmon`
(with `XDG_STATE_HOME=<dir>` to point it at test jobs).

## Protocol (v1)

One file per job: `$XDG_STATE_HOME/dlmon/jobs/<id>.json` (default `~/.local/state/dlmon/jobs/`).
Write it atomically: write `.<id>.json.tmp` in the same directory, then rename it over `<id>.json`.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `v` | int | yes | Schema version, `1` |
| `id` | string | yes | `[A-Za-z0-9._-]{1,128}`, equal to the file name without `.json` |
| `title` | string | yes | Display name |
| `state` | string | yes | `queued` · `running` · `paused` · `done` · `failed` |
| `updated` | number | yes | Unix seconds of this write; the heartbeat |
| `done_bytes`, `total_bytes` | int | no | Byte progress; leave `total_bytes` out when unknown |
| `done_items`, `total_items`, `failed_items` | int | no | File counts; used for percent when bytes are unknown |
| `rate_bps` | number | no | Producer's own speed estimate, bytes per second |
| `eta_s` | number | no | Seconds left; derived from bytes and rate when absent |
| `pid` | int | no | The process doing the work; set it only if that process lives as long as the job |
| `stale_after_s` | number | no | Heartbeat timeout, default 300 |
| `started` | number | no | Unix seconds the job began |
| `message` | string | no | One-line detail, e.g. the last error |
| `open` | string | no | Absolute path or URL opened when the row is clicked |

The widget derives one more state, **停滞 (stale)**: a `queued`/`running` job whose `pid` no longer exists,
or whose `updated` is older than `stale_after_s`. A producer stopping on purpose should write `paused`
first, which never goes stale. `done` and `failed` jobs are deleted 24 h after their last `updated`.

### Writing a job

Python, using the reference writer:

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.local/share/plasma/plasmoids/com.mikezom.dlmon/contents/scripts"))
import dlmon
dlmon.write_job({"id": "my-job", "title": "My download", "state": "running",
                 "done_bytes": 1_000, "total_bytes": 10_000}, dlmon.default_jobs_dir())
```

Shell (merges into the existing file, so later calls only pass what changed):

```bash
DLMON=~/.local/share/plasma/plasmoids/com.mikezom.dlmon/contents/scripts/dlmon.py
python $DLMON report --id my-job --title "My download" --state running --total-bytes 10000
python $DLMON report --id my-job --done-bytes 4000 --rate-bps 500
python $DLMON report --id my-job --state done
python $DLMON remove --id my-job
```

Any other language: write the JSON above. `python dlmon.py status` prints what the widget will show.

## Producers

Any program that writes a job file is a producer.

- A long-running downloader: write `running` with byte counts every few seconds, set `pid`, and write
  `paused` from its SIGTERM handler so that a shutdown does not show up as stale.
- Chrome (planned): Chrome only publishes download progress on D-Bus through `libunity`, which is often
  not installed. The plan is a small extension using the `chrome.downloads` API that sends each download
  to a native-messaging host, which writes `chrome-<downloadId>.json` jobs.

## Testing

```bash
python -m unittest discover -s tests -v
```
