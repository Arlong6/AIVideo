"""2D physics primitives for melee battle."""

# World — characters live in a horizontal arena 480 wide
ARENA_LEFT = 10
ARENA_RIGHT = 470
GROUND_Y = 530  # feet landing position; matches renderer HORIZON_Y

# Engagement zone — kept at the original 60-420 range.
# Used by: (1) AI retreat/wall-stuck checks in battle.py so the AI still
# turns around at the same absolute positions it did before the arena widened,
# and (2) Flash teleport clamping so scripted flash:back calls don't push
# characters further than the scripts were tuned for.
AI_ENGAGE_LEFT = 44
AI_ENGAGE_RIGHT = 436
FLASH_ARENA_LEFT = AI_ENGAGE_LEFT
FLASH_ARENA_RIGHT = AI_ENGAGE_RIGHT

# Motion
WALK_SPEED = 4.5           # px/frame — 60% faster for snappy approach/retreat
JUMP_VELOCITY = -14.0       # upward impulse (y is screen-down)
GRAVITY = 0.85              # px/frame²
MAX_FALL_SPEED = 18.0
GROUND_FRICTION = 0.85      # vel_x decay per frame when on ground and no input
FLASH_DISTANCE = 130        # px a Flash teleports
FLASH_COOLDOWN_MS = 3500    # Flash recharge time

# Combat
MELEE_RANGE = 110           # horizontal distance for basic attack to connect
SPECIAL_RANGE = 130         # special skill reach
MAX_ATTACK_RANGE = 360      # upper bound for the env pre-fire gate on cd/special
ULTIMATE_TRIGGER_DISTANCE = 999  # ultimates always connect (no range gate)


def apply_gravity(vel_y: float) -> float:
    return min(MAX_FALL_SPEED, vel_y + GRAVITY)


def clamp_x(x: float) -> float:
    return max(ARENA_LEFT, min(ARENA_RIGHT, x))
