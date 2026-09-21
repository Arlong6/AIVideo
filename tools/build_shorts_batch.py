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


# On-screen hook. Kept next to the call that burns it in, so it cannot drift
# out of step with the caption language again.
HOOK_LINE = "WHO WINS?"


def _raw_is_intact(path: Path) -> bool:
    """Decode the tail of a raw render to prove it is not truncated.

    A render that gets killed part-way leaves a file that still opens, still
    reports a plausible duration, and still has a valid header — and then throws
    "Invalid NAL unit size" as soon as anything reads past the cut. build_short
    does not check, so it happily produced a 5-second short from a corrupt
    53-second raw and reported only a non-zero exit code.

    Decoding the last second is enough: truncation always lands at the end, and
    it costs a fraction of a full decode pass.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-sseof", "-1", "-i", str(path), "-f", "null", "-"],
        capture_output=True, text=True)
    return r.returncode == 0 and "Invalid NAL" not in r.stderr


def build_one(entry: dict, names: dict) -> Path:
    left = names.get(entry["left"], entry["left"]).upper()
    right = names.get(entry["right"], entry["right"]).upper()
    win_id = entry["left"] if entry["winner"] == "left" else entry["right"]
    win = names.get(win_id, win_id).upper()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_p = ROOT / entry["raw"]
    if not _raw_is_intact(raw_p):
        raise RuntimeError(
            f"raw render is truncated or corrupt: {entry['raw']}\n"
            "  A killed render leaves a file that looks valid until something\n"
            "  decodes past the cut. Re-render this fight before building.")
    out = OUT_DIR / (Path(entry["script"]).stem + ".mp4")
    # The timeline sidecar render_script writes next to the raw. Its absence is
    # normal for anything rendered before it existed — the short just builds
    # without the event-cued stickers.
    ev = (ROOT / entry["raw"]).with_name(Path(entry["raw"]).stem.replace("_raw", "")
                                         + "_events.json")
    subprocess.run([
        sys.executable, "-m", "pixel_battle.scripts.build_short",
        entry["raw"], str(out),
        # The channel went English-first on 2026-09-19 (captions, bio, display
        # name). The burnt-in hook was still Chinese, so a viewer read an English
        # caption and then saw 「誰會贏?」 on the video itself.
        HOOK_LINE, f"{left} VS {right}", f"{win} WINS", CUT_START,
    ] + (["--events", str(ev)] if ev.exists() else []), check=True, cwd=str(ROOT))
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
