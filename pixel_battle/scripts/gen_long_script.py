"""Generate a dense ~40s script 01 (Lux kite Garen, final_spark climax ~33s).

Design: high action density (~every 0.5s) but mostly NON-LETHAL — Garen chiefly
advances/jumps/whiffs at range so Lux (30 HP) survives to the climax; Lux kites
densely with roots/flashes/jumps. Periodic flash:in CRISES add danger. CDs:
flash 3500ms, decisive_strike (cd) 3500ms, light_binding 4000ms.
"""
from pathlib import Path

ULT_T = 33000
END = 34000

# Build as lists of (t, action). Author densely; the sim is the balance check.
left = []   # Garen — hunter, mostly movement + whiff, periodic flash crises
right = []  # Lux — caster, MP must stay 100 (free actions only), kite

# Garen flash:in crisis times — only 3, well-spaced (each is a real hit on Lux,
# and Lux has just 30 HP). The rest of Garen's "action" is pure movement.
# Higher HP lets the fight breathe over 40s. Garen must absorb Lux's RANGED barrage
# (light_binding + lucent) and still be <32 at the climax for the ultimate KO.
# Balanced ranged kite (clean KO + ~17 hits). Moderate distance ~150-280 keeps Lux's
# bolts in range; smaller figures + wider camera make this read as well-spread.
LEFT_HP = 60    # Garen — chipped to ~<32 by the climax for the ult KO
RIGHT_HP = 95   # Lux — survives Garen's flash bursts
g_flash = [3000, 9000, 15000, 21000, 27000]
l_root = [700, 4700, 8700, 12700, 16700, 20700, 24700, 28700]   # ranged root every 4s
l_lucent = [6000, 15000]   # lucent_singularity — only 2, so MP comfortably refills to 100 for the ult
l_flash = [1900, 13000, 25000]    # kite resets; pre-ult flash added separately

# ── Garen timeline: walk-hunt with jumps/blocks, whiff basics, flash crises ──
t = 400
gi = 0
gflash_set = set(g_flash)
# AGGRESSIVE hunt — real attacks (basic + decisive_strike dash) interleaved with
# movement. With higher HP both can trade hits → actual clashing, not a standoff.
# No block/crouch (those read as "striking a pose and holding").
pattern = ["advance", "attack:basic", "attack:cd", "advance", "attack:basic",
           "jump", "advance", "attack:basic", "retreat", "attack:cd",
           "attack:basic", "advance"]
# Courage removed. JUDGMENT (spin storm) is Garen's signature — fires at every flash
# crisis AND a few standalone beats between them for more "spinning attacks".
g_special = [(6500, "judgment"), (18500, "judgment"), (24500, "judgment")]
used_sp = set()
pi = 0
while t < ULT_T - 600:
    if t in gflash_set:
        left.append((t, "flash:in"))
        # Crisis payload — Garen just flashed (idle, can cast), so JUDGMENT reliably
        # fires here as a big spinning blade storm: his signature skill, every crisis.
        left.append((t + 500, "cast:judgment"))
        t += 1000
        continue
    sp = next((s for s in g_special if s not in used_sp and abs(s[0] - t) < 320), None)
    if sp is not None:
        left.append((sp[0], f"cast:{sp[1]}"))
        used_sp.add(sp)
        t = sp[0] + 600
        continue
    # snap to nearest flash if close
    nxt = min((f for f in g_flash if f > t), default=ULT_T)
    if nxt - t < 500:
        t = nxt
        continue
    left.append((t, pattern[pi % len(pattern)]))
    pi += 1
    t += 470
left.append((ULT_T + 200, "advance"))

# ── Lux timeline: dense kite — root/retreat/jump/flash/whiff, hold MP=100 ──
root_set = set(l_root)
flash_set = set(l_flash)
t = 700
# Lux movement — retreat-biased to KEEP DISTANCE (she's a mage, stays in bolt range
# ~150-280, out of Garen's melee). NO melee basic. Ranged attacks come from the
# scheduled light_binding / lucent casts below. Always moving, no held poses.
lpat = ["retreat", "jump", "retreat", "advance", "retreat", "jump",
        "retreat", "advance", "jump", "retreat", "retreat", "jump"]
li = 0
used_root = set()
used_flash = set()
used_luc = set()
while t < ULT_T - 1500:
    # prioritise scheduled ranged casts / flashes near this time
    rr = next((r for r in l_root if r not in used_root and abs(r - t) < 300), None)
    lu = next((x for x in l_lucent if x not in used_luc and abs(x - t) < 300), None)
    ff = next((f for f in l_flash if f not in used_flash and abs(f - t) < 300), None)
    if rr is not None:
        right.append((rr, "cast:light_binding"))
        used_root.add(rr); t = rr + 520; continue
    if lu is not None:
        right.append((lu, "cast:lucent_singularity"))
        used_luc.add(lu); t = lu + 520; continue
    if ff is not None:
        right.append((ff, "flash:back"))
        used_flash.add(ff); t = ff + 520; continue
    right.append((t, lpat[li % len(lpat)]))
    li += 1
    t += 470
# final separation + cast — retreat (NOT flash) so Lux stays within final_spark's
# 340 range and the beam actually connects for the KO.
right.append((ULT_T - 1100, "retreat"))
right.append((ULT_T - 600, "retreat"))
right.append((ULT_T, "cast:final_spark"))

def emit(rows):
    rows = sorted(rows, key=lambda r: r[0])
    return "\n".join(f'  - {{t: {t}, do: "{a}"}}' if ":" in a
                     else f'  - {{t: {t}, do: {a}}}' for t, a in rows)

yaml = f'''# 蓋倫 vs 拉克絲 — 長版密集攻防 ~40s · 大絕收場 (auto-generated, then hand-tuned)
name: "Lux vs Garen — dense 40s kite + ultimate climax"
left: garen
right: lux
duration_ms: {END + 6000}
seed: 7
right_start_mp: 100
left_start_mp: 90
left_start_hp: {LEFT_HP}
right_start_hp: {RIGHT_HP}
left_timeline:
{emit(left)}
right_timeline:
{emit(right)}
'''
Path("pixel_battle/data/scripts/01_lux_kite_garen.yaml").write_text(yaml, encoding="utf-8")
print(f"wrote {len(left)} left + {len(right)} right actions, ult at {ULT_T}ms")
