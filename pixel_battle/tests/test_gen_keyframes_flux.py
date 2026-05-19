"""Tests for the FLUX-based keyframe generator."""
import numpy as np
from PIL import Image

# Add scripts dir to path for the gen_keyframes module
import importlib.util
import pathlib

_p = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "gen_keyframes.py"
spec = importlib.util.spec_from_file_location("gen_keyframes", _p)
gen_keyframes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen_keyframes)


def test_pixel_art_finalize_outputs_target_size():
    src = Image.new("RGB", (1024, 1024), color=(123, 45, 200))
    out = gen_keyframes.pixel_art_finalize(src, palette_colors=16, target_px=512)
    assert out.size == (512, 512)


def test_pixel_art_finalize_quantizes_palette():
    """Output should have <= palette_colors unique colors."""
    rng = np.random.default_rng(42)
    arr = rng.integers(0, 256, size=(1024, 1024, 3), dtype=np.uint8)
    src = Image.fromarray(arr, mode="RGB")
    out = gen_keyframes.pixel_art_finalize(src, palette_colors=16, target_px=512)
    unique = len({tuple(p) for p in np.array(out).reshape(-1, 3)})
    assert unique <= 16, f"expected <=16 colors, got {unique}"


def test_pixel_art_finalize_creates_pixel_grid():
    """Each 'pixel' should be a 4x4 block (NEAREST upscale from 128 to 512)."""
    # Use a sharp 2-color pattern so we can detect block boundaries
    src = Image.new("RGB", (128, 128))
    pix = src.load()
    for x in range(128):
        for y in range(128):
            pix[x, y] = (255, 0, 0) if (x + y) % 2 == 0 else (0, 0, 255)
    out = gen_keyframes.pixel_art_finalize(src, palette_colors=2, target_px=512)
    # Sample a 4x4 block — all pixels should match
    out_arr = np.array(out)
    block = out_arr[0:4, 0:4]
    assert (block == block[0, 0]).all(), "4x4 block should be solid (NEAREST upscale)"


def test_poses_has_eleven_entries_with_jumps():
    assert len(gen_keyframes.POSES) == 11
    for required in ("attack_windup", "attack_strike", "attack_recover",
                     "hit_recoil", "ko_falling", "ko_landed",
                     "special_charge", "ultimate_pose",
                     "jump_up", "jump_apex", "jump_land"):
        assert required in gen_keyframes.POSES, f"missing pose: {required}"


def test_kontext_model_constant():
    assert gen_keyframes.KONTEXT_MODEL == "fal-ai/flux-pro/kontext"
