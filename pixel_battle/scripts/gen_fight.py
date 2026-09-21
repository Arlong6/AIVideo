"""Auto-tuned, ARCHETYPE-AWARE long fight generator (~50s) for the shorts batch.

Each champion plays to its class so mage / assassin / warrior never blur together:
  - ranged  (mage, marksman): hold spacing, fire free ranged basics + cooldowns,
              NEVER walk into melee. Reads as a caster/archer kiting.
  - assassin: flash IN, blade combo, dash OUT — hit-and-run at the edge of melee.
  - melee   (warrior, tank, duelist): march forward and trade strikes / slams.

The ult caster (LEFT by default, RIGHT with --caster-right) uses only FREE actions (basic / cooldown / flash / move) so
MP stays 100 for the ult; the defender (right) may spend MP on its specials. HP is
auto-tuned by measuring (999-HP pure-sim) how much each side takes by the ult, so
both bars drain all fight and the defender lands ~DEF_REMAIN for the ult to KO.

Usage: python -m pixel_battle.scripts.gen_fight <left> <right> <ult_id> <vfx> <_> <out.yaml> [ult_ms]
       [--caster-right]  — mirror the roles so the RIGHT fighter casts the finisher and wins
(the 5th arg is kept for call-compat; melee-approach is derived from <vfx>.)
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

# --caster-right mirrors the roles: the RIGHT fighter becomes the ult caster and
# therefore the winner. Without it the LEFT fighter casts the finisher and wins —
# which, applied to a whole batch, makes every fight end the same way and kills the
# "who wins?" hook. Stripped from argv here so the positional contract is unchanged.
_argv = [a for a in sys.argv if a != "--caster-right"]
CASTER = "right" if len(_argv) != len(sys.argv) else "left"

LEFT, RIGHT, ULT_ID, VFX, _MEL, OUT = (
    _argv[1], _argv[2], _argv[3], _argv[4], _argv[5], _argv[6])
ULT_T = int(_argv[7]) if len(_argv) > 7 else 45000
SEED = 7

# How far to offset the defender's phrase in a mirror match, as a fraction of the
# phrase. There is no single right answer: half a phrase fixes b11 and leaves b09
# stalling, a third fixes b09 and breaks b11. The two pairings simply interlock
# at different points. So this is a starting value and main() searches the
# candidates below, keeping whichever produces the smallest silent gap — the same
# measure-then-choose approach the HP budget already uses.
MIRROR_OFFSET = 0.5
MIRROR_CANDIDATES = (0.5, 1 / 3, 0.25, 0.75, 1 / 6)
# Comfortable buffers: both fighters are still alive (visibly drained, ~40 HP)
# when the ultimate lands. The ult is a 70-dmg FINISHER, so it KOs the defender
# from anywhere in this band — which frees the combat to vary its rhythm without
# the old "must hit exactly 26 HP at 45.0s" balance breaking.
DEF_REMAIN = 40
# The winner is meant to look like they are LOSING until the finisher lands.
# ATK_REMAIN used to be 40, the same as the defender, and the measured result was
# two HP bars descending in lockstep for the whole 45 seconds — across b18 the
# two sides never diverged by more than 8%. A viewer checking the bars at any
# moment saw a dead heat, so there was nothing to find out by keeping watching.
# Ending the caster near death turns the ultimate into a comeback instead of a
# formality, and drops them into the low-HP danger band for the final stretch.
#
# 16 was too thin and broke the fights. The auto-tuner in measure() runs a PURE
# simulation, but the renderer does not: whenever slow-mo is active it ticks the
# engine at `ENGINE_MS * dt_scale` (≈2ms instead of 16.67ms), so the scripted
# driver gets up to eight times as many decisions per engine-millisecond and
# lands correspondingly more damage. The old value of 40 had enough slack to
# absorb that divergence; 16 did not, and the caster died before reaching its own
# ultimate — b18 rendered 47.1s with the wrong winner instead of 53.2s.
#
# 28 keeps the comeback (the winner still finishes around 20%, against 28% at the
# old setting) while leaving margin for the sim-vs-render gap. The real fix is to
# make measure() model the renderer's slow-mo; until then, changes to this number
# MUST be verified by an actual render, not by check_winners.
# With measure() now stepping through the same pacer as the renderer, the number
# written here is the number the video actually delivers, so it can go back to a
# genuinely dramatic value instead of one padded against a modelling error.
ATK_REMAIN = 18


# ── Dramatic arc ─────────────────────────────────────────────────────────────
# The phrase loop used to run unchanged from 0s to 45s: the tempo at second 40
# was identical to the tempo at second 5. These phases reshape that single loop
# into a story without touching the choreography itself.
#
# Each entry is (until_fraction_of_ULT_T, gap_scale, suppress_caster, suppress_defender).
# `gap_scale` stretches or compresses the beat spacing. `suppress_N` converts
# every Nth attack on that side into a defensive beat (0 = no suppression),
# which is what makes one side visibly lose ground: they stop landing hits, the
# opponent's bar stops draining, and the two curves separate on screen.
#
# Suppression is counted, not random — the generator has to stay reproducible.
# Tuned against the measured HP curves, not guessed. The first attempt used
# suppression 2 (half of one side's attacks dropped) for a long middle phase and
# froze the defender's bar at 93% for fifteen straight seconds — a bar that does
# not move reads as broken, which is worse than a bar that moves predictably.
# Suppression 3 keeps a side losing ground while still landing something.
#
# The lead changes hands twice. One swing is a story; zero swings is a metronome,
# and the version before this had zero.
# Two failed tunings are baked into these numbers; both were measured, not felt.
#
# Suppression 2 at an even tempo turned b09 and b11 into 7- and 12-second stalls,
# because dropping half of one side's attacks simply means less is happening.
# The obvious compensation — run the suppressed phases FASTER to buy the density
# back — made it worse, not better: every one of the twelve fights stalled and
# b18's impact count fell from 34 to 27. Tempo is not density. The choreography's
# advance/retreat beats need time to actually arrive, and compressing them leaves
# both fighters oscillating around the edge of range, whiffing.
#
# What works is closing the distance the suppression opens: see the chase rule in
# side_actions(). Tempo stays near neutral and only drifts tighter toward the end.
ARC = [
    # Feel-out — even, wide spacing, lets the opening read.
    (0.12, 1.20, 3, 3),
    # Defender presses. The eventual winner falls behind: the "oh no" setup.
    (0.30, 0.98, 2, 0),
    # The caster hits back and closes the gap.
    (0.46, 0.94, 0, 2),
    # Defender pushes again, harder.
    (0.64, 0.90, 2, 0),
    # Second rally — the caster nearly levels it, so the last reversal stings.
    (0.82, 0.86, 0, 2),
    # Driven to the danger band, then the finisher.
    (1.00, 0.70, 3, 0),
]


def _arc_at(progress: float):
    """(gap_scale, suppress_caster, suppress_defender) at this point in the fight."""
    for until, scale, sc, sd in ARC:
        if progress <= until:
            return scale, sc, sd
    return ARC[-1][1:]


# Beats a suppressed attack turns into — they already exist in every archetype's
# vocabulary, so nothing new has to be animated.
#
# Archetype matters here. Making a ranged fighter retreat opens the gap further,
# and then the OPPONENT's attacks whiff too: measured across the batch, a single
# shared list of defensive beats turned one stall into three and cut b18's impact
# count from 42 to 34. Ranged fighters give ground in place instead.
_DEFENSIVE = {
    "ranged": ("crouch", "jump", "crouch"),
    "assassin": ("crouch", "jump", "retreat"),
    "melee": ("retreat", "crouch", "jump"),
}

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


def _assert_ult_belongs_to_caster():
    """The ultimate must be a skill of whichever fighter casts it. Getting this
    wrong used to surface only deep in the timeline loader as an opaque
    "'x' is not a skill of 'y'" — easy to misread as a data-file problem when the
    real cause is passing the left fighter's ult alongside --caster-right."""
    import json
    caster_id = LEFT if CASTER == "left" else RIGHT
    data = json.loads((Path(__file__).resolve().parents[1]
                       / "data/characters.json").read_text(encoding="utf-8"))
    chars = data.get("characters", data)
    entry = chars.get(caster_id) if isinstance(chars, dict) else \
        next((c for c in chars if c.get("id") == caster_id), None)
    if entry is None:
        raise SystemExit(f"gen_fight: unknown character '{caster_id}'")
    skills = entry.get("skills") or {}
    names = list(skills.keys()) if isinstance(skills, dict) else \
        [s.get("id") for s in skills]
    if ULT_ID not in names:
        raise SystemExit(
            f"gen_fight: ult '{ULT_ID}' is not a skill of the caster "
            f"'{caster_id}' (caster side = {CASTER}).\n"
            f"  {caster_id} skills: {', '.join(n for n in names if n)}\n"
            f"  With --caster-right you must pass the RIGHT fighter's ult.")


