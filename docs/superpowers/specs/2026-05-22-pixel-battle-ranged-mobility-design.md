# Pixel Battle — Ranged Combat & Mobility (Sub-project C) — Design Spec

> **For agentic workers:** This is a *design spec*. The step-by-step implementation
> plan is generated separately via `superpowers:writing-plans`.

- **Date:** 2026-05-22
- **Status:** Design approved — the user granted full autonomous execution (no approval gates) and is running this work under `/loop`.
- **Relationship:** Sub-project **C** of the pixel_battle combat work, following A (combat-feel polish) and B (scripted combat).

## 1. Motivation

After reviewing the Sub-project B scripted fights, the user's feedback:

- The rendered videos **stutter** (會卡).
- The characters are still **too big / too close** on screen.
- "The mage fights at range" does not really work — the engine caps *every* attack at ≤130 px.
- They want a **Flash / teleport** mobility ability.
- The scripts and overall polish "still have a way to go."

**Stutter diagnosis (verified in code):** the cause is the engine **hitstop**. Every landed hit freezes the simulation for `HITSTOP_MS` (50 ms = 3 video frames at 60 fps). During the scripts' attack-heavy finishers, hits land roughly every 400–500 ms, so a 3-frame freeze recurs every ~0.4 s — a clearly perceptible micro-stutter.

## 2. Goal

Make scripted fights smooth, well-framed, and genuinely tactical: kill the hitstop stutter, give projectile skills real reach so a mage can fight from a distance, add a Flash mobility ability, shrink the on-screen characters, and re-author the script library to use the new range and Flash.

## 3. Scope & Constraints

**In scope** — five changes:
1. Hitstop stutter fix.
2. Per-skill numeric range (true long-range skills).
3. Flash mobility ability.
4. Smaller on-screen characters.
5. Re-author the 5 scripts to use range + Flash.

**Hard constraint:** **No RL retraining.** The RL `Discrete(9)` action space is untouched — Flash is added as engine action integers 9/10, which the RL model never emits; only the `ScriptDriver` uses them. `characters.json` gains data-only `range` fields.

**Out of scope:** LLM auto-generation of scripts (still future); new characters/skills.

## 4. The Five Changes

### 4.1 Hitstop stutter fix

The hitstop currently fires on **every** landed hit (`_resolve_attack_hit` sets `_hitstop_remaining` unconditionally). Change it to fire only on **significant** hits — a **crit**, or a **cd / special / ultimate** skill hit. Plain **basic-attack** hits (the bulk of all hits, and all of the finisher spam) no longer freeze the sim.

Result: rapid basic trading renders smoothly; the dramatic hits (crits, skills, ultimates) keep their impact freeze. This is one condition change in `_resolve_attack_hit` — no new state, no debounce. `HITSTOP_MS` / `HITSTOP_MS_HEAVY` values are unchanged (now that hitstop is rare, 50/100 ms reads as impact, not stutter).

### 4.2 Per-skill numeric range

`Skill.range` currently holds the string `"melee"` / `"special"`, mapped to `MELEE_RANGE = 110` / `SPECIAL_RANGE = 130`. Allow `range` to also hold a **number** (px). Add a `Skill.effective_range` accessor: returns the number if `range` is numeric, else 130 for `"special"`, else 110.

- `_resolve_attack_hit` (the authoritative hit check) uses `skill.effective_range` as the distance limit.
- `_apply_action`'s pre-fire gate for cd/special actions (currently hardcoded to `SPECIAL_RANGE`) widens to a generous `MAX_ATTACK_RANGE` (≈ 360) upper bound, so a long-range skill action is not blocked before it can fire. basic/kick actions stay gated at `MELEE_RANGE`. The authoritative per-skill check remains `_resolve_attack_hit`.

The genuinely projectile skills (vfx `bolt` / `multishot` / `beam`) get long `range` values in `characters.json`:

