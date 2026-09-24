"""Join a TikTok Studio analytics export to the fight plan, and aggregate.

"看觀看數做調整" needs two things the platform does not give you together: the
numbers per video, and what each video WAS — which matchup, which arena, which
hook, which side won, ranged-vs-melee or not. Publer's API exposes no analytics
at all (four endpoints tried, four 404s), so the numbers come from TikTok
Studio's own "下載資料" CSV export, and this script supplies the second half.

Matching is by caption: every fight's caption has a unique first line (gen_captions
enforces it), and TikTok's export carries the video description. Title is tried
first, then the description's first line, then a loose contains-match. Rows
that match nothing are listed, not silently dropped.

Column names are detected by keyword, in Chinese or English, because the export
format has changed before and will again. Override with --col views=<name> etc.

Usage:
  python3 tools/ingest_analytics.py ~/Downloads/tiktok_studio_export.csv
  python3 tools/ingest_analytics.py export.csv --by arena --by hook
  python3 tools/ingest_analytics.py export.csv --col views="影片觀看次數"
  python3 tools/ingest_analytics.py export.csv --json out.json
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTIONS = ROOT / "pixel_battle/output/captions"

# metric -> keywords that identify its column (lowercase, substring match)
KEYS = {
    "title": ["標題", "title", "video title", "影片標題"],
    "desc": ["說明", "描述", "description", "caption", "文案"],
    "views": ["觀看次數", "觀看", "views", "video views", "plays"],
    "likes": ["按讚", "讚", "likes"],
    "comments": ["留言", "評論", "comments"],
    "shares": ["分享", "shares"],
    "watch_s": ["平均觀看時長", "平均觀看", "average watch", "avg watch", "watch time"],
    "completion": ["完播", "watched full", "completion", "full video"],
    "date": ["發布", "日期", "date", "publish", "post time"],
}
DIMS = ["matchup", "arena", "hook", "win_side", "archetypes", "winner"]


def _detect(header: list[str], overrides: dict[str, str]) -> dict[str, str]:
    cols = {}
    low = {h: h.lower() for h in header}
    for metric, kws in KEYS.items():
        if metric in overrides:
            cols[metric] = overrides[metric]
            continue
        for h, hl in low.items():
            if any(k.lower() in hl for k in kws):
                cols[metric] = h
                break
    return cols


def _num(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("%", "")
    m = re.match(r"^-?\d+(\.\d+)?", s)
    if not m:
        return None
    x = float(m.group(0))
    if s.lower().endswith("k"):
        x *= 1e3
    elif s.lower().endswith("m"):
        x *= 1e6
    return x


def _plan() -> list[dict]:
    r = subprocess.run([sys.executable, str(ROOT / "tools/plan_posting.py"), "--json"],
                       cwd=str(ROOT), capture_output=True, text=True)
    plan = json.loads(r.stdout)
    src = (ROOT / "pixel_battle/scripts/gen_fight.py").read_text(encoding="utf-8")
    block = re.search(r"ARCH = \{(.*?)\n\}", src, re.S).group(1)
    arch = dict(re.findall(r'"([a-z_]+)":\s*"(ranged|assassin|melee)"', block))
    ids = {}
    data = json.loads((ROOT / "pixel_battle/data/characters.json").read_text(encoding="utf-8"))
    chars = data.get("characters", data)
    items = chars.items() if isinstance(chars, dict) else [(c["id"], c) for c in chars]
    for cid, e in items:
        ids[str(e.get("display_name", cid))] = cid
    for p in plan:
        cap = CAPTIONS / f"{p['stem']}.txt"
        p["first_line"] = cap.read_text(encoding="utf-8").splitlines()[0].strip() if cap.exists() else ""
        l, rr = ids.get(p["left"], p["left"].lower()), ids.get(p["right"], p["right"].lower())
        p["archetypes"] = "+".join(sorted((arch.get(l, "?"), arch.get(rr, "?"))))
        p["matchup"] = f"{p['left']} vs {p['right']}"
    return plan


def _match(row: dict, cols: dict, plan: list[dict]) -> dict | None:
    title = str(row.get(cols.get("title", ""), "")).strip()
    desc = str(row.get(cols.get("desc", ""), "")).strip()
    first = desc.splitlines()[0].strip() if desc else ""
    for p in plan:
        if p["first_line"] and (p["first_line"] == title or p["first_line"] == first):
            return p
    for p in plan:
        if p["first_line"] and (p["first_line"] in desc or p["first_line"] in title):
            return p
    for p in plan:
        if p["matchup"].lower() in (title + " " + desc).lower():
            return p
    return None


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    path = Path(args[0]).expanduser()
    overrides = {}
    dims = []
    out_json = None
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--col" and i + 1 < len(argv) and "=" in argv[i + 1]:
            k, v = argv[i + 1].split("=", 1)
            overrides[k] = v
        elif a == "--by" and i + 1 < len(argv):
            dims.append(argv[i + 1])
        elif a == "--json" and i + 1 < len(argv):
            out_json = Path(argv[i + 1])
    dims = dims or ["archetypes", "hook", "arena", "win_side"]

    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("empty export", file=sys.stderr)
        return 1
    cols = _detect(list(rows[0].keys()), overrides)
    print("columns:", {k: v for k, v in cols.items()})
    missing = [m for m in ("views",) if m not in cols]
    if missing:
        print(f"could not find a column for {missing}; pass --col views=<header>", file=sys.stderr)
        return 1

    plan = _plan()
    joined, unmatched = [], []
    for row in rows:
        p = _match(row, cols, plan)
        if not p:
            unmatched.append(str(row.get(cols.get("title", ""), row))[:60])
            continue
        rec = {**{d: p.get(d) for d in DIMS}, "stem": p["stem"], "post_no": p["post_no"]}
        for m in ("views", "likes", "comments", "shares", "watch_s", "completion"):
            rec[m] = _num(row.get(cols.get(m, ""))) if m in cols else None
        joined.append(rec)

    print(f"\nmatched {len(joined)}/{len(rows)} rows to fights")
    if unmatched:
        print("unmatched:")
        for u in unmatched[:10]:
            print("  ", u)

    def fmt(x):
        return "-" if x is None else (f"{x:,.0f}" if x >= 100 else f"{x:.2f}")

    for d in dims:
        groups: dict = defaultdict(list)
        for r in joined:
            groups[r.get(d)].append(r)
        print(f"\n=== by {d} ===")
        print(f"  {'group':22} {'n':>3} {'views':>9} {'likes':>7} {'comm':>6} {'share':>6} {'watch_s':>8} {'compl':>6}")
        for g, rs in sorted(groups.items(), key=lambda kv: -sum((x['views'] or 0) for x in kv[1]) / max(1, len(kv[1]))):
            n = len(rs)
            def avg(m):
                v = [x[m] for x in rs if x[m] is not None]
                return sum(v) / len(v) if v else None
            print(f"  {str(g)[:22]:22} {n:>3} {fmt(avg('views')):>9} {fmt(avg('likes')):>7} "
                  f"{fmt(avg('comments')):>6} {fmt(avg('shares')):>6} {fmt(avg('watch_s')):>8} {fmt(avg('completion')):>6}")

    print("\n=== per video ===")
    for r in sorted(joined, key=lambda x: -(x["views"] or 0)):
        print(f"  #{r['post_no']:>2} {r['stem']:24} views={fmt(r['views']):>8} likes={fmt(r['likes']):>6} "
              f"{r['archetypes']:16} {r['hook']:10} {r['arena']}")

    if out_json:
        out_json.write_text(json.dumps(joined, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nwrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