_assert_ult_belongs_to_caster()
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
    # MIRROR-MATCH ONLY: start the two sides at different points in the phrase.
    #
    # Both sides used to begin at index 0. When they share an archetype they
    # therefore share a script, and the melee phrase's `retreat, retreat, jump`
    # stretch fires on both at once — both fighters back off together, the gap
    # doubles, and nothing lands. b09 and b11 are both melee-vs-melee and both
    # stalled; half a phrase of offset fixed b11 outright (11.4s gap -> 4.6s,
    # 14 impacts -> 22).
    #
    # Applying it unconditionally made things far worse (1 of 12 fights passed):
    # in a mixed pairing the two phrases are already different, and the default
    # alignment happens to put one side's advance inside the other's attack
    # window. Desynchronising that throws the interlock away. So: only when the
    # two archetypes match.
    t, si = (400 if is_caster else 700), 0
    mirror = L_ARCH == R_ARCH
    pi = int(len(phrase) * MIRROR_OFFSET) if (mirror and not is_caster) else 0

    # NOBODY WANTS TO CLOSE. When neither fighter is a melee archetype, both
    # phrases are built around holding or breaking distance: the ranged script
    # retreats to kite, the assassin script uses `flash:back` to vanish. Put
    # those two together and they simply walk away from each other — b12
    # (assassin vs ranged) opened a 35.5-second hole where nothing landed at all.
    # With no melee fighter present to force the engagement, the disengage beats
    # have to be inverted or the fight never happens.
    no_melee = "melee" not in (L_ARCH, R_ARCH)
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
    # Inject a special on every Nth BASIC attack (counted), NOT every Nth phrase
    # step. The old `pi % period` gate keyed on phrase index — and a melee
    # defender's basics (phrase indices 1,3,10) never coincide with pi%3==2, so
    # melee defenders got ZERO mid-fight casts and the fight showed only the final
    # ult. Counting basics guarantees every archetype rotates through its kit.
    period = 5 if is_caster else 3
    basic_n = 0
    atk_n = 0          # attacks seen on this side, for counted suppression
    while t < end:
        act, gap = phrase[pi % len(phrase)]
        scale, sup_c, sup_d = _arc_at(t / ULT_T)
        if sp and act == "attack:basic" and t < cast_until:
            basic_n += 1
            if basic_n % period == 0:
                act = f"cast:{sp[si % len(sp)]}"; si += 1   # cycle through the whole kit
        sup = sup_c if is_caster else sup_d
        other_sup = sup_d if is_caster else sup_c
        if act.startswith("attack:") or act.startswith("cast:"):
            atk_n += 1
            if sup and atk_n % sup == 0:
                # Give ground instead of striking. The opponent's bar stops
                # draining here, which is what a viewer reads as "losing".
                pool = _DEFENSIVE.get(arch, _DEFENSIVE["melee"])
                act = pool[atk_n % len(pool)]
        elif other_sup and act == "retreat":
            # CHASE. While the opponent is giving ground, backing off as well
            # just parks both fighters out of range and nothing lands — which is
            # how the first cut of this arc manufactured stalls. Press instead.
            act = "advance"
        if no_melee:
            if act == "retreat":
                act = "advance"
            elif act == "flash:back":
                act = "flash:in"
        rows.append((t, act)); t += max(120, int(gap * scale)); pi += 1
    return rows


