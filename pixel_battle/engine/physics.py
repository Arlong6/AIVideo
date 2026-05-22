"""2D physics primitives for melee battle."""

# World — characters live in a horizontal arena 480 wide
ARENA_LEFT = 60
ARENA_RIGHT = 420
GROUND_Y = 530  # feet landing position; matches renderer HORIZON_Y

# Motion
WALK_SPEED = 2.8           # px/frame
JUMP_VELOCITY = -14.0       # upward impulse (y is screen-down)
GRAVITY = 0.85              # px/frame²
MAX_FALL_SPEED = 18.0
GROUND_FRICTION = 0.85      # vel_x decay per frame when on ground and no input

# Combat
MELEE_RANGE = 110           # horizontal distance for basic attack to connect
SPECIAL_RANGE = 130         # special skill reach
MAX_ATTACK_RANGE = 360      # upper bound for the env pre-fire gate on cd/special
ULTIMATE_TRIGGER_DISTANCE = 999  # ultimates always connect (no range gate)


def apply_gravity(vel_y: float) -> float:
    return min(MAX_FALL_SPEED, vel_y + GRAVITY)


def clamp_x(x: float) -> float:
    return max(ARENA_LEFT, min(ARENA_RIGHT, x))
