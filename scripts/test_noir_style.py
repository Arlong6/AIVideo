"""
A.1 — Visual style validation for the noir long-form upgrade.

Generates 4 representative crime scenes with a candidate neo-noir style
prefix so arlong can eyeball the look BEFORE we refactor visual_agent.

Scenes deliberately cover the safety-filter danger zone using "oblique
framing": aftermath instead of act, setting instead of subject, objects
instead of people. If Imagen blocks any of these we know the prefix
+ framing pattern won't survive production.

Run:
    python3 scripts/test_noir_style.py
Output:
    data/noir_style_test/scene_{1..4}.png
Cost: ~$0.08 (4 × Imagen Fast).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "data" / "noir_style_test"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Candidate neo-noir prefix. Anchors chosen:
#  - "neo-noir crime aesthetic"        → distinct genre target
#  - "extreme chiaroscuro"             → trademark noir lighting
#  - "desaturated near-monochrome"     → kills the bright stock-photo look
#  - "single hard practical light"     → motivated lighting, looks cinematic
#  - "heavy 35mm film grain"           → period gravity
#  - "no faces, no people"             → safety filter + matches faceless
#                                        channel positioning
NOIR_PREFIX = (
    "cinematic 16:9, neo-noir crime film aesthetic, "
    "extreme chiaroscuro lighting with deep shadows obscuring half the frame, "
    "desaturated near-monochrome palette, cool steel-blue and amber sodium tones, "
    "single hard practical light source like a streetlight or naked bulb or neon sign, "
    "heavy 35mm film grain, atmospheric haze, dust motes in the light beam, "
    "ominous oppressive mood, empty abandoned space, "
    "no text, no watermark, no faces, no people, no humans, "
    "shot on ARRI Alexa, of "
)

# 4 scenes chosen to stress the safety filter + cover narrative range
SCENES = [
    ("aftermath", "tea house at night after closing, overturned wooden chair, "
                  "police evidence markers on tiled floor, ceiling fan motionless, "
                  "yellow police tape across doorway"),
    ("investigation", "detective desk covered in case files and crime scene photos, "
                      "vintage brass table lamp casting harsh angled shadow, "
                      "cold coffee cup, magnifying glass, ashtray with cigarette stub"),
    ("location", "abandoned subway platform after midnight, fluorescent tubes "
                 "flickering, empty wooden bench, security camera dome on ceiling, "
                 "single forgotten umbrella on the floor"),
    ("exterior", "courthouse exterior in heavy rain at dusk, neon sign reflection "
                 "on wet pavement, lone newspaper blowing across stone steps, "
                 "puddles catching streetlight glow"),
]


def main():
    from google import genai
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not set.")
        return 1

    client = genai.Client(api_key=api_key)

    print("=== Noir style test ===")
    print(f"Prefix: {NOIR_PREFIX[:80]}...")
    print(f"Generating {len(SCENES)} scenes...\n")

    results = []
    for i, (tag, scene) in enumerate(SCENES, 1):
        full_prompt = NOIR_PREFIX + scene
        out_path = OUT_DIR / f"scene_{i}_{tag}.png"
        print(f"[{i}/{len(SCENES)}] {tag}: {scene[:60]}...")
        try:
            resp = client.models.generate_images(
                model="imagen-4.0-fast-generate-001",
                prompt=full_prompt,
                config={"number_of_images": 1, "aspect_ratio": "16:9"},
            )
            imgs = getattr(resp, "generated_images", None) or []
            if not imgs:
                print(f"  ❌ BLOCKED or empty response (safety filter likely)")
                results.append((tag, "blocked", None))
                continue
            img = imgs[0]
            img_bytes = img.image.image_bytes
            out_path.write_bytes(img_bytes)
            sz_kb = out_path.stat().st_size // 1024
            print(f"  ✅ {out_path.name} ({sz_kb} KB)")
            results.append((tag, "ok", str(out_path)))
        except Exception as e:
            err = str(e)[:200]
            print(f"  ❌ ERROR: {err}")
            results.append((tag, "error", err))

    print("\n=== Summary ===")
    ok = sum(1 for _, s, _ in results if s == "ok")
    blocked = sum(1 for _, s, _ in results if s == "blocked")
    err = sum(1 for _, s, _ in results if s == "error")
    print(f"✅ {ok}/{len(SCENES)} generated, 🚫 {blocked} blocked, ⚠️ {err} errors")
    print(f"\nOpen: {OUT_DIR}")
    for tag, status, path in results:
        if status == "ok":
            print(f"  open '{path}'")
    return 0 if ok == len(SCENES) else 1


if __name__ == "__main__":
    sys.exit(main())
