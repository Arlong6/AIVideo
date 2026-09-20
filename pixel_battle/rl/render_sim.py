"""Advance a battle the way play.py's render loop advances it, without drawing.

The render loop does not tick the engine at a constant rate. Whenever slow-mo is
active it calls `battle.tick_ms(ENGINE_MS * dt_scale)` — around 2ms instead of
16.67ms — while still applying one scripted decision per frame. The choreography
therefore gets up to eight times as many decisions per engine-millisecond during
those stretches, and lands correspondingly more damage.

Any headless check that steps at a constant dt is measuring a different fight.
That went unnoticed while gen_fight left the ultimate's caster a 40 HP cushion,
which was wide enough to swallow the difference. Cutting the cushion to 16 for a
comeback arc made it visible immediately: the constant-dt loop reported the
caster reaching its ultimate with HP to spare, while the renderer killed it
first and handed the fight to the other side with the ultimate never firing.

Rules mirrored from `pixel_battle/rl/play.py`:

    hit         45ms  @ 0.12   (play.py:1578-1579)
    lethal hit  200ms @ 0.3    (play.py:1581-1583, 1610-1612)
    ultimate    150ms @ 0.3    (play.py:1957-1958)

`_slowmo_remaining_ms` is decremented by a full ENGINE_MS per frame whatever the
scale, exactly as the renderer does.

This is a model, not the renderer. It leaves out the KO and ultimate sequence
controllers, which impose their own dt_scale over their runs. It is much closer
than constant-dt stepping and it reproduces the failure above, but a change to
the HP budget should still be confirmed by one real render before a batch ships.
"""
from __future__ import annotations

ENGINE_MS = 1000.0 / 60

HIT_SLOWMO_MS, HIT_SLOWMO_SCALE = 45.0, 0.12
KO_SLOWMO_MS, KO_SLOWMO_SCALE = 200.0, 0.3
ULT_SLOWMO_MS, ULT_SLOWMO_SCALE = 150.0, 0.3


class RenderPacer:
    """Tracks slow-mo state across frames and steps the env like the renderer."""

    def __init__(self, env):
        self.env = env
        self.remaining_ms = 0.0
        self.scale = 1.0
        self._seen = 0

    def step(self, left_act: int, right_act: int) -> None:
        env, b = self.env, self.env.battle
        if self.remaining_ms > 0:
            self.remaining_ms -= ENGINE_MS
            env._apply_action(env.left, env.right, int(left_act))
            env._apply_action(env.right, env.left, int(right_act))
            b.tick_ms(int(ENGINE_MS * self.scale), skip_ai=True)
        else:
            self.scale = 1.0
            env.step((left_act, right_act))
        self._absorb_events()

    def _absorb_events(self) -> None:
        b = self.env.battle
        for ev in b.events[self._seen:]:
            et = ev.type.value
            if et == "hit":
                self.remaining_ms = max(self.remaining_ms, HIT_SLOWMO_MS)
                self.scale = min(self.scale, HIT_SLOWMO_SCALE)
            if et in ("hit", "crit"):
                # The renderer keys this off the struck fighter's HP, so look at
                # whichever side is not the actor.
                target = b.right if ev.actor == getattr(b.left, "id", None) else b.left
                if target.hp <= 0:
                    self.remaining_ms = max(self.remaining_ms, KO_SLOWMO_MS)
                    self.scale = KO_SLOWMO_SCALE
            elif et == "ultimate_start":
                self.remaining_ms = max(self.remaining_ms, ULT_SLOWMO_MS)
                self.scale = min(self.scale, ULT_SLOWMO_SCALE)
        self._seen = len(b.events)
