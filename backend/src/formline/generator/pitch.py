"""Pitch geometry in the 0–100 coordinate system (attacking toward x = 100)."""

from math import atan2, degrees, hypot

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
GOAL_WIDTH_M = 7.32
GOAL_HEIGHT_M = 2.44

GOAL_Y = 50.0
POST_LOW_Y = GOAL_Y - (GOAL_WIDTH_M / 2) / PITCH_WIDTH_M * 100  # ≈ 44.62
POST_HIGH_Y = GOAL_Y + (GOAL_WIDTH_M / 2) / PITCH_WIDTH_M * 100  # ≈ 55.38
BOX_X = 100 - 16.5 / PITCH_LENGTH_M * 100  # ≈ 84.29
BOX_Y_LOW = GOAL_Y - 20.16 / PITCH_WIDTH_M * 100  # ≈ 20.35
BOX_Y_HIGH = GOAL_Y + 20.16 / PITCH_WIDTH_M * 100  # ≈ 79.65


def clamp(v: float, lo: float = 0.5, hi: float = 99.5) -> float:
    return max(lo, min(hi, v))


def to_m(dx: float, dy: float) -> float:
    """Distance in meters between two points given their coordinate deltas."""
    return hypot(dx * PITCH_LENGTH_M / 100, dy * PITCH_WIDTH_M / 100)


def goal_distance_m(x: float, y: float) -> float:
    return to_m(100 - x, GOAL_Y - y)


def goal_angle_deg(x: float, y: float) -> float:
    """Angle the goal mouth subtends from (x, y): wider is easier."""
    gx = (100 - x) * PITCH_LENGTH_M / 100
    y1 = (POST_LOW_Y - y) * PITCH_WIDTH_M / 100
    y2 = (POST_HIGH_Y - y) * PITCH_WIDTH_M / 100
    return abs(degrees(atan2(y2, gx) - atan2(y1, gx)))


def in_box(x: float, y: float) -> bool:
    return x >= BOX_X and BOX_Y_LOW <= y <= BOX_Y_HIGH


def mirror(x: float, y: float) -> tuple[float, float]:
    """The same spot seen from the other team's attacking direction."""
    return 100 - x, 100 - y
