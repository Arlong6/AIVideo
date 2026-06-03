"""Generate a dense ~40s script 02 (Garen rushdown, demacian_justice slam ~33s).

Mirror of script 01 with roles flipped: GAREN is the ultimate caster (slam → needs
melee proximity at the climax, so he closes in), LUX defends with ranged spells.
Lessons from 01: caster uses only FREE actions pre-ult (basic/cd/flash/advance) so
MP stays 100 for the ult; per-script HP lets the 40s fight trade real hits.
"""
from pathlib import Path

ULT_T = 33000
END = 40000

# HP: Garen soaks Lux's ranged poke for 40s; Lux is chipped by the rushdown and
# finished by the 30-dmg slam (so she must be alive but lowish at the climax).
LEFT_HP = 95    # Garen — survives Lux's ranged barrage
RIGHT_HP = 70   # Lux — rushed down; slam (30) KOs her at ~33s

left = []   # Garen — aggressor + slam caster (FREE actions only pre-ult)
right = []  # Lux — defender, ranged kite

# Garen flash:in crises (CD 3500) — close the gap, land a melee burst
g_flash = [3000, 9000, 15000, 21000, 27000]
# Lux ranged: light_binding (FREE, roots Garen to survive the rush) + lucent pokes
l_root = [700, 4700, 8700, 12700, 16700, 20700, 24700, 28700]
l_lucent = [6000, 13000, 20000, 27000]
l_flash = [1900, 11000, 23000]   # escape resets when cornered

# ── Garen timeline: relentless rushdown, FREE actions only (slam needs full MP) ──
t = 400
gflash_set = set(g_flash)
pattern = ["advance", "attack:basic", "attack:cd", "advance", "attack:basic",
           "jump", "advance", "attack:basic", "advance", "attack:cd",
           "attack:basic", "advance"]
pi = 0
while t < ULT_T - 600:
    if t in gflash_set:
        left.append((t, "flash:in"))
        left.append((t + 500, "attack:basic"))   # crisis burst
        t += 1000
        continue
    nxt = min((f for f in g_flash if f > t), default=ULT_T)
    if nxt - t < 500:
        t = nxt
        continue
    left.append((t, pattern[pi % len(pattern)]))
    pi += 1
    t += 470
# Final approach: flash onto the cornered mage, then SLAM (melee range).
left.append((ULT_T - 700, "flash:in"))
left.append((ULT_T - 200, "advance"))
left.append((ULT_T, "cast:demacian_justice"))

# ── Lux timeline: ranged defender — roots/pokes/retreats (MP free, not ulting) ──
t = 700
lpat = ["retreat", "jump", "advance", "retreat", "jump", "advance",
        "retreat", "jump", "retreat", "advance", "retreat", "jump"]
li = 0
used_root, used_luc, used_flash = set(), set(), set()
while t < ULT_T - 1200:
    rr = next((r for r in l_root if r not in used_root and abs(r - t) < 300), None)
    lu = next((x for x in l_lucent if x not in used_luc and abs(x - t) < 300), None)
    ff = next((f for f in l_flash if f not in used_flash and abs(f - t) < 300), None)
    if rr is not None:
        right.append((rr, "cast:light_binding")); used_root.add(rr); t = rr + 520; continue
    if lu is not None:
        right.append((lu, "cast:lucent_singularity")); used_luc.add(lu); t = lu + 520; continue
    if ff is not None:
        right.append((ff, "flash:back")); used_flash.add(ff); t = ff + 520; continue
    right.append((t, lpat[li % len(lpat)])); li += 1; t += 470
right.append((ULT_T - 600, "attack:basic"))   # last desperate poke as the slam lands

def emit(rows):
    rows = sorted(rows, key=lambda r: r[0])
    return "\n".join(f'  - {{t: {t}, do: "{a}"}}' if ":" in a
                     else f'  - {{t: {t}, do: {a}}}' for t, a in rows)

yaml = f'''# 蓋倫 vs 拉克絲 — 鐵衛逆襲處決 (長版密集 ~40s) · demacian_justice slam 收場
name: "Garen rushdown — 40s, demacian_justice slam climax"
left: garen
right: lux
duration_ms: {END + 6000}
seed: 7
left_start_mp: 100
left_start_hp: {LEFT_HP}
right_start_hp: {RIGHT_HP}
left_timeline:
{emit(left)}
right_timeline:
{emit(right)}
'''
Path("pixel_battle/data/scripts/02_garen_rush_lux.yaml").write_text(yaml, encoding="utf-8")
print(f"wrote {len(left)} left + {len(right)} right actions, slam at {ULT_T}ms")
