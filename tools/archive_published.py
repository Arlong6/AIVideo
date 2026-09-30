"""Move the raw render + short of every TikTok-published fight to the SSD.

Local disk was down to 18 GB on 2026-09-30 with 5 GB of pixel_battle output,
most of it raw renders of fights that were already live. arlong: 「記得之後影片
太久要丟到ssd那」. The rule (memory: reference_video_archive_ssd):

  - move only what Publer reports as PUBLISHED. Scheduled is not enough: a
    post that fails still needs the local short for the retry.
  - move the raw render (scripted/<stem>_*) and the short; keep covers,
    captions, manifest and the queue local — they are small and the tools
    read them.
  - record where each file went in upload_queue.json (`archived_to`), so the
    queue stays the one place that knows a fight's state. The `status` field
    is left alone — plan_posting pins the order on it.

Publer's list endpoint ignores per_page (always 15 rows) and its `page` is
ZERO-based (page=1 is the second page; probed 2026-09-30), so pages are walked
from 0 until one comes back empty. Rows are matched to the queue by caption
first line — the same uniqueness key gen_captions enforces and
ingest_analytics matches on.

Usage:
  python3 tools/archive_published.py            # dry run: shows what would move
  python3 tools/archive_published.py --move
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import publer_client as pc          # noqa: E402
import publish_tiktok as pt         # noqa: E402

SSD = Path("/Volumes/Extreme SSD/AI_Videos/pixel_battle_output/published")
SCRIPTED = ROOT / "pixel_battle/output/scripted"
SHORTS = ROOT / "pixel_battle/output/shorts"


def _published_texts() -> list[str]:
    pt._load_env()
    h = pc._headers(os.environ["PUBLER_API_KEY"], os.environ.get("PUBLER_WORKSPACE_ID"))
    texts: list[str] = []
    for page in range(0, 50):
        r = pc._request("GET", f"{pc.API_BASE}/posts?state=published&page={page}", h)
        posts = r.get("posts", [])
        if not posts:
            break
        texts += [(p.get("text") or "") for p in posts]
    return texts


def _match_published(q: list[dict], texts: list[str]) -> set[str]:
    """Stems whose post Publer reports as published.

    Pass 1 matches caption first line exactly and consumes the post text, so
    pass 2 cannot re-use it. Pass 2 is for the first posts, which went out with
    captions rewritten since (the matchup moved to line 1 on 2026-09-25) and
    #1, posted by hand: both stem tokens (b01_lumen_jugg -> "lumen", "jugg";
    the hand-typed post says "Juggernau") in the post text, left before right.
    The order matters because mirror pairs exist (b02 Wildfire/Vanguard and
    b10 Vanguard/Wildfire) and an unordered match picked a scheduled fight.
    """
    remaining = list(texts)
    hit: set[str] = set()
    for e in q:
        first = (e.get("caption") or "").splitlines()
        if not first:
            continue
        for t in remaining:
            lines = t.splitlines()
            if lines and lines[0].strip() == first[0].strip():
                hit.add(e["stem"])
                remaining.remove(t)
                break
    for e in q:
        if e["stem"] in hit:
            continue
        names = e["stem"].split("_")[1:]
        if len(names) != 2:
            continue
        for t in remaining:
            tl = t.lower()
            i, j = tl.find(names[0]), tl.find(names[1])
            if i >= 0 and j > i:
                hit.add(e["stem"])
                remaining.remove(t)
                break
    if remaining:
        print(f"  {len(remaining)} published post(s) match no fight:")
        for t in remaining:
            print("    ", t.splitlines()[0][:60] if t.strip() else "(empty)")
    return hit


def _files_for(stem: str) -> list[Path]:
    files = sorted(SCRIPTED.glob(f"{stem}_*"))
    short = SHORTS / f"{stem}.mp4"
    if short.exists():
        files.append(short)
    return files


def main() -> int:
    move = "--move" in sys.argv
    if not SSD.parent.parent.exists():
        print(f"SSD not mounted: {SSD.parent.parent}", file=sys.stderr)
        return 1

    q = json.loads(pt.QUEUE.read_text(encoding="utf-8"))
    texts = _published_texts()
    print(f"Publer reports {len(texts)} published posts")

    total = 0
    n_move = 0
    published = _match_published(q, texts)
    for e in q:
        if e["stem"] not in published:
            continue
        if e.get("archived_to"):
            continue
        files = _files_for(e["stem"])
        if not files:
            continue
        size = sum(f.stat().st_size for f in files)
        total += size
        n_move += 1
        print(f"  #{e['post_no']:>2} {e['stem']:24} {size / 1e6:7.0f} MB  {len(files)} files")
        if move:
            dest = SSD / e["stem"]
            dest.mkdir(parents=True, exist_ok=True)
            for f in files:
                shutil.move(str(f), str(dest / f.name))
            # status stays "uploaded": plan_posting pins the posting order on
            # that value, and publish_tiktok counts it. archived_to is the
            # only new fact.
            e["archived_to"] = str(dest)
    if move:
        pt.QUEUE.write_text(json.dumps(q, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{'moved' if move else 'would move'} {n_move} fights, {total / 1e9:.2f} GB"
          + ("" if move else "  (add --move)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
