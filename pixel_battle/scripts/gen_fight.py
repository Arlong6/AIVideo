"""Auto-tuned LONG fight generator (~50s) for the shorts batch.

A 40-60s fight must keep BOTH bars draining the whole time and leave the
defender just low enough that the ultimate finishes them. Hand-tuning HP per
matchup is brittle, so we measure: build the timeline, run a pure-sim with both
fighters at 999 HP, record how much damage each side has taken right before the
ult fires, then set starting HP so the defender lands at ~DEF_REMAIN (ult KOs)
and the caster survives with ~ATK_REMAIN. Deterministic (fixed seed) so the
measurement matches the render.

Usage: python -m pixel_battle.scripts.gen_fight <left> <right> <ult_id> <vfx> <melee:0|1> <out.yaml> [ult_ms]
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

LEFT, RIGHT, ULT_ID, VFX, MELEE, OUT = (
    sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] == "1", sys.argv[6])
ULT_T = int(sys.argv[7]) if len(sys.argv) > 7 else 45000
SEED = 7
DEF_REMAIN = 26   # defender HP just before the ult → ult (~30-32) KOs
ATK_REMAIN = 24   # caster survives the exchange with this much

# ── Build timelines (caster = left, FREE actions only so MP stays 100) ──────────
def build():
    left, right = [], []
    if MELEE:
        lpat = ["advance", "attack:basic", "attack:cd", "advance", "attack:basic",
                "jump", "advance", "attack:basic", "advance", "attack:cd"]
        flash_act, flash_period = "flash:in", 6000
    else:
        lpat = ["retreat", "attack:basic", "jump", "retreat", "attack:cd",
                "advance", "attack:basic", "retreat", "jump", "attack:cd"]
        flash_act, flash_period = "flash:back", 6500
    l_flash = list(range(2500, ULT_T - 1500, flash_period))
    t, pi, lf = 400, 0, set()
    while t < ULT_T - 700:
        ff = next((f for f in l_flash if f not in lf and abs(f - t) < 300), None)
        if ff is not None:
            left.append((ff, flash_act)); lf.add(ff); t = ff + 520; continue
        left.append((t, lpat[pi % len(lpat)])); pi += 1; t += 470
    if MELEE:
        left.append((ULT_T - 650, "flash:in")); left.append((ULT_T - 160, "advance"))
    else:
        left.append((ULT_T - 650, "retreat"))
    left.append((ULT_T, f"cast:{ULT_ID}"))

    # Defender: PRESSURES forward (never retreats — two retreating fighters wall
    # off to opposite sides and never trade). Periodic flash:in guarantees it
    # closes on a kiting caster even when a champion's advance step stalls
    # against the wall (yasuo's short steps + self-rooting attacks otherwise
    # leave a permanent ~290px gap and zero contact).
    rpat = ["advance", "attack:basic", "advance", "attack:cd", "advance",
            "attack:basic", "jump", "advance", "attack:basic", "attack:cd",
            "advance", "attack:basic"]
    r_flash = list(range(2000, ULT_T - 800, 4000))
    t, pi, rf = 700, 0, set()
    while t < ULT_T - 500:
        ff = next((f for f in r_flash if f not in rf and abs(f - t) < 320), None)
        if ff is not None:
            right.append((ff, "flash:in")); rf.add(ff); t = ff + 500; continue
        right.append((t, rpat[pi % len(rpat)])); pi += 1; t += 470
    return left, right


def emit(rows):
    rows = sorted(rows, key=lambda r: r[0])
    return "\n".join(f'  - {{t: {a}, do: "{b}"}}' if ":" in b
                     else f'  - {{t: {a}, do: {b}}}' for a, b in rows)


def write_yaml(left, right, lhp, rhp):
    hp_lines = ""
    if lhp is not None: hp_lines += f"left_start_hp: {lhp}\n"
    if rhp is not None: hp_lines += f"right_start_hp: {rhp}\n"
    yaml = f'''# {LEFT} vs {RIGHT} — LONG (~{ULT_T//1000+6}s), {ULT_ID} climax · auto-tuned HP
name: "{LEFT} vs {RIGHT} — long ({ULT_ID})"
left: {LEFT}
right: {RIGHT}
duration_ms: {ULT_T + 8000}
seed: {SEED}
left_start_mp: 100
{hp_lines}left_timeline:
{emit(left)}
right_timeline:
{emit(right)}
'''
    Path(OUT).write_text(yaml, encoding="utf-8")


# ── Measure: 999 HP both, record damage taken by each side just before the ult ──
def measure():
    from pixel_battle.rl.env import PixelBattleEnv
    from pixel_battle.script.loader import load_fight_file
    d = load_fight_file(OUT)
    env = PixelBattleEnv(left_id=LEFT, right_id=RIGHT, seed=SEED); env.reset()
    b = env.battle
    b.left.mp = 100
    for f in (b.left, b.right):
        f.hp = 999
        if hasattr(f, "hp_max"): f.hp_max = 999
    L, R = b.left, b.right
    pre_l, pre_r = L.hp, R.hp
    for _ in range(int((ULT_T + 6000) / 16) + 50):
        la, ra = d.decide(b)
        # snapshot hp at the last tick BEFORE the scheduled ult time — robust
        # regardless of how/when the cast resolves.
        if b.elapsed_ms < ULT_T:
            pre_l, pre_r = L.hp, R.hp
        else:
            break
        env.step((la, ra))
    return 999 - pre_l, 999 - pre_r          # damage taken by left, by right


def main():
    left, right = build()
    write_yaml(left, right, None, None)       # provisional (default 30 HP)
    dmg_left, dmg_right = measure()
    lhp = round(dmg_left + ATK_REMAIN)
    rhp = round(dmg_right + DEF_REMAIN)
    write_yaml(left, right, lhp, rhp)
    print(f"  {OUT.split('/')[-1]}: ult {ULT_ID}@{ULT_T/1000:.0f}s  "
          f"dmg L={dmg_left:.0f} R={dmg_right:.0f}  ->  Lhp={lhp} Rhp={rhp}")


if __name__ == "__main__":
    main()
