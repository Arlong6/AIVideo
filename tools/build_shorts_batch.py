"""Render every b*.yaml and build a posting-ready short for each.

Writes output/shorts/manifest.json recording matchup and winner — this
replaces the old POSTING.md, which was gitignored and lost with the
previous render batch.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPTS = ROOT / "pixel_battle/data/scripts"
RAW_DIR = ROOT / "pixel_battle/output/scripted"
OUT_DIR = ROOT / "pixel_battle/output/shorts"
CUT_START = "1.5"


def _display_names() -> dict:
    data = json.loads((ROOT / "pixel_battle/data/characters.json")
                      .read_text(encoding="utf-8"))
    return {k: v.get("display_name", k) for k, v in data.items()}


def render_one(script_path: Path) -> dict:
    """Render one fight, returning its matchup and winner."""
    import yaml
    import pixel_battle.rl.play_scripted as ps

    captured: dict = {}
    orig = ps._render_fight

    def _tap(*a, **k):
        r = orig(*a, **k)
        captured.update(r)
        return r

    ps._render_fight = _tap
    try:
        raw = ps.render_script(script_path)
    finally:
        ps._render_fight = orig

    meta = yaml.safe_load(script_path.read_text(encoding="utf-8"))
    return {
        "script": script_path.name,
        "raw": str(raw),
        "left": meta.get("left"),
        "right": meta.get("right"),
        "winner": captured.get("winner"),
    }


def build_one(entry: dict, names: dict) -> Path:
    left = names.get(entry["left"], entry["left"]).upper()
    right = names.get(entry["right"], entry["right"]).upper()
    win_id = entry["left"] if entry["winner"] == "left" else entry["right"]
    win = names.get(win_id, win_id).upper()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / (Path(entry["script"]).stem + ".mp4")
    subprocess.run([
        sys.executable, "-m", "pixel_battle.scripts.build_short",
        entry["raw"], str(out),
        "誰會贏?", f"{left} VS {right}", f"{win} WINS", CUT_START,
    ], check=True, cwd=str(ROOT))
    entry["short"] = str(out)
    entry["title"] = f"{left} VS {right}"
    return out


if __name__ == "__main__":
    names = _display_names()
    manifest = []
    for script in sorted(SCRIPTS.glob("b*.yaml")):
        print(f"=== {script.name} ===", flush=True)
        try:
            entry = render_one(script)
            build_one(entry, names)
            manifest.append(entry)
            print(f"    {entry['title']} -> winner={entry['winner']}")
        except Exception as e:
            print(f"    FAILED: {type(e).__name__}: {e}")
            manifest.append({"script": script.name, "error": str(e)})
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for m in manifest if "error" not in m)
    print(f"\nbuilt {ok}/{len(manifest)}")
