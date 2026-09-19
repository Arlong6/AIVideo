"""Build a posting order for the b01-b21 shorts that does not look mass-produced.

TikTok's enforcement signal with documented backing is CONTENT, not cadence:
"Using automation to run many accounts or send repetitive content". A 21-video
run of the same matchup format is exactly the shape that reads as templated, so
the schedule below deliberately varies, between consecutive posts:

  - which SIDE of the screen wins (a viewer who spots "left always wins" stops
    guessing, and the comment-bait CTA dies with it)
  - the arena, so the backdrop changes
  - the archetype matchup (ranged/melee/assassin)
  - the caption hook structure, so no two posts open the same way

Deterministic: same inputs always produce the same schedule, so the plan can be
regenerated and diffed rather than being a one-off.

Usage:
  python3 tools/plan_posting.py            # print the schedule
  python3 tools/plan_posting.py --json     # machine-readable
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

ARENA_ZH = {"frost": "霜原", "dusk": "暮色", "magma": "熔岩",
            "dojo": "道場", "ruins": "遺跡"}

# English arena wording, phrased to drop straight into a sentence. The channel
# went English-first on 2026-09-19; the zh names stay so nothing that already
# reads them breaks.
ARENA_EN = {"frost": "the frostfield", "dusk": "the dusk arena",
            "magma": "the magma pit", "dojo": "the dojo", "ruins": "the ruins"}
ARCH = {
    "lux": "ranged", "ashe": "ranged", "jinx": "ranged", "deadeye": "ranged",
    "quarrel": "ranged", "pyre": "ranged", "venom": "ranged", "warlock": "ranged",
    "necro": "ranged", "totem": "ranged", "forge": "ranged", "katarina": "assassin",
    "yasuo": "melee", "garen": "melee", "pantheon": "melee", "mordekaiser": "melee",
    "bulwark": "melee", "ironfist": "melee", "reaver": "melee", "cyclone": "melee",
    "wrecker": "melee", "cleaver": "melee", "outlaw": "melee",
}

# Six opening structures. Consecutive posts never reuse one, so the first line a
# viewer reads is not the same shape every time.
HOOKS = [
    ("question",  "問句開場 — 直接問誰會贏，收留言"),
    ("underdog",  "反直覺開場 — 點出誰看起來會輸"),
    ("character", "角色聚焦 — 從勝方的招式切入"),
    ("arena",     "場地開場 — 從場景寫起"),
    ("pacing",    "賽況開場 — 強調最後一招才分勝負"),
    ("callout",   "挑釁開場 — 對留言區的預測下戰帖"),
]

# Three tag pools. Rotating them keeps the tag block from being byte-identical
# across the run, which is part of what makes a series look automated.
TAG_POOLS = [
    ["#火柴人", "#格鬥", "#誰會贏", "#stickman"],
    ["#火柴人動畫", "#對戰", "#像素", "#stickfight"],
    ["#火柴人", "#一對一", "#動畫", "#animation"],
]

# English pools, rotated the same way. No #fyp/#foryou here — gen_captions
# appends those, and a repeated tag in one stack is wasted space.
TAG_POOLS_EN = [
    ["#stickman", "#stickfight", "#whowins", "#animation"],
    ["#stickmanfight", "#fightscene", "#pixelart", "#1v1"],
    ["#stickman", "#stickbattle", "#animation", "#fightanimation"],
]


def _display_names() -> dict:
    data = json.loads((ROOT / "pixel_battle/data/characters.json")
                      .read_text(encoding="utf-8"))
    chars = data.get("characters", data)
    items = chars.items() if isinstance(chars, dict) else \
        [(c["id"], c) for c in chars]
    return {k: v.get("display_name", k) for k, v in items}


def _fights() -> list[dict]:
    from gen_batch import BATCH
    names = _display_names()
    out = []
    for stem, left, right, arena, caster in BATCH:
        win, lose = (left, right) if caster == "left" else (right, left)
        out.append({
            "stem": stem, "arena": arena, "arena_zh": ARENA_ZH[arena],
            "arena_en": ARENA_EN[arena],
            "win_side": caster,
            "left": names.get(left, left), "right": names.get(right, right),
            "winner": names.get(win, win), "loser": names.get(lose, lose),
            "matchup": f"{ARCH.get(left,'melee')}/{ARCH.get(right,'melee')}",
        })
    return out


def _sides(seq: list[dict]) -> str:
    return "".join("L" if f["win_side"] == "left" else "R" for f in seq)


def _violations(seq: list[dict]) -> int:
    """Count only HARD problems, never "how random does this look".

    Two earlier attempts optimised a regularity score and both collapsed into a
    pattern: penalising every same-side neighbour produced LRLRLR..., and then
    rewarding runs of two produced LLRRLLRR... Any deterministic search that
    minimises a smoothness metric lands on some periodic optimum, which is
    exactly the predictability being designed out. So the order comes from a
    seeded shuffle and this function only rejects the genuinely bad shapes.
    """
    v = 0
    s = _sides(seq)
    runs, cur = [], 1
    for a, b in zip(s, s[1:]):
        if a == b:
            cur += 1
        else:
            runs.append(cur); cur = 1
    runs.append(cur)
    v += sum(1 for r in runs if r >= 4)               # 4 same-side wins in a row

    # Local balance. Run-length alone missed a real failure: a draw could open
    # LLLRLLLRLLL and close RRLRRRLRRR — no long run anywhere, yet the first ten
    # posts (the ones that set a new account's impression) were almost all
    # left-side wins. Every 8-post window must stay inside 3..5 of each side.
    for i in range(len(s) - 7):
        w = s[i:i + 8]
        if not 3 <= w.count("L") <= 5:
            v += 1
    for a, b in zip(seq, seq[1:]):
        if a["arena"] == b["arena"]:
            v += 1                                    # same backdrop twice running
        if a["matchup"] == b["matchup"] and a["arena"] == b["arena"]:
            v += 1
    return v


def _order(fights: list[dict], seed: int = 20260913) -> list[dict]:
    """Seeded shuffle, keeping the first draw that has no hard violations.

    Deterministic (fixed seed) so the plan is reproducible and diffable, but the
    sequence itself is random rather than optimised — no period for a viewer to
    latch onto.
    """
    import random

    rng = random.Random(seed)
    # b01 is pinned first: it is the fight already reviewed and packaged, so the
    # debut post is a known-good one rather than whatever the shuffle picks.
    pinned = [f for f in fights if f["stem"].startswith("b01")]
    rest = [f for f in fights if not f["stem"].startswith("b01")]
    best, best_v = None, None
    for _ in range(4000):
        trial = rest[:]
        rng.shuffle(trial)
        trial = pinned + trial
        v = _violations(trial)
        if best_v is None or v < best_v:
            best, best_v = trial, v
        if v == 0:
            return trial
    return best


def main() -> int:
    seq = _order(_fights())
    plan = []
    for n, f in enumerate(seq):
        plan.append({**f, "post_no": n + 1,
                     "hook": HOOKS[n % len(HOOKS)][0],
                     "hook_zh": HOOKS[n % len(HOOKS)][1],
                     "tags": TAG_POOLS[n % len(TAG_POOLS)],
                  "tags_en": TAG_POOLS_EN[n % len(TAG_POOLS_EN)]})

    if "--json" in sys.argv:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    print(f"{'#':>3} {'fight':24}{'對戰':26}{'勝方':11}{'側':6}{'場地':6}{'開場結構'}")
    for p in plan:
        vs = f"{p['left']} vs {p['right']}"
        print(f"{p['post_no']:>3} {p['stem']:24}{vs:26}{p['winner']:11}"
              f"{p['win_side']:6}{p['arena_zh']:6}{p['hook_zh']}")

    sides = _sides(seq)
    print(f"\n勝方側序列: {sides}")
    runs, cur = [], 1
    for a, b in zip(sides, sides[1:]):
        if a == b:
            cur += 1
        else:
            runs.append(cur); cur = 1
    runs.append(cur)
    alt = best = 1
    for a, b in zip(sides, sides[1:]):
        alt = 1 if a == b else alt + 1
        best = max(best, alt)
    print(f"最長連續同側: {max(runs)}  |  最長交替段: {best}  |  相鄰同場地: "
          f"{sum(1 for a,b in zip(plan,plan[1:]) if a['arena']==b['arena'])}  |  "
          f"相鄰同開場: {sum(1 for a,b in zip(plan,plan[1:]) if a['hook']==b['hook'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
