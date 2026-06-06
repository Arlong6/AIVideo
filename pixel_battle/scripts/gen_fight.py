"""Auto-tuned, ARCHETYPE-AWARE long fight generator (~50s) for the shorts batch.

Each champion plays to its class so mage / assassin / warrior never blur together:
  - ranged  (mage, marksman): hold spacing, fire free ranged basics + cooldowns,
              NEVER walk into melee. Reads as a caster/archer kiting.
  - assassin: flash IN, blade combo, dash OUT — hit-and-run at the edge of melee.
  - melee   (warrior, tank, duelist): march forward and trade strikes / slams.

The ult caster (left) uses only FREE actions (basic / cooldown / flash / move) so
MP stays 100 for the ult; the defender (right) may spend MP on its specials. HP is
auto-tuned by measuring (999-HP pure-sim) how much each side takes by the ult, so
both bars drain all fight and the defender lands ~DEF_REMAIN for the ult to KO.

Usage: python -m pixel_battle.scripts.gen_fight <left> <right> <ult_id> <vfx> <_> <out.yaml> [ult_ms]
(the 5th arg is kept for call-compat; melee-approach is derived from <vfx>.)
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

LEFT, RIGHT, ULT_ID, VFX, _MEL, OUT = (
    sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
ULT_T = int(sys.argv[7]) if len(sys.argv) > 7 else 45000
SEED = 7
DEF_REMAIN = 26
ATK_REMAIN = 24

# Champion → movement archetype (mage+marksman collapse to "ranged";
# warrior/tank/duelist to "melee"; assassin is its own hit-and-run profile).
ARCH = {
    # ranged casters/archers/gunners — hold spacing, kite
    "lux": "ranged", "ashe": "ranged", "jinx": "ranged",
    "deadeye": "ranged", "quarrel": "ranged", "pyre": "ranged", "venom": "ranged",
    # assassin — flash in/out
    "katarina": "assassin",
    # melee bruisers/tanks/duelists — advance and trade
    "yasuo": "melee", "garen": "melee", "pantheon": "melee", "mordekaiser": "melee",
    "bulwark": "melee", "ironfist": "melee", "reaver": "melee", "cyclone": "melee",
    "wrecker": "melee", "cleaver": "melee",
}
L_ARCH, R_ARCH = ARCH.get(LEFT, "melee"), ARCH.get(RIGHT, "melee")
ULT_ADJACENT = VFX in ("slam", "spin", "dash", "melee")   # ult needs to be in close


def _specials(cid):
    """Damaging special skill ids for a champion (defender spends MP on these)."""
    import json
    d = json.load(open("pixel_battle/data/characters.json"))
    return [s["id"] for s in d[cid]["skills"]
            if s["type"] == "special" and s.get("dmg", 0) > 0]


def side_actions(arch, is_caster, cid):
    """Build (t, action) rows for one fighter, in its archetype's idiom."""
    rows = []
    sp = _specials(cid)
    cast = (lambda i: f"cast:{sp[i % len(sp)]}") if sp else (lambda i: "attack:cd")

    if arch == "ranged":
        # Stand and trade ranged basics/cooldowns from the spawn spacing (~280px,
        # inside the 300px ranged-basic reach). NO retreat/flash — two retreating
        # casters wall off to opposite sides and every shot whiffs.
        base = ["attack:basic", "attack:cd", "attack:basic", "jump",
                "attack:basic", "attack:cd", "attack:basic", "jump"]
        flash, fperiod = "", 0
    elif arch == "assassin":
        base = ["flash:in", "attack:basic", "attack:cd", "attack:basic", "retreat",
                "advance", "attack:basic", "jump", "attack:cd", "retreat"]
        flash, fperiod = "flash:in", 3600
    else:  # melee
        base = ["advance", "attack:basic", "attack:cd", "advance", "attack:basic",
                "jump", "advance", "attack:basic", "advance", "attack:cd"]
        flash, fperiod = "flash:in", 5200

    flashes = list(range(2200, ULT_T - 1500, fperiod)) if flash else []
    t, pi, used = (400 if is_caster else 700), 0, set()
    end = ULT_T - 700 if is_caster else ULT_T - 500
    while t < end:
        ff = next((f for f in flashes if f not in used and abs(f - t) < 320), None)
        if ff is not None:
            rows.append((ff, flash)); used.add(ff); t = ff + 520; continue
        act = base[pi % len(base)]
        # Defender (MP-free) sprinkles real specials for class flavor.
        if (not is_caster) and act == "attack:basic" and pi % 3 == 2:
            act = cast(pi)
        rows.append((t, act)); pi += 1; t += 470
    return rows


def build():
    left = side_actions(L_ARCH, True, LEFT)
    # Caster ult approach: melee/spin/dash ults need adjacency → flash in first;
    # ranged ults fire from current spacing.
    if ULT_ADJACENT:
        left.append((ULT_T - 640, "flash:in")); left.append((ULT_T - 160, "advance"))
    else:
        left.append((ULT_T - 600, "attack:basic"))   # keep poking at range
    left.append((ULT_T, f"cast:{ULT_ID}"))
    right = side_actions(R_ARCH, False, RIGHT)
    return left, right


def emit(rows):
    rows = sorted(rows, key=lambda r: r[0])
    return "\n".join(f'  - {{t: {a}, do: "{b}"}}' if ":" in b
                     else f'  - {{t: {a}, do: {b}}}' for a, b in rows)


def write_yaml(left, right, lhp, rhp):
    hp = ""
    if lhp is not None: hp += f"left_start_hp: {lhp}\n"
    if rhp is not None: hp += f"right_start_hp: {rhp}\n"
    Path(OUT).write_text(
        f'''# {LEFT}({L_ARCH}) vs {RIGHT}({R_ARCH}) — LONG ~{ULT_T//1000+6}s · {ULT_ID} climax · auto-tuned
name: "{LEFT} vs {RIGHT} — long ({ULT_ID})"
left: {LEFT}
right: {RIGHT}
duration_ms: {ULT_T + 8000}
seed: {SEED}
left_start_mp: 100
{hp}left_timeline:
{emit(left)}
right_timeline:
{emit(right)}
''', encoding="utf-8")


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
        if b.elapsed_ms < ULT_T:
            pre_l, pre_r = L.hp, R.hp
        else:
            break
        env.step((la, ra))
    return 999 - pre_l, 999 - pre_r


def main():
    left, right = build()
    write_yaml(left, right, None, None)
    dmg_l, dmg_r = measure()
    lhp, rhp = round(dmg_l + ATK_REMAIN), round(dmg_r + DEF_REMAIN)
    write_yaml(left, right, lhp, rhp)
    print(f"  {OUT.split('/')[-1]}: {LEFT}({L_ARCH}) vs {RIGHT}({R_ARCH}) "
          f"ult {ULT_ID}/{VFX}@{ULT_T/1000:.0f}s  dmg L={dmg_l:.0f} R={dmg_r:.0f}"
          f"  -> Lhp={lhp} Rhp={rhp}")


if __name__ == "__main__":
    main()
