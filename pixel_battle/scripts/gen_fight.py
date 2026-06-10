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
# Comfortable buffers: both fighters are still alive (visibly drained, ~40 HP)
# when the ultimate lands. The ult is a 70-dmg FINISHER, so it KOs the defender
# from anywhere in this band — which frees the combat to vary its rhythm without
# the old "must hit exactly 26 HP at 45.0s" balance breaking.
DEF_REMAIN = 40
ATK_REMAIN = 40

# Champion → movement archetype (mage+marksman collapse to "ranged";
# warrior/tank/duelist to "melee"; assassin is its own hit-and-run profile).
ARCH = {
    # ranged casters/archers/gunners — hold spacing, kite
    "lux": "ranged", "ashe": "ranged", "jinx": "ranged",
    "deadeye": "ranged", "quarrel": "ranged", "pyre": "ranged", "venom": "ranged", "warlock": "ranged",
    "necro": "ranged", "totem": "ranged", "forge": "ranged",
    # assassin — flash in/out
    "katarina": "assassin",
    # melee bruisers/tanks/duelists — advance and trade
    "yasuo": "melee", "garen": "melee", "pantheon": "melee", "mordekaiser": "melee",
    "bulwark": "melee", "ironfist": "melee", "reaver": "melee", "cyclone": "melee",
    "wrecker": "melee", "cleaver": "melee", "outlaw": "melee",
}
L_ARCH, R_ARCH = ARCH.get(LEFT, "melee"), ARCH.get(RIGHT, "melee")
ULT_ADJACENT = VFX in ("slam", "spin", "dash", "melee")   # ult needs to be in close


def _specials(cid):
    """All special (MP-spending) skill ids — damaging first, then buffs/utility,
    so the rotation shows the FULL kit, not just basics + the ultimate."""
    import json
    d = json.load(open("pixel_battle/data/characters.json"))
    sk = [s for s in d[cid]["skills"] if s["type"] == "special"]
    sk.sort(key=lambda s: 0 if s.get("dmg", 0) > 0 else 1)   # damaging first
    return [s["id"] for s in sk]


# Per-archetype PHRASES: (action, gap_after_ms). Tight attack clusters punctuated
# by longer "breath" beats (movement/jump) give each class its own rhythm instead
# of one metronomic 470ms pulse. Phrases loop until the ult approach.
# Phrases mix basic + cd + special-bearing beats so consecutive attacks use
# DIFFERENT animations (a plain swing, then a dash-strike, then a cooldown,
# then a special) instead of the same jab on repeat — and they pump the spacing
# CLOSE (trade) ↔ FAR (kite/reposition) ↔ close instead of locking at one range.
_PHRASES = {
    # archer/mage: fire from range, big hop-back to open distance, poke from afar,
    # then drift in for a closer shot — the gap breathes wide↔mid.
    "ranged": [
        ("attack:basic", 340), ("attack:cd", 380), ("retreat", 360),   # ↗ back off FAR
        ("jump", 380), ("attack:basic", 340),                          # poke from afar
        ("attack:cd", 400), ("advance", 280), ("attack:basic", 340),   # drift to mid, shot
        ("retreat", 340), ("attack:cd", 560),                          # open up again
    ],
    # assassin: hyper-mobile — blink in for a fast flurry, dash-strike, aerial,
    # slide low, vanish FAR, dart back. Range snaps point-blank ↔ way out.
    "assassin": [
        ("flash:in", 190), ("attack:basic", 230), ("attack:cd", 240),  # blink in, cut, dash-cut
        ("attack:basic", 230), ("jump", 250),                          # flurry + aerial
        ("attack:cd", 240), ("crouch", 230),                           # dash-cut, slide low
        ("flash:back", 280),                                           # VANISH far
        ("advance", 200), ("attack:basic", 230), ("attack:cd", 240),   # dart back in
        ("attack:basic", 230), ("jump", 250),
        ("flash:in", 190), ("attack:cd", 240), ("attack:basic", 230),
        ("retreat", 300),
    ],
    # melee: a CLOSE trade cluster (basic+cd+special, varied swings) → disengage
    # to mid → reposition at range → charge back in. The gap pumps in-and-out.
    "melee": [
        ("advance", 240), ("attack:basic", 340), ("attack:cd", 420),   # close: varied trade
        ("attack:basic", 360), ("attack:cd", 400),
        ("retreat", 300), ("retreat", 360), ("jump", 360),             # disengage to mid+air
        ("advance", 240), ("attack:cd", 400), ("attack:basic", 360),   # charge back, cd-first
        ("crouch", 280),                                               # slide low
    ],
}


def side_actions(arch, is_caster, cid):
    """Rhythmic choreography — the archetype's phrase looped. Defenders spend MP
    on real specials for class flavour; casters stay on free actions so MP holds
    at 100 for the ultimate finisher."""
    rows = []
    sp = _specials(cid)
    phrase = _PHRASES.get(arch, _PHRASES["melee"])
    t, pi, si = (400 if is_caster else 700), 0, 0
    end = ULT_T - 700 if is_caster else ULT_T - 500
    # The caster must hold MP=100 for the ult. Melee/assassin casters regain MP
    # fast (many connecting hits) so they can spend on specials then rebuild;
    # ranged casters kite — their MP regen is too slow, so they keep MP for the
    # ult and show variety through their projectile basics + cooldown instead.
    # Defenders need no ult, so they spend freely and often.
    if is_caster:
        cast_until = 0 if arch == "ranged" else (ULT_T - 8500)
    else:
        cast_until = end
    period = 5 if is_caster else 3
    while t < end:
        act, gap = phrase[pi % len(phrase)]
        if sp and act == "attack:basic" and pi % period == period - 1 and t < cast_until:
            act = f"cast:{sp[si % len(sp)]}"; si += 1   # cycle through the whole kit
        rows.append((t, act)); t += gap; pi += 1
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