def build():
    """Choreograph both sides. The CASTER side lands the ultimate and wins; the
    other side defends and is KO'd by it."""
    cast_is_left = CASTER == "left"
    left = side_actions(L_ARCH, cast_is_left, LEFT)
    right = side_actions(R_ARCH, not cast_is_left, RIGHT)
    caster = left if cast_is_left else right
    # Caster ult approach: melee/spin/dash ults need adjacency → flash in first;
    # ranged ults fire from current spacing.
    if ULT_ADJACENT:
        caster.append((ULT_T - 640, "flash:in")); caster.append((ULT_T - 160, "advance"))
    else:
        caster.append((ULT_T - 600, "attack:basic"))   # keep poking at range
    caster.append((ULT_T, f"cast:{ULT_ID}"))
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
        f'''# {LEFT}({L_ARCH}) vs {RIGHT}({R_ARCH}) — LONG ~{ULT_T//1000+6}s · {ULT_ID} climax · auto-tuned · caster={CASTER}
name: "{LEFT} vs {RIGHT} — long ({ULT_ID})"
left: {LEFT}
right: {RIGHT}
duration_ms: {ULT_T + 8000}
seed: {SEED}
{CASTER}_start_mp: 100
{hp}left_timeline:
{emit(left)}
right_timeline:
{emit(right)}
''', encoding="utf-8")


