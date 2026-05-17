"""Strip dark navy/purple background from sprite PNGs using flood-fill from corners.

Usage:
    python -m pixel_battle.scripts.strip_backgrounds
"""
from pathlib import Path

import numpy as np
from PIL import Image

SPRITES_DIR = Path(__file__).resolve().parents[1] / "assets" / "sprites"


def strip_bg(img: Image.Image, threshold: int = 50) -> Image.Image:
    """Remove background pixels by flood-filling from all 4 corners.

    Each corner seeds a BFS; a pixel is considered background if its RGB distance
    from the *local* seed pixel's color is within `threshold`.  Using the seed
    pixel's own color (rather than a global median) handles gradients like the
    glass_slab sprites whose top is blue and bottom is dark navy.
    """
    arr = np.array(img.convert("RGBA"))
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(float)

    visited = np.zeros((h, w), dtype=bool)
    queue: list[tuple[int, int]] = []

    for r, c in [(0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)]:
        if not visited[r, c]:
            visited[r, c] = True
            queue.append((r, c))

    while queue:
        r, c = queue.pop()
        seed_color = rgb[r, c]  # reference each pixel against its immediate neighbor
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and not visited[nr, nc]:
                dist = float(np.linalg.norm(rgb[nr, nc] - seed_color))
                if dist < threshold:
                    visited[nr, nc] = True
                    queue.append((nr, nc))

    # Make all flood-filled pixels transparent
    arr[visited, 3] = 0
    return Image.fromarray(arr)


def main() -> None:
    char_dirs = [d for d in SPRITES_DIR.iterdir() if d.is_dir()]
    if not char_dirs:
        print(f"No character directories found in {SPRITES_DIR}")
        return

    total = 0
    for char_dir in sorted(char_dirs):
        for src_path in sorted(char_dir.glob("*.png")):
            # Skip already-processed alpha variants
            if src_path.stem.endswith("_alpha"):
                continue
            img = Image.open(src_path)
            result = strip_bg(img, threshold=50)
            out_path = src_path.with_name(src_path.stem + "_alpha.png")
            result.save(out_path)
            # Quick sanity: verify transparency was added
            arr = np.array(result)
            transparent_px = int((arr[:, :, 3] == 0).sum())
            total_px = arr.shape[0] * arr.shape[1]
            pct = 100.0 * transparent_px / total_px
            print(f"  {char_dir.name}/{src_path.name} -> {out_path.name}  "
                  f"({pct:.1f}% transparent)")
            total += 1

    print(f"\nDone. Processed {total} sprites.")


if __name__ == "__main__":
    main()
