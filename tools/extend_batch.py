"""Append a new block of fights to gen_batch.BATCH, reproducibly.

The first 21 were picked by hand. That was fine for 21 and is not fine for the
volume the second month needs (two a day, sixty a month): a human choosing sixty
matchups drifts toward favourites, and the drift is invisible until someone
notices the same two champions in every third video.

Selection here is a seeded shuffle with hard vetoes, nothing cleverer — the
posting planner already learned that optimising a regularity metric just
produces a different regularity (see plan_posting.py). Constraints:

  - no pair that already exists in BATCH, in either orientation
  - no ranged-vs-ranged pairing. Ten of ten such fights in block 2 stalled: two
    kiters trade projectiles from opposite walls and nothing reads on a phone.
    This is a content rule, not a bug to fix in the choreography.
  - every roster champion appears at least MIN_APPEARANCES times in the block
  - no champion appears in two consecutive rows
  - arenas cycle so consecutive rows never share one
  - caster side balanced to within one, with no run longer than three
  - every other row is tagged "swap": the caster draws a secondary weapon at
    the second rally (gen_fight --swap). Half, not all, so a swap does not
    become a tell that the fight is about to turn.

brick_phone and glass_slab are excluded: they are the original prototype pair
(a joke about phones), have no weapon and no ARCH entry, and do not belong to
the weapon-codename roster the channel ships.

Usage:
  python3 tools/extend_batch.py --count 30 --seed 22 --dry-run
  python3 tools/extend_batch.py --count 30 --seed 22          # writes into gen_batch.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

# yasuo is out until his kit is reworked. Four block-2 fights with him failed
# pacing through three rounds of engine fixes that cleared every other champion
# (retreat cap, crouch-slide cap, flash-away clamp). His cooldown is a plain
# slash where katarina's is a dash, so after the assassin phrase's flash:back he
# has no beat that closes distance again. That is a kit problem, not a
# choreography one, and it gets fixed in characters.json, not by bending the
# engine further around one champion.
EXCLUDE = {"brick_phone", "glass_slab", "yasuo"}
ARENAS = ["frost", "dusk", "magma", "dojo", "ruins"]
MIN_APPEARANCES = 2
MAX_SIDE_RUN = 3


def _display_short() -> dict[str, str]:
    """id -> the short display token used in stems, learned from existing rows."""
    from gen_batch import BATCH
    short: dict[str, str] = {}
    for stem, left, right, _, _, *_tags in BATCH:
        parts = stem.split("_", 1)[1].split("_")
        if len(parts) == 2:
            short.setdefault(left, parts[0])
            short.setdefault(right, parts[1])
    # Anything not yet seen falls back to its display name, lowercased.
    data = json.loads((ROOT / "pixel_battle/data/characters.json").read_text(encoding="utf-8"))
    chars = data.get("characters", data)
    items = chars.items() if isinstance(chars, dict) else [(c["id"], c) for c in chars]
    for cid, entry in items:
        short.setdefault(cid, str(entry.get("display_name", cid)).lower().replace(" ", ""))
    return short


def _arch() -> dict[str, str]:
    """champion id -> archetype, read from gen_fight's ARCH so the two agree."""
    src = (ROOT / "pixel_battle/scripts/gen_fight.py").read_text(encoding="utf-8")
    block = re.search(r"ARCH = \{(.*?)\n\}", src, re.S).group(1)
    return dict(re.findall(r'"([a-z_]+)":\s*"(ranged|assassin|melee)"', block))


def _roster() -> list[str]:
    data = json.loads((ROOT / "pixel_battle/data/characters.json").read_text(encoding="utf-8"))
    chars = data.get("characters", data)
    ids = list(chars.keys()) if isinstance(chars, dict) else [c["id"] for c in chars]
    return [i for i in ids if i not in EXCLUDE]


