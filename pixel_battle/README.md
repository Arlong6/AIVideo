# Pixel Battle

9:16 vertical auto-battler producing TikTok/YT Shorts mp4 output.

See `docs/superpowers/specs/2026-05-17-pixel-battle-design.md` for full design.

## Run Episode 1
```
python -m pixel_battle.episodes.ep01_brick_vs_glass
```

## Test
```
pytest pixel_battle/tests/
```

## Status (2026-05-17)

- ✅ Engine, renderer, cinematics, video pipeline complete
- ✅ Episode 1 (Brick Phone vs Glass Slab) end-to-end working
- ⚠️ SFX/BGM are sine-wave placeholders — replace with CC0 assets before manual upload
- 📋 Manual upload steps: TikTok (primary, manual via app), YT Shorts (mirror via youtube_uploader.py if 9:16 supported)
- 📊 Tracking: see `data/episodes_log.json` for metrics log
