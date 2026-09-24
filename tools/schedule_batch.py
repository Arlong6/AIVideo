"""Schedule the next N pending fights, one per day at a fixed local time.

publish_tiktok.py posts the next pending fight and takes one `--at`. Driving it
in a loop from the shell needs date arithmetic and quoting that is easy to get
wrong — the first attempt at this was a zsh heredoc that silently produced no
posts at all. Doing it here keeps the arithmetic in one place and makes a failure
loud.

Each call uploads a ~30MB file to Publer, so a full run takes several minutes;
launch it through tools/run_detached.py rather than a plain background job.

Usage:
  python3 tools/schedule_batch.py 2026-09-27 12          # 12 posts from that date
  python3 tools/schedule_batch.py 2026-09-27 12 --hour 21
  python3 tools/schedule_batch.py 2026-09-27 12 --dry-run
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))          # the channel posts on Taipei time


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    start = datetime.strptime(args[0], "%Y-%m-%d")
    count = int(args[1])
    hour = 21
    if "--hour" in sys.argv:
        hour = int(sys.argv[sys.argv.index("--hour") + 1])
    dry = "--dry-run" in sys.argv

    base = datetime(start.year, start.month, start.day, hour, 0, 0, tzinfo=TZ)
    done = 0
    for i in range(count):
        at = (base + timedelta(days=i)).isoformat()
        cmd = [sys.executable, str(ROOT / "tools/publish_tiktok.py"), "--at", at]
        if not dry:
            cmd.append("--post")
        print(f"=== slot {i + 1}/{count} -> {at}", flush=True)
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        out = (r.stdout or "") + (r.stderr or "")
        print("\n".join(out.strip().splitlines()[-3:]), flush=True)
        if r.returncode != 0:
            # Stop rather than plough on: a failure here usually means the queue
            # is empty or Publer rejected something, and the remaining slots
            # would all fail the same way.
            print(f"STOPPED at slot {i + 1}: exit {r.returncode}", flush=True)
            break
        done += 1
    print(f"scheduled {done}/{count}", flush=True)
    return 0 if done == count else 1


if __name__ == "__main__":
    raise SystemExit(main())