def measure():
    """Damage each side takes by the ultimate, measured the way it will RENDER.

    This used to step at a constant dt, which is not what play.py does: during
    slow-mo the renderer ticks the engine at a fraction of ENGINE_MS while still
    applying one scripted decision per frame, so more damage lands than a
    constant-dt loop predicts. With the old 40 HP cushion on the caster the error
    never mattered. Cutting the cushion for the comeback arc exposed it at once —
    the caster died before reaching its own ultimate and the fight went to the
    wrong side. Measuring through the same pacer the checkers use means the
    number written into the YAML is the number the video actually produces.
    """
    from pixel_battle.rl.env import PixelBattleEnv
    from pixel_battle.rl.render_sim import RenderPacer
    from pixel_battle.script.loader import load_fight_file
    d = load_fight_file(OUT)
    env = PixelBattleEnv(left_id=LEFT, right_id=RIGHT, seed=SEED); env.reset()
    b = env.battle
    (b.left if CASTER == "left" else b.right).mp = 100
    for f in (b.left, b.right):
        f.hp = 999
        if hasattr(f, "hp_max"): f.hp_max = 999
    L, R = b.left, b.right
    pre_l, pre_r = L.hp, R.hp
    pacer = RenderPacer(env)
    # Frame budget, not engine-time budget — slow-mo means more frames are needed
    # to reach the same engine timestamp.
    for _ in range(int(60 * 60)):
        la, ra = d.decide(b)
        if b.elapsed_ms < ULT_T:
            pre_l, pre_r = L.hp, R.hp
        else:
            break
        pacer.step(la, ra)
    return 999 - pre_l, 999 - pre_r


def _worst_silent_gap() -> float:
    """Longest stretch with nothing landing, for the YAML currently on disk.

    Uses the same render-accurate pacer the checkers use, so the number here is
    the number tools/check_pacing.py will report afterwards rather than an
    optimistic constant-dt estimate.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from sim_render import simulate
    r = simulate(Path(OUT))
    hits = r["impacts"]
    end_s = (r["events"][-1].t_ms / 1000.0) if r["events"] else 0.0
    if not hits:
        return end_s
    marks = [0.0] + hits + [end_s]
    return max(marks[i + 1] - marks[i] for i in range(len(marks) - 1))


def _emit_tuned():
    """Full pipeline for the current MIRROR_OFFSET: choreograph, tune HP, write."""
    left, right = build()
    write_yaml(left, right, None, None)
    dmg_l, dmg_r = measure()
    if CASTER == "left":
        lhp, rhp = round(dmg_l + ATK_REMAIN), round(dmg_r + DEF_REMAIN)
    else:
        lhp, rhp = round(dmg_l + DEF_REMAIN), round(dmg_r + ATK_REMAIN)
    write_yaml(left, right, lhp, rhp)
    return dmg_l, dmg_r, lhp, rhp


def _tune_mirror_offset():
    """Pick the phrase offset that leaves the smallest silent gap.

    Only mirror matches need this — when both sides share an archetype they share
    a phrase, so their movement beats can land on top of each other and both
    fighters back away at once. Which offset breaks that up depends on the pair:
    half a phrase fixes b11 and leaves b09 stalling, a third does the reverse. So
    it is measured, not assumed.

    Each candidate is evaluated through the WHOLE pipeline, HP tuning included.
    Measuring on default HP instead was the first attempt and it chose badly —
    start HP is several times higher after tuning, and the AI's low-HP retreat
    (engine/battle.py DEFENSIVE_RETREAT_HP) makes the fight play differently
    enough that the offset which looked best beforehand produced an 11-second
    silent gap afterwards.
    """
    global MIRROR_OFFSET
    if L_ARCH != R_ARCH:
        return
    best, best_gap = MIRROR_OFFSET, None
    for cand in MIRROR_CANDIDATES:
        MIRROR_OFFSET = cand
        _emit_tuned()
        gap = _worst_silent_gap()
        if best_gap is None or gap < best_gap:
            best, best_gap = cand, gap
    MIRROR_OFFSET = best
    print(f"    mirror offset {best:.3f} (worst silent gap {best_gap:.1f}s)")


def main():
    _tune_mirror_offset()
    dmg_l, dmg_r, lhp, rhp = _emit_tuned()
    print(f"  {OUT.split('/')[-1]}: {LEFT}({L_ARCH}) vs {RIGHT}({R_ARCH}) "
          f"ult {ULT_ID}/{VFX}@{ULT_T/1000:.0f}s  dmg L={dmg_l:.0f} R={dmg_r:.0f}"
          f"  -> Lhp={lhp} Rhp={rhp}  caster={CASTER} (winner)")


if __name__ == "__main__":
    main()
