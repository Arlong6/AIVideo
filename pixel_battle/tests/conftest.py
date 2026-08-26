"""Shared pytest fixtures for pixel_battle tests.

Render-module unit tests (stick_renderer, hud, weapons, impact_fx, ...) build
their own small `pygame.Surface` fixtures and assert drawn-pixel positions in
raw fight coordinates. As of Task 7 of the native-hi-res plan, those modules
draw through `scaled_pygame`, which defaults to S=2.25 for production video
output — so the same raw-coordinate assertions would otherwise land outside
a same-sized-as-before real Surface.

`scaled_pygame.set_scale(1.0)` is documented as an exact identity (see its
docstring), so forcing it around every test keeps existing raw-coordinate
assertions meaningful without touching each test file. Tests that care about
a specific scale (test_scaled_pygame.py) already set it explicitly via their
own `_fresh()` helper, so this default is simply overridden there.
"""
import pytest

from pixel_battle.rl import scaled_pygame as _scaled_pygame


@pytest.fixture(autouse=True)
def _reset_render_scale():
    prev = _scaled_pygame.S
    _scaled_pygame.set_scale(1.0)
    yield
    _scaled_pygame.set_scale(prev)
