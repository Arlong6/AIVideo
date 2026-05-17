"""Strip dark background from sprite PNGs.

Uses ABSOLUTE distance from sampled background color (NOT per-neighbor BFS).
Per-neighbor BFS walks along smooth gradients into the character body — the
Imagen-generated sprites have gradients from corner (dark navy ~34,45,65) to
mid-tones (~76,94,116) that touch the character's body color (~157,170,178),
which the BFS would chew through with delta < 50 at every step.

Strategy here: sample bg from corners + median-blur a wider border ring, then
mark any pixel within `threshold` of that bg color as transparent. This keeps
the character body fully intact regardless of gradient.

Usage:
    python -m pixel_battle.scripts.strip_backgrounds
"""
from pathlib import Path

import numpy as np
from PIL import Image

SPRITES_DIR = Path(__file__).resolve().parents[1] / "assets" / "sprites"


def strip_bg(img: Image.Image, threshold: float = 60.0,
             edge_width: int = 30) -> tuple:
    """Make background pixels transparent using per-row local bg reference.

    Imagen-generated sprites center the character horizontally. The leftmost
    and rightmost N pixels of each row are reliable bg samples — and being
    per-row, they correctly track any vertical gradient (e.g., glass_slab's
    bright-blue top → dark-navy bottom).

    For each row, we average the leftmost `edge_width` and rightmost
    `edge_width` pixels to estimate that row's bg color. Pixels within
    `threshold` Euclidean RGB distance of their row's bg become transparent.
    """
    arr = np.array(img.convert("RGBA"))
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.float32)

    # Per-row bg: mean of leftmost and rightmost edge_width pixels
    left_bg = rgb[:, :edge_width, :].mean(axis=1)    # (h, 3)
    right_bg = rgb[:, -edge_width:, :].mean(axis=1)  # (h, 3)
    row_bg = (left_bg + right_bg) / 2.0              # (h, 3)

    diff = rgb - row_bg[:, np.newaxis, :]            # (h, w, 3)
    dist = np.linalg.norm(diff, axis=2)              # (h, w)

    mask = dist < threshold
    arr[mask, 3] = 0
    avg_bg = row_bg.mean(axis=0)
    return Image.fromarray(arr), avg_bg, float(mask.mean() * 100)


def main() -> None:
    char_dirs = [d for d in SPRITES_DIR.iterdir() if d.is_dir()]
    if not char_dirs:
        print(f"No character directories found in {SPRITES_DIR}")
        return

    total = 0
    for char_dir in sorted(char_dirs):
        for src_path in sorted(char_dir.glob("*.png")):
            if src_path.stem.endswith("_alpha"):
                continue
            img = Image.open(src_path)
            result, bg, pct = strip_bg(img, threshold=55.0)
            out_path = src_path.with_name(src_path.stem + "_alpha.png")
            result.save(out_path)
            print(f"  {char_dir.name}/{src_path.name} -> bg≈{bg.astype(int).tolist()} "
                  f"({pct:.1f}% transparent)")
            total += 1

    print(f"\nDone. Processed {total} sprites.")


if __name__ == "__main__":
    main()
