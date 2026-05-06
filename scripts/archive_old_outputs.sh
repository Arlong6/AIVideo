#!/usr/bin/env bash
# Move output/ subdirs older than KEEP_DAYS to SSD.
# Usage: ./scripts/archive_old_outputs.sh [keep_days]
# SSD must be mounted at /Volumes/Extreme SSD/
set -euo pipefail

KEEP_DAYS="${1:-7}"
OUTPUT="/Users/arlong/Projects/AIvideo/output"
SSD="/Volumes/Extreme SSD/AI_Videos"

[[ -d "$SSD" ]] || { echo "❌ SSD not mounted at $SSD"; exit 1; }

python3 - "$KEEP_DAYS" "$OUTPUT" "$SSD" <<'PY'
import os, sys, subprocess
from datetime import datetime, timedelta

KEEP_DAYS, OUTPUT, SSD = int(sys.argv[1]), sys.argv[2], sys.argv[3]
cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
moved = 0; total = 0
for d in sorted(os.listdir(OUTPUT)):
    src = os.path.join(OUTPUT, d)
    if not os.path.isdir(src): continue
    if datetime.fromtimestamp(os.path.getmtime(src)) >= cutoff: continue
    dst = os.path.join(SSD, d)
    if os.path.exists(dst):
        print(f"  SKIP (exists): {d}"); continue
    size = sum(os.path.getsize(os.path.join(dp,f))
               for dp,dn,fn in os.walk(src) for f in fn)
    r = subprocess.run(["rsync","-a","--remove-source-files",
                        src+"/", dst+"/"], capture_output=True)
    if r.returncode != 0:
        print(f"  ❌ {d}: {r.stderr.decode()[:200]}"); continue
    subprocess.run(["find", src, "-type","d","-empty","-delete"], capture_output=True)
    moved += 1; total += size
    print(f"  ✓ {size/1e6:7.1f} MB  {d}")
print(f"\n✅ Moved {moved} dirs / {total/1e9:.2f} GB → SSD")
PY
