"""Write one TikTok caption per fight, following the posting plan's hook rotation.

Conventions borrowed from the nihongo-reels pipeline, which has been posting to
TikTok daily since April 2026:
  - the first line is a curiosity hook and decides retention; it is the one part
    that must never be templated across the run
  - short hashtag stack, region tag at the end
  - no heavy call-to-action in the last line (it costs completion rate)

Every caption also carries the music attribution: the BGM is Kevin MacLeod's
"Crusade", which is CC-BY and requires credit.

Captions deliberately contain NO brand name — the handle and bio carry identity,
and inventing a name here would bake a placeholder into files later steps read.

Usage:
  python3 tools/gen_captions.py                 # print all (English)
  python3 tools/gen_captions.py --lang zh       # the original Chinese set
  python3 tools/gen_captions.py --write DIR     # one <stem>.txt per fight
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MUSIC_CREDIT = ("音樂：Crusade – Kevin MacLeod (incompetech.com)\n"
                "Licensed under Creative Commons: By Attribution 4.0")
MUSIC_CREDIT_EN = ("Music: Crusade – Kevin MacLeod (incompetech.com)\n"
                   "Licensed under Creative Commons: By Attribution 4.0")

TAG_REGION = "#fyp #台灣"
# English-first from 2026-09-19. No #台灣 here: the zh stack was aimed at a
# Taiwan feed, and keeping it would split the signal TikTok reads from the post.
TAG_REGION_EN = "#fyp #foryou"


def _ult_display(cid: str) -> str:
    data = json.loads((ROOT / "pixel_battle/data/characters.json")
                      .read_text(encoding="utf-8"))
    chars = data.get("characters", data)
    entry = chars[cid] if isinstance(chars, dict) else \
        next(c for c in chars if c.get("id") == cid)
    skills = entry["skills"]
    u = next((s for s in skills if s.get("type") == "ultimate"), skills[-1])
    return u["id"].replace("_", " ").upper()


def _char_id(display: str) -> str:
    data = json.loads((ROOT / "pixel_battle/data/characters.json")
                      .read_text(encoding="utf-8"))
    chars = data.get("characters", data)
    items = chars.items() if isinstance(chars, dict) else \
        [(c["id"], c) for c in chars]
    for k, v in items:
        if v.get("display_name") == display:
            return k
    return display.lower()


# One builder per hook type. Each returns the first line only; the tag block is
# appended by build(). Keeping them separate is what stops the run reading as one
# template with the nouns swapped.
def _hook_en(kind: str, f: dict) -> str:
    """English first lines. Same two rules as _hook: every line carries the
    matchup so none collide, and none of them name the loser."""
    vs = f"{f['left']} vs {f['right']}"
    ult = _ult_display(_char_id(f["winner"]))
    if kind == "question":
        return f"{f['left']} or {f['right']} — who takes it?\nAnswer in the last 5 seconds"
    if kind == "underdog":
        return f"{vs}\nLooks one-sided. It is not."
    if kind == "character":
        return f"{vs}: one {ult} ended the whole thing"
    if kind == "arena":
        return f"{vs} in {f['arena_en']}\nSettled in 53 seconds"
    if kind == "pacing":
        return f"{vs} went down to the last sliver of health"
    if kind == "callout":
        return f"{vs} — the comments are going to argue about this one"
    raise ValueError(f"unknown hook {kind}")


def _hook(kind: str, f: dict) -> str:
    """First line per hook type.

    Two rules learned the hard way while writing these:

    1. Every hook must carry the matchup, because the first line decides
       retention and must be unique across the run. An earlier "pacing" hook
       opened with a fixed sentence and collided three times; so did
       "callout". The duplicate check below is a hard failure, not a warning.
    2. No hook names who LOSES. Saying "everyone thought X had it" gives the
       result away in the caption, which is the one thing the videos are built
       to withhold until the last five seconds. The winner's ultimate is named
       in some hooks, but the cover already prints it, so that leaks nothing new.
    """
    vs = f"{f['left']} vs {f['right']}"
    ult = _ult_display(_char_id(f["winner"]))
    if kind == "question":
        return f"{f['left']} 對上 {f['right']}，你押誰？\n答案在最後 5 秒"
    if kind == "underdog":
        return f"{vs}\n看起來一面倒，其實沒有"
    if kind == "character":
        # Matchup on the FIRST line. The opening line is the uniqueness key, and
        # two fights won by the same champion with this hook produced the same
        # line ("One SKYFALL ended the whole thing", b13 and b36) once the roster
        # grew past 21.
        return f"{vs}：一招 {ult} 直接收掉整場"
    if kind == "arena":
        # Same rule as the character hook: the matchup rides on line 1. Five
        # arenas across 51 fights means the arena alone repeats.
        return f"{vs}，在{f['arena_zh']}\n53 秒分勝負"
    if kind == "pacing":
        return f"{vs} 打到剩最後一格血"
    if kind == "callout":
        return f"{vs}，這場結果留言區一定吵"
    raise ValueError(f"unknown hook {kind}")


def build(f: dict, lang: str = "en") -> str:
    if lang == "en":
        tags = " ".join(f["tags_en"])
        return (f"{_hook_en(f['hook'], f)}\n\n{tags} {TAG_REGION_EN}"
                f"\n\n{MUSIC_CREDIT_EN}")
    tags = " ".join(f["tags"])
    return f"{_hook(f['hook'], f)}\n\n{tags} {TAG_REGION}\n\n{MUSIC_CREDIT}"


def main() -> int:
    out = subprocess.run([sys.executable, str(ROOT / "tools/plan_posting.py"),
                          "--json"], capture_output=True, text=True, cwd=str(ROOT))
    if out.returncode != 0:
        raise SystemExit(f"plan_posting failed:\n{out.stderr}")
    plan = json.loads(out.stdout)

    lang = "en"
    if "--lang" in sys.argv:
        lang = sys.argv[sys.argv.index("--lang") + 1]
        if lang not in ("en", "zh"):
            raise SystemExit("--lang takes en or zh")

    write_dir = None
    if "--write" in sys.argv:
        i = sys.argv.index("--write")
        write_dir = Path(sys.argv[i + 1]) if i + 1 < len(sys.argv) else None
        if write_dir is None:
            raise SystemExit("--write needs a directory")
        write_dir.mkdir(parents=True, exist_ok=True)

    firsts = set()
    for f in plan:
        cap = build(f, lang)
        first = cap.split("\n")[0]
        if first in firsts:
            raise SystemExit(f"duplicate first line across the run: {first!r} "
                             f"(at {f['stem']}). The opening line decides "
                             f"retention; it must be unique per video.")
        firsts.add(first)
        if write_dir:
            (write_dir / f"{f['stem']}.txt").write_text(cap, encoding="utf-8")
        else:
            print(f"--- #{f['post_no']} {f['stem']} [{f['hook']}]")
            print(cap)
            print()
    if write_dir:
        print(f"wrote {len(plan)} captions to {write_dir}")
    print(f"unique first lines: {len(firsts)}/{len(plan)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
