"""Path 2 Task A: Generate animation keyframes via Gemini 2.5 Flash Image i2i.

Per character (brick_phone, glass_slab), generates 8 keyframes:
  - attack_windup, attack_strike, attack_recover
  - hit_recoil
  - ko_falling, ko_landed
  - special_charge
  - ultimate_pose

Plus the existing base (brick_phone_1.png / glass_slab_2.png) serves as IDLE.

Output: pixel_battle/assets/sprites/{char_id}/{pose}.png
Cost: ~$0.80-1.20 total (16 i2i calls)
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

SRC = ROOT / "pixel_battle" / "assets" / "sprite_proto"
OUT_BASE = ROOT / "pixel_battle" / "assets" / "sprites"

def pixel_art_finalize(img: Image.Image, palette_colors: int = 16,
                       target_px: int = 512) -> Image.Image:
    """Force a real pixel grid: downsample → quantize → NEAREST upscale.

    Steps:
      1. Resize to 128x128 (LANCZOS for clean detail capture)
      2. Quantize to `palette_colors` colors (MEDIANCUT, no dithering)
      3. NEAREST upscale to `target_px` so each pixel is a 4x4 block
    """
    grid = 128
    small = img.convert("RGB").resize((grid, grid), Image.LANCZOS)
    quant = small.quantize(colors=palette_colors,
                           method=Image.MEDIANCUT,
                           dither=Image.NONE)
    return quant.convert("RGB").resize((target_px, target_px), Image.NEAREST)


BASES = {
    "brick_phone": SRC / "brick_phone_1.png",
    "glass_slab": SRC / "glass_slab_2.png",
}

GEMINI_IMG_MODEL = "gemini-2.5-flash-image"

PRESERVE = (
    "Preserve the EXACT character design, colors, proportions, face design, and pixel art style. "
    "Same dark navy/purple background. Same isolated character with clear silhouette. "
    "16-bit fighting game sprite. Only change the pose as described."
)

POSES = {
    "attack_windup": "Modify the image to show the same character in an attack windup pose: "
                     "leaning slightly backward, fists pulled back near the body, weight shifted onto back foot, "
                     "eyes narrowed and focused. " + PRESERVE,

    "attack_strike": "Modify the image to show the same character in an attack strike pose: "
                     "leaning aggressively forward, one fist thrust forward in a punch, "
                     "the other arm pulled back for balance, weight on front foot. " + PRESERVE,

    "attack_recover": "Modify the image to show the same character in attack recovery pose: "
                      "returning to neutral, arms dropping back to sides, slight forward lean. " + PRESERVE,

    "hit_recoil": "Modify the image to show the same character recoiling from a hit: "
                  "leaning sharply backward, head tilted up, arms up defensively, "
                  "eyes squinted in pain, body slightly twisted. " + PRESERVE,

    "ko_falling": "Modify the image to show the same character falling backward in mid-air after a knockout: "
                  "body horizontal, arms loose, face shows X eyes or dazed expression, "
                  "small motion lines around the body. " + PRESERVE,

    "ko_landed": "Modify the image to show the same character knocked out on the ground: "
                 "lying horizontally on its back, eyes as X marks, small dizzy stars or birds circling above, "
                 "completely flat. " + PRESERVE,

    "special_charge": "Modify the image to show the same character charging up a special attack: "
                      "arms out wide, energy aura visible around the body, glowing eyes, "
                      "feet planted in a power stance, fierce expression. " + PRESERVE,

    "ultimate_pose": "Modify the image to show the same character in a dramatic ultimate-skill ready pose: "
                     "low fighting stance, one fist raised high, intense glowing eyes, "
                     "bold silhouette, like a fighting game super move portrait. " + PRESERVE,
}


def gen_pose(client, base_image: Image.Image, instruction: str, out_path: Path) -> bool:
    try:
        r = client.models.generate_content(
            model=GEMINI_IMG_MODEL,
            contents=[base_image, instruction],
        )
        for cand in r.candidates:
            for part in cand.content.parts:
                if hasattr(part, "inline_data") and part.inline_data and part.inline_data.data:
                    out_path.write_bytes(part.inline_data.data)
                    return True
        return False
    except Exception as e:
        print(f"    error: {str(e)[:200]}")
        return False


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set")
        sys.exit(1)
    client = genai.Client(api_key=api_key)

    total_ok = 0
    total_fail = 0

    for char_id, base_path in BASES.items():
        if not base_path.exists():
            print(f"  [SKIP] {char_id}: base sprite missing at {base_path}")
            continue

        out_dir = OUT_BASE / char_id
        out_dir.mkdir(parents=True, exist_ok=True)

        # Copy base as idle.png
        base_img = Image.open(base_path)
        idle_out = out_dir / "idle.png"
        base_img.save(idle_out)
        print(f"\n=== {char_id} ===")
        print(f"  [base] idle.png copied from {base_path.name}")

        for pose_name, instr in POSES.items():
            out_path = out_dir / f"{pose_name}.png"
            print(f"  generating {pose_name}...", end=" ", flush=True)
            if gen_pose(client, base_img, instr, out_path):
                size_kb = out_path.stat().st_size // 1024
                print(f"ok ({size_kb} KB)")
                total_ok += 1
            else:
                print("FAIL")
                total_fail += 1

    print(f"\n=== Summary ===")
    print(f"  OK:   {total_ok}")
    print(f"  FAIL: {total_fail}")
    print(f"  Output: {OUT_BASE}")
    print(f"  Approx cost: ~${total_ok * 0.04:.2f}")


if __name__ == "__main__":
    main()
