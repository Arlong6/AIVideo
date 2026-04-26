# Task: Shorts → Long-form pipeline + dual voice + cross-promotion

## Context
- Crime channel: 9,314 views, 15 subs, 61 videos. Best Short 201 views.
- Existing long-form pipeline produces 13 videos avg 14 views — weak.
- User strategy: use Shorts performance as topic-validation signal,
  upgrade winners into deeper long-form with dual-voice dialogue, and
  cross-promote Shorts → main channel.

## Decisions (user-confirmed)
- **Trigger**: ≥500 views threshold for AUTO future upgrade. **Phase 1
  bootstrap**: manually pick current top performers (no Short hits 500
  yet — best is 201). Use top 3-5 as initial batch.
- **Approach**: regenerate from scratch (not extend) — long-form gets
  full multi-voice dialogue treatment, not just appended content.
- **Old long-forms**: keep for now. Re-evaluate after new ones land.
- **Future Shorts**: add "看完整版主頁" CTA pointing back to channel.

## Phase 1 — Pipeline Foundation (this session)

- [ ] **1.1 Build Shorts performance scanner**
  - New script `shorts_to_longform_queue.py`
  - Inputs: video_log.json + YouTube API stats
  - Output: `longform_queue.json` ranked by views, excluding topics that
    already have a long-form
  - Manual override flag for Phase 1 bootstrap (top 5 by views)

- [ ] **1.2 Add dual-voice support to TTS**
  - Modify `tts_generator.py` to accept `voice_role` param
  - Add 2 ElevenLabs voice IDs: NARRATOR + ALT (e.g. interrogator)
  - Add Chinese voice IDs (research best ElevenLabs zh voices)
  - Smoke test: render two-line dialogue locally

- [ ] **1.3 Extend long-form script schema for dialogue**
  - In `script_generator.py` `_generate_long_scripts`, add `dialogue_blocks`
    field — list of `{role: "narrator"|"alt", text: str}` segments
  - Update prompt to include 2-4 dialogue exchanges per video (court
    transcripts, interrogation snippets, victim's last words, etc.)
  - Validate at most 30% of total duration is dialogue (rest stays narration)

- [ ] **1.4 Wire dialogue rendering**
  - Update `video_assembler.py` to render dialogue blocks with the right
    voice per role + visual cue (different bg color or speaker label)

## Phase 2 — Cross-Promotion CTA in Shorts

- [ ] **2.1 Update Shorts CTA prompt to optionally include channel jump**
  - When the topic has (or will have) a long-form, append "完整版主頁"
    sub-line to the binary-choice CTA
  - Keep the "1 vs 2" binary as primary; "看完整" is secondary

- [ ] **2.2 Update Remotion CrimeCTA visual to render channel-jump line**
  - Below the 1/2 cards, show small "🔗 主頁看完整版" link styled text
  - Trigger from new `c.has_longform` field in case schema

## Phase 3 — Generate First Batch

- [ ] **3.1 Pick top 3 Shorts manually**
  - 芭提雅(201), 湯英伸(135), 鄭性澤(132) candidate set
  - Verify all 3 have enough verifiable source material for 15-min depth
  - User confirms picks before generation

- [ ] **3.2 Generate long-form for batch**
  - Run new pipeline against the 3 picks
  - QA check each output
  - Schedule publish: 3 videos over 9 days (1 every 3 days, not back-to-back)

- [ ] **3.3 Track performance**
  - Tag these long-forms in video_log with `source: "shorts_upgrade"`
  - Compare 14-day view performance vs old long-form baseline (avg 14)

## Phase 4 — Auto-Trigger (deferred)

- [ ] **4.1 Add scheduled job to scan for ≥500 view Shorts**
  - GitHub workflow weekly: detects newly-qualified Shorts
  - Posts to Telegram for user approval before queueing

- [ ] **4.2 Document the trigger threshold + override** in CLAUDE.md or
  notes for future reference

## Out of Scope (intentional)
- Don't delete existing long-forms yet
- Don't change short-form daily cadence
- Don't change topic selection for Shorts (still randomized)
- Don't refactor Books pipeline (abandoned)

## Estimated Effort
- Phase 1: 1 session (3-4 hours)
- Phase 2: 30 min
- Phase 3: depends on render time (each long-form takes ~30 min on GH Actions)
- Phase 4: 30 min later

## Review

### Done in this session (2026-04-26)
- Phase 1: dual-voice TTS, Shorts scanner, dialogue [ALT] schema, multirole audio
- Phase 2: cross-promo `has_longform` flag end-to-end (case → renderer)
- Phase 3.1: longform.yml workflow_dispatch supports topic + source_tag
- Phase 3.2: triggered D.B.庫柏 long-form (run 24946381573, source=shorts_upgrade)

### Pending / decisions needed
- Verify D.B. render succeeds with dialogue blocks (smoke test for the
  whole new pipeline). If it fails, fix before triggering 洪仲丘 / 芭提雅.
- Pacing decision: 3-day spacing vs back-to-back batch.
- Phase 4 (auto ≥500 view trigger): deferred until first batch's
  performance is observed.

### What worked
- Inline [ALT]...[/ALT] markers turned out cleaner than separate
  dialogue_blocks array — no schema explosion, easy to validate.
- Reusing existing `_topic_key` normalization across scanner +
  has-longform check kept logic DRY.
- workflow_dispatch inputs (topic, source_tag, slot_a, slot_b earlier)
  is the right escape hatch — future overrides can layer on the same
  pattern without forking the cron path.

### What didn't
- Initially tried "0Hz" pitch in VOICE_ROLES.alt — edge-tts requires
  "+0Hz" / "-0Hz" sign prefix. Caught immediately by smoke test.
- Books pipeline fade timeout (30s) was a latent bug from the Crime
  fade addition — exposed only when Books resumed 60+ clip videos.
  Fixed in the same session by switching to ultrafast preset + 90s
  timeout + skip-on-timeout.
