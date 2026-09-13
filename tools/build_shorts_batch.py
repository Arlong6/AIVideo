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


def _rel(p) -> str:
    """Repo-relative path — absolute paths break the manifest when the
    checkout it was built in (e.g. a worktree) goes away."""
    return str(Path(p).resolve().relative_to(ROOT))


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
        "raw": _rel(raw),
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
    entry["short"] = _rel(out)
    entry["title"] = f"{left} VS {right}"
    return out


def _load_manifest() -> list:
    f = OUT_DIR / "manifest.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


if __name__ == "__main__":
    import sys

    names = _display_names()
    # Optional stem filters (e.g. `b03 b14`). Re-rendering only what changed
    # keeps the untouched renders — and any upload package already cut from
    # them — byte-identical, instead of churning all 21 for a 10-fight edit.
    wanted = [a for a in sys.argv[1:] if not a.startswith("-")]
    all_scripts = sorted(SCRIPTS.glob("b*.yaml"))
    scripts = ([s for s in all_scripts
                if any(s.name.startswith(w) for w in wanted)]
               if wanted else all_scripts)
    if wanted and not scripts:
        raise SystemExit(f"no fight script matched {wanted}")
    if wanted:
        print(f"rendering {len(scripts)} of {len(all_scripts)} fights: "
              f"{', '.join(s.stem for s in scripts)}\n")

    # Merge into the existing manifest so untouched fights keep their entries.
    prior = {e.get("script"): e for e in _load_manifest()}
    manifest = []
    for script in scripts:
        print(f"=== {script.name} ===", flush=True)
        try:
            entry = render_one(script)
            build_one(entry, names)
            manifest.append(entry)
            print(f"    {entry['title']} -> winner={entry['winner']}")
        except Exception as e:
            print(f"    FAILED: {type(e).__name__}: {e}")
            manifest.append({"script": script.name, "error": str(e)})
    for e in manifest:
        prior[e["script"]] = e
    merged = [prior[s.name] for s in all_scripts if s.name in prior]
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for m in manifest if "error" not in m)
    print(f"\nbuilt {ok}/{len(manifest)} (manifest holds {len(merged)} fights)")
