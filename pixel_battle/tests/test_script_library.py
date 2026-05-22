"""Every shipped fight script loads + validates."""
from pathlib import Path

from pixel_battle.script.loader import load_script

_SCRIPT_DIR = Path(__file__).resolve().parents[1] / "data" / "scripts"


def test_all_scripts_load():
    scripts = sorted(_SCRIPT_DIR.glob("*.yaml"))
    assert len(scripts) >= 5, "expected at least 5 starter scripts"
    for path in scripts:
        s = load_script(path)               # raises ScriptError if invalid
        assert s.left and s.right
        assert s.left_intents and s.right_intents