| Character | Skill | Kind | `range` (px) |
|---|---|---|---|
| lux | light_binding | cd | 280 |
| lux | lucent_singularity | special | 300 |
| lux | final_spark | ultimate | 340 |
| ashe | volley | cd | 260 |
| ashe | hawkshot | special | 300 |
| ashe | enchanted_crystal_arrow | ultimate | 340 |
| brick_phone | screw_dart | cd | 250 |
| brick_phone | snake_strike | special | 240 |
| glass_slab | shard_scatter | cd | 240 |
| glass_slab | ad_popup_spam | special | 240 |
| glass_slab | force_update | ultimate | 320 |

All **basic** attacks and the **melee bruisers'** skills (Garen, Yasuo — `decisive_strike`, `judgment`, `sweeping_blade`, `steel_tempest`, etc.) keep short range — preserving the "the mage kites, the bruiser must close the gap" dynamic. Self-buff skills (`prismatic_barrier`, `courage`, etc.) need no `range`. Values are starting points, tuned at validation.

### 4.3 Flash mobility ability

A new instant-teleport ability, scriptable. Two `do` verbs added to `DO_VERBS`:
- `flash:in` — blink toward the opponent (a gap-close).
- `flash:back` — blink away from the opponent (the kiter's escape).

Implemented as engine action integers **9** and **10** in `_apply_action` — purely additive: the RL `Discrete(9)` space is unchanged (the RL model only ever emits 0–8; the `ScriptDriver` emits 9/10). A Flash instantly shifts the character's `pos_x` by `FLASH_DISTANCE` (≈ 130 px) in the chosen direction, clamped to the arena. It is gated by a per-character `FLASH_COOLDOWN_MS` (≈ 3500 ms) cooldown — a Flash issued while on cooldown is a no-op. A simple blink VFX (a fading puff at the origin and the destination).

### 4.4 Smaller characters

`CAM_ZOOM` 1.2 → **1.0** — at 1.0 the camera shows the whole arena (no crop/upscale), which is the best framing for reading long-range kiting. Additionally, trim the `_STYLES` limb/torso proportions by ≈ 15 % so the figures are genuinely smaller, not just framed wider. Both are starting values, tuned at validation; the visual-safety test must stay green.

### 4.5 Re-author the script library

With real per-skill range and Flash available, re-author the 5 scripts so the mage scripts **genuinely kite** — cast from 250–300 px, `flash:back` to escape a closing bruiser, re-establish distance — instead of the Sub-project B workaround of `advance`-ing to ≤130 px before every cast. The bruiser scripts use `flash:in` / `advance` to close the gap. Each script must still end in a decisive KO and still load + validate.

## 5. Error handling

- `Skill.range` accepts a number or the legacy `"melee"` / `"special"` strings; any unrecognised value falls back to `MELEE_RANGE`.
- A Flash issued while its cooldown is active is a silent no-op (consistent with how an out-of-range or unaffordable attack action no-ops).
- The Flash destination `pos_x` is clamped to the arena bounds (`clamp_x`).

## 6. Testing

- **Hitstop:** a basic-attack hit does NOT set `_hitstop_remaining`; a crit, and a cd / special / ultimate hit, DO.
- **Per-skill range:** `Skill.effective_range` returns the numeric value when set and the 110/130 fallback otherwise; a skill with `range: 280` lands a hit at 250 px distance; a melee skill still misses at 200 px.
- **Flash:** `flash:back` and `flash:in` shift `pos_x` by `FLASH_DISTANCE` in the correct direction, clamped to the arena; a Flash on cooldown is a no-op; the `flash:in`/`flash:back` verbs are in `DO_VERBS`.
- **Smaller:** `CAM_ZOOM == 1.0`; the visual-safety test `test_all_poses_keep_feet_planted_and_in_frame` stays green.
- **Scripts:** all 5 re-authored scripts still load + validate.
- All pre-existing tests stay green.

## 7. Validation

Re-render all 5 scripts via `play_scripted.py`. Confirm: no stutter; characters are smaller and the arena reads wide; the mage scripts visibly kite at range and use Flash to escape; the bruiser scripts close the gap; every fight still reaches a decisive KO.

## 8. Future work

- LLM auto-generation of fight scripts per video (the YAML format already supports it).
- More characters / skills; richer Flash variants.
