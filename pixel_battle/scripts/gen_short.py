"""Parameterized SHORT fight generator for the test-water shorts batch.

~14s punchy fight, ultimate at ~9s as the payoff. The caster uses only FREE
actions pre-ult (basic / cd / flash / advance / retreat) so MP stays 100 for the
ult. Melee ults (slam) → caster rushes in; ranged ults (beam/bolt) → caster kites.
Default 30 HP means the ult one-shots the defender — we just need both alive at 9s.

Usage: python gen_short.py <left> <right> <ult_id> <vfx> <melee:0|1> <out.yaml>
"""
import sys
from pathlib import Path

LEFT, RIGHT, ULT_ID, VFX, MELEE, OUT = (
    sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] == "1", sys.argv[6])
ULT_T = 9000
END = 11000

left, right = [], []   # left = caster

# Caster pre-ult: FREE actions only. Melee → rushdown; ranged → kite.
if MELEE:
    lpat = ["advance", "attack:basic", "attack:cd", "advance", "attack:basic",
            "jump", "advance", "attack:basic"]
    l_flash = [2500, 6000]          # flash:in to close
    l_flash_act = "flash:in"
else:
    lpat = ["retreat", "attack:basic", "jump", "retreat", "attack:cd",
            "advance", "attack:basic", "retreat"]
    l_flash = [2500, 6500]          # flash:back to keep range
    l_flash_act = "flash:back"

t, pi = 400, 0
used_lf = set()
while t < ULT_T - 600:
    ff = next((f for f in l_flash if f not in used_lf and abs(f - t) < 280), None)
    if ff is not None:
        left.append((ff, l_flash_act)); used_lf.add(ff); t = ff + 500; continue
    left.append((t, lpat[pi % len(lpat)])); pi += 1; t += 480
# Final approach for melee (adjacent), or hold range for ranged, then ULT.
if MELEE:
    left.append((ULT_T - 600, "flash:in"))
    left.append((ULT_T - 150, "advance"))
else:
    left.append((ULT_T - 600, "retreat"))
left.append((ULT_T, f"cast:{ULT_ID}"))

# Defender: aggressive mix (can spend MP — not ulting). Keeps the fight 刺激.
rpat = ["advance", "attack:basic", "attack:cd", "jump", "attack:basic",
        "advance", "retreat", "attack:basic", "jump", "attack:cd"]
t, pi = 700, 0
while t < ULT_T - 400:
    right.append((t, rpat[pi % len(rpat)])); pi += 1; t += 480

def emit(rows):
    rows = sorted(rows, key=lambda r: r[0])
    return "\n".join(f'  - {{t: {a}, do: "{b}"}}' if ":" in b
                     else f'  - {{t: {a}, do: {b}}}' for a, b in rows)

yaml = f'''# {LEFT} vs {RIGHT} — SHORT (~14s) test-water short, {ULT_ID} climax
name: "{LEFT} vs {RIGHT} — short ({ULT_ID})"
left: {LEFT}
right: {RIGHT}
duration_ms: {END + 4000}
seed: 7
left_start_mp: 100
left_timeline:
{emit(left)}
right_timeline:
{emit(right)}
'''
Path(OUT).write_text(yaml, encoding="utf-8")
print(f"  wrote {OUT}: {len(left)}L+{len(right)}R, ult {ULT_ID} at {ULT_T}ms melee={MELEE}")
