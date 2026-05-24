"""Every shipped fight script loads + validates."""
from pathlib import Path

import pytest

from pixel_battle.script.loader import load_script

_SCRIPT_DIR = Path(__file__).resolve().parents[1] / "data" / "scripts" / "legacy"


def test_all_scripts_load():
    scripts = sorted(_SCRIPT_DIR.glob("*.yaml"))
    assert len(scripts) >= 5, "expected at least 5 starter scripts"
    for path in scripts:
        s = load_script(path)               # raises ScriptError if invalid
        assert s.left and s.right
        assert s.left_intents and s.right_intents


def test_script_matchup_and_depth():
    """No mirror matchups; each side must have at least 3 intents."""
    scripts = sorted(_SCRIPT_DIR.glob("*.yaml"))
    assert len(scripts) >= 5, "expected at least 5 starter scripts"
    for path in scripts:
        s = load_script(path)
        assert s.left != s.right, (
            f"{path.name}: mirror matchup — left and right are both {s.left!r}"
        )
        assert len(s.left_intents) >= 3, (
            f"{path.name}: left_intents has only {len(s.left_intents)} intent(s); minimum 3"
        )
        assert len(s.right_intents) >= 3, (
            f"{path.name}: right_intents has only {len(s.right_intents)} intent(s); minimum 3"
        )


@pytest.mark.parametrize(
    "script_path",
    sorted(_SCRIPT_DIR.glob("*.yaml")),
    ids=lambda p: p.name,
)
def test_script_has_ko_finisher(script_path):
    """Every script must contain at least one intent whose `until` is exactly
    `target_hp<=0`.  Without this guard, the episode can end without a KO."""
    s = load_script(script_path)
    all_intents = s.left_intents + s.right_intents
    has_finisher = any(i.until_src == "target_hp<=0" for i in all_intents)
    assert has_finisher, (
        f"{script_path.name}: no intent with until='target_hp<=0' found — "
        "script is missing a KO finisher"
    )
