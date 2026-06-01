# Crime Reel — External Render Contract

This Remotion project exposes a generic `Crime` composition that renders a crime-story short from a JSON spec plus an assets directory. External systems (e.g., AIvideo) can call it without knowing any React/TypeScript.

## Entry point

```bash
scripts/render-crime.sh \
  --case  /path/to/case.json \
  --assets /path/to/assets_dir \
  --out   /path/to/out.mp4
```

The script copies `assets_dir` into `public/crime/{case.id}/`, then runs `remotion render` with the case JSON passed via `--props`.

## Case JSON schema

Must match the TypeScript `Case` type in `src/crime/data.ts`. Example:

```json
{
  "id": "300m-yen",
  "title": "三億円事件",
  "titleZh": "三億日圓搶案",
  "date": "1968年12月10日",
  "location": "東京都府中市",
  "status": "unsolved",
  "statusLabel": "未偵破",
  "hook": "日本史上最離奇的劫案——警方追了七年，連一個嫌犯都找不到。他們到底怎麼做到的？",
  "hookImage": "images/tokyo_1960s.jpg",
  "setup": "1968年12月，東京府中。運鈔車上的四人，不知道即將遇到什麼。",
  "setupImage": "images/fuchu.jpg",
  "events": [
    { "text": "一名騎白色警用摩托車的警察，突然攔下運鈔車。", "image": "images/police.jpg" },
    { "text": "「車上被裝了炸彈，快下車！」警察大喊，鑽到車底檢查。", "image": "images/cedric.jpg" },
    { "text": "突然一陣白煙冒出——「要爆炸了，快逃！」", "image": "images/smoke.jpg" },
    { "text": "四人躲遠，回頭一看。運鈔車不見了。", "image": "images/cedric.jpg" }
  ],
  "twist": "白煙是煙霧彈。摩托車是噴漆的假貨。警察，是假扮的。三億日圓，在光天化日下蒸發。",
  "twistImage": "images/yen.jpg",
  "aftermath": "警方公開嫌犯的蒙太奇畫像，動員全國追查七年。1975年公訴時效到期，1988年連民事追訴都結束。那七年的追查，化為一場空。嫌犯的真實身份，至今成謎。",
  "aftermathImage": "images/fuchu.jpg",
  "cta": "追蹤看更多真實懸案",
  "credits": "照片來源：Wikimedia Commons",
  "timings": {
    "hook": 8.184,
    "setup": 7.176,
    "events": [5.04, 5.688, 3.792, 4.488],
    "twist": 10.008,
    "aftermath": 17.328,
    "cta": 2.616
  }
}
```

### Field rules

- `id` — slug; becomes the folder name under `public/crime/`. Only `[a-z0-9-]`.
- `status` — `"unsolved"` or `"solved"`.
- `statusLabel` — free text shown on-screen (中文).
- `events` — 3–6 items. Each must have a matching `event-{n}.mp3` in assets.
- `*Image` fields — paths relative to the case folder root. If omitted, scene shows black background.
- `timings` — **required**, **in seconds**, must be the ffprobe-measured duration of each mp3. Scenes are sized as `audio_length + 1.2s breath` (0.5s for CTA). If timings are wrong, audio gets cut off.

## Assets directory layout

```
assets_dir/
  hook.mp3
  setup.mp3
  event-1.mp3
  event-2.mp3
  event-3.mp3
  event-4.mp3
  twist.mp3
  aftermath.mp3
  cta.mp3
  images/
    tokyo_1960s.jpg
    fuchu.jpg
    police.jpg
    ...
```

Number of `event-{n}.mp3` files must match `case.events.length`.

## Measuring audio durations

The project already uses this pattern in `scripts/gen_crime_audio.py`:

```python
import subprocess

def probe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())
```

AIvideo **must** populate `case.timings` from ffprobe before calling the renderer. Hardcoded estimates will cause cut-offs on long lines (tested failure mode: aftermath at 17.3s sliced to 9s).

## Shared resources

- **BGM**: `public/music/crime-bgm.mp3` — reused across all cases. Replace at will; renderer auto-picks.
- **Font stack**: iOS system fonts (`PingFang TC`, `Hiragino Sans TC`, etc.); no font bundling needed.

## Output

- 1080 × 1920 H.264 mp4, AAC audio, 30 fps.
- Duration is derived from `case.timings` (typically 60–90 s).

## Failure modes & checks

- Missing mp3 → Remotion silently plays nothing for that scene. Validate with `ls assets_dir/*.mp3 | wc -l` before rendering.
- Missing image → Remotion logs error but continues (black background). Validate with `ls assets_dir/images/*.jpg`.
- `timings.events.length != events.length` → TypeScript runtime error. Script will `exit 1`.
- Case JSON not valid JSON → Python loader fails fast with line/col.

## Studio preview (for devs)

```bash
npm run dev
# open http://localhost:3000
# pick "Crime" from sidebar, editor lets you tweak props JSON live
```

## Minimum viable call from Python

```python
import json, subprocess, tempfile, pathlib

CASE = { ... }  # build dict matching schema
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump(CASE, f, ensure_ascii=False)
    case_path = f.name

subprocess.run([
    "/Users/arlong/Projects/japanese-learner/nihongo-reels/scripts/render-crime.sh",
    "--case", case_path,
    "--assets", "/tmp/my_case_assets",
    "--out", "/tmp/reel.mp4",
], check=True)
```
