# pixel_battle/tests/conftest.py
"""Suite-wide test fixtures.

Legacy render tests (stick_renderer/hud/impact_fx/weapons) build real,
unscaled pygame.Surface()s and assert unscaled pixel positions/sizes. Since
those modules now import the scaled_pygame shim and draw at the production
default S=2.25, an un-pinned test's drawn content lands at 2.25x-scaled
coordinates outside its own small unscaled surface. Force S=1.0 around every
test so these assertions keep matching what they were written against, and
restore whatever S was before (not a hardcoded 2.25) so a test that sets its
own scale explicitly — e.g. test_scaled_pygame.py, which drives S itself
per-test via `_fresh(scale)` / `set_scale(...)` — is unaffected either way.
"""
import pytest

from pixel_battle.rl import scaled_pygame as _scaled


@pytest.fixture(autouse=True)
def _unscaled_render_for_legacy_tests():
    prev = _scaled.S
    _scaled.set_scale(1.0)
    yield
    _scaled.set_scale(prev)