def select(count: int, seed: int) -> list[tuple]:
    from gen_batch import BATCH
    rng = random.Random(seed)
    roster = _roster()
    used = {frozenset((r[1], r[2])) for r in BATCH}
    start_no = len(BATCH) + 1
    short = _display_short()

    arch = _arch()
    pool = [(a, b) for i, a in enumerate(roster) for b in roster[i + 1:]
            if frozenset((a, b)) not in used
            and not (arch.get(a) == "ranged" and arch.get(b) == "ranged")]
    rng.shuffle(pool)

    rows: list[tuple[str, str]] = []
    appear: Counter = Counter()

    # Pass 1: greedy fill honouring "no champion in consecutive rows".
    # Pass 2 (below) repairs under-represented champions by swapping.
    for a, b in pool:
        if len(rows) >= count:
            break
        if rows and (a in rows[-1] or b in rows[-1]):
            continue
        rows.append((a, b))
        appear[a] += 1
        appear[b] += 1

    for cid in roster:
        while appear[cid] < MIN_APPEARANCES:
            # Replace the row whose two champions are most over-represented,
            # with a fresh unused pair containing cid.
            cand = [(a, b) for a, b in pool if cid in (a, b)
                    and (a, b) not in rows and (b, a) not in rows]
            if not cand:
                break
            worst_i = max(range(len(rows)),
                          key=lambda i: appear[rows[i][0]] + appear[rows[i][1]])
            old = rows[worst_i]
            appear[old[0]] -= 1
            appear[old[1]] -= 1
            new = cand[0]
            rows[worst_i] = new
            appear[new[0]] += 1
            appear[new[1]] += 1

    # Orientation: shuffle which champion stands left, so "left" is not always
    # the roster-earlier one.
    rows = [(b, a) if rng.random() < 0.5 else (a, b) for a, b in rows]

    # Arenas: cycle, offset by a random start, never repeating a neighbour.
    arena_i = rng.randrange(len(ARENAS))
    arenas = []
    for _ in rows:
        arenas.append(ARENAS[arena_i % len(ARENAS)])
        arena_i += 1

    # Caster side: balanced, no run longer than MAX_SIDE_RUN.
    sides = ["left"] * (count // 2) + ["right"] * (count - count // 2)
    for _ in range(200):
        rng.shuffle(sides)
        ok, run = True, 1
        for i in range(1, len(sides)):
            run = run + 1 if sides[i] == sides[i - 1] else 1
            if run > MAX_SIDE_RUN:
                ok = False
                break
        if ok:
            break

    out = []
    for i, ((left, right), arena, side) in enumerate(zip(rows, arenas, sides)):
        stem = f"b{start_no + i:02d}_{short[left]}_{short[right]}"
        row = (stem, left, right, arena, side)
        if i % 2 == 0:
            row += ("swap",)
        out.append(row)
    return out


def _stem_no(stem: str) -> str:
    """'b52_frostbow_wrecker' -> 'b52'; works past b99 where [:3] does not."""
    return stem.split("_", 1)[0]


def _block_header(rows, seed: int) -> str:
    # Block 1 (hand-picked) carries no header; every generated block does.
    src = (ROOT / "tools/gen_batch.py").read_text(encoding="utf-8")
    n = src.count("# ── Block ") + 2
    return (f"    # ── Block {n} ({_stem_no(rows[0][0])}-{_stem_no(rows[-1][0])}), "
            f"selected by tools/extend_batch.py --seed {seed} ──")


def _format(rows, seed: int) -> str:
    lines = [_block_header(rows, seed)]
    for stem, left, right, arena, side, *tags in rows:
        line = (f'    ("{stem}",'.ljust(30) + f'"{left}",'.ljust(15)
                + f'"{right}",'.ljust(15) + f'"{arena}",'.ljust(9) + f'"{side}"')
        line += "".join(f', "{t}"' for t in tags) + "),"
        lines.append(line)
    return "\n".join(lines)


def main() -> int:
    count = int(sys.argv[sys.argv.index("--count") + 1]) if "--count" in sys.argv else 30
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 22
    rows = select(count, seed)
    block = _format(rows, seed)

    appear: Counter = Counter()
    for _, l, r, _, _, *_tags in rows:
        appear[l] += 1
        appear[r] += 1
    n_left = sum(1 for r in rows if r[4] == "left")
    print(block)
    n_swap = sum(1 for r in rows if "swap" in r[5:])
    print(f"\n{len(rows)} fights · left {n_left} / right {len(rows) - n_left}"
          f" · appearances min {min(appear.values())} max {max(appear.values())}"
          f" · champions covered {len(appear)}/{len(_roster())} · swaps {n_swap}")

    if "--dry-run" in sys.argv:
        return 0
    p = ROOT / "tools/gen_batch.py"
    s = p.read_text(encoding="utf-8")
    m = re.search(r"^BATCH = \[\n(.*?)^\]", s, re.S | re.M)
    if not m:
        print("could not find BATCH in gen_batch.py", file=sys.stderr)
        return 1
    if block.splitlines()[0] in s:
        print("that block is already present; refusing to append twice", file=sys.stderr)
        return 1
    s = s[:m.end() - 1] + block + "\n" + s[m.end() - 1:]
    p.write_text(s, encoding="utf-8")
    print(f"\nappended to {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
