# pixel_battle Shorts — Test-Water Design

**Date:** 2026-06-04
**Goal:** Validate whether the cinematic stick-figure fight content can find an audience, BEFORE investing in a new channel / automation. Decision is data-driven (arlong's product-gate discipline — no impulsive all-in).

## Scope

Produce **5-8 punchy vertical short videos** from the existing pixel_battle fight engine (Lux/Garen + other LoL champions), post them manually, measure response, then decide whether to scale.

NOT in scope (explicitly deferred until data justifies):
- Phone-brand-war re-skin (considered, dropped — keep the stick-figure visuals we built).
- New-channel automation / auto-upload pipeline.
- Monetization, dedicated branding.

## Content

- **Format:** ~15-25s vertical (1080×1920 export; engine renders 480×854 → upscale). Short and dense, NOT the 40s cut.
- **Structure (勁爆 / hype-first):**
  1. **Hook in the first 1-2s** — text-overlay taunt or a flash-teaser of the ultimate (don't slow-build).
  2. Fast buildup — a few seconds of fight at high pace.
  3. **Ultimate climax + knockback KO** as the payoff.
  4. Short hold on the KO / winner.
- **Engagement frame:** optional "誰會贏?" text overlay early → the ultimate is the reveal (留言/重看 bait). NOT the phone theme.
- **Matchups:** reuse script 01 (Lux beam) + 02 (Garen slam); add 3-6 more via the scripted system using the existing champions (yasuo `last_breath`, ashe `enchanted_crystal_arrow`, etc.). For shorts, fights can be SHORTER than 40s (quicker to the ult) — easier to balance and better-paced for the platform.

## Production split

- **Claude makes:** the 5-8 cut shorts (hook front-loaded, punchier), titles + hook text + thumbnails, packaged ready-to-post. Deliver into `pixel_battle/output/shorts/`.
- **arlong posts:** manual upload of the first batch (new TikTok dedicated account + new YouTube channel — first 5 YT uploads MUST be manual per the anti-spam rule). Claude does NOT touch accounts.
- If a video pops → THEN wire auto-upload (like the crime pipeline) for scale.

## Platforms

- **TikTok** — dedicated account (strongest cold-start for animation/fight content). Don't mix into an existing account (algorithm rewards niche focus).
- **YouTube Shorts** — new channel.
- Same video to both; compare which platform responds.

## Cadence & decision gate

- Post the 5-8 over ~2 weeks (慢慢發), not all at once.
- **Success signal:** any single video breaking out (views / watch-through / shares / comments meaningfully above the rest).
- **Gate:** after the batch, review the data →
  - breakout → invest in production volume + a new-channel auto-upload pipeline.
  - flat → shelve, no further investment.

## First step

Produce ONE sample short first (format + 勁爆 level) for arlong to approve, then batch the remaining to 5-8.
