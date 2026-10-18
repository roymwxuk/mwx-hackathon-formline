"""Team shape: where each player wants to be, given the ball and who has it.

Positions here are in a team's own attacking frame (attacking toward x = 100, y < 50 the
right flank, as in the events). `to_shared` converts to the tracking frame, where the home
team attacks toward x = 100 in both periods.

The model is deliberately simple and readable: a 4-3-3 with one anchor spot per role, then
- the block moves up and down with the ball (more in possession, held back out of it),
- it slides toward the ball's side,
- it stretches in possession and compacts without the ball (about 25–40 m deep),
- the goalkeeper stays near his goal line, shading toward the ball;
- players near the ball are drawn toward it (support or press).
Event anchors and motion limits (later tasks) turn these targets into real paths.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import exp

from formline.pitch import PITCH_LENGTH_M, clamp, to_m

# Role anchors (x, y) in the own attacking frame for a neutral ball at the centre spot.
# DM and ST sit slightly right of centre: mirrored into the shared frame, one side's DM and
# the other side's ST then stand about 5 m apart instead of on the same spot.
ROLE_SPOTS: Mapping[str, tuple[float, float]] = {
    "GK": (5.0, 50.0),
    "RB": (30.0, 14.0), "RCB": (24.0, 37.0), "LCB": (24.0, 63.0), "LB": (30.0, 86.0),
    "DM": (38.0, 46.0), "RCM": (48.0, 34.0), "LCM": (48.0, 66.0),
    "RW": (60.0, 14.0), "ST": (63.0, 46.0), "LW": (60.0, 86.0),
}
ROLE_LINE = {"GK": 0, "RB": 1, "RCB": 1, "LCB": 1, "LB": 1, "DM": 2, "RCM": 2, "LCM": 2,
             "RW": 3, "ST": 3, "LW": 3}

# How the block follows the ball: (longitudinal follow, push up, depth scale, width scale).
IN_POSSESSION = (0.55, 6.0, 1.15, 1.0)
OUT_OF_POSSESSION = (0.45, -4.0, 0.72, 0.72)  # a loose ball blends the two halfway
SLIDE = 0.3  # lateral shift toward the ball's side
# Players near the ball are drawn toward it (support in possession, pressing without it),
# with a pull that fades with distance (Gaussian, ATTRACT_M): events happen near the ball.
ATTRACT_IN = 0.35
ATTRACT_OUT = 0.5
ATTRACT_M = 18.0
BLOCK_CENTRE_X = 38.0  # the outfield block's centre for a ball at the centre spot
OUTFIELD_MIN_X = 7.5  # deepest an outfield player stands (just in front of the keeper)


@dataclass(frozen=True)
class Slot:
    shirt: int
    role: str


def assign_roles(starters: Iterable[tuple[int, str]]) -> list[Slot]:
    """Starting XI `(shirt, position)` to slots. Positions are the squad's (GK, RB, CB, LB,
    DM, CM, AM, RW, ST, LW): the two centre backs split into right and left by shirt order,
    and the CM and AM fill the right and left central midfield spots."""
    slots, cbs = [], []
    for shirt, position in starters:
        if position == "CB":
            cbs.append(shirt)
            continue
        role = {"CM": "RCM", "AM": "LCM"}.get(position, position)
        if role not in ROLE_SPOTS:
            raise ValueError(f"no shape role for position {position}")
        slots.append(Slot(shirt, role))
    for shirt, role in zip(sorted(cbs), ("RCB", "LCB"), strict=False):
        slots.append(Slot(shirt, role))
    return slots


def _attack_level(in_possession: bool | float | None) -> float:
    """1 = in possession, 0 = without the ball, 0.5 = neither; floats blend between shapes
    (the motion model eases from one shape to the other after a turnover)."""
    if in_possession is None:
        return 0.5
    return float(in_possession)


def team_shape(slots: Iterable[Slot], ball: tuple[float, float],
               in_possession: bool | float | None, *, kickoff: bool = False
               ) -> dict[int, tuple[float, float]]:
    """Target spot per shirt in the own attacking frame. `in_possession` None means neither
    team controls the ball (a loose ball or a stoppage); a float between 0 and 1 blends the
    shapes without and with the ball."""
    bx, by = ball
    level = _attack_level(in_possession)
    follow, push, depth, width = (o + (i - o) * level
                                  for o, i in zip(OUT_OF_POSSESSION, IN_POSSESSION, strict=True))
    centre = BLOCK_CENTRE_X + push + follow * (bx - 50)
    out: dict[int, tuple[float, float]] = {}
    for slot in slots:
        sx, sy = ROLE_SPOTS[slot.role]
        if slot.role == "GK":
            x = 5.0 + (6.0 * level if bx > 50 else 0.0) + 0.04 * max(0.0, bx - 50)
            y = 50 + 0.3 * (by - 50)
            out[slot.shirt] = (clamp(x, 1.0, 16.0), clamp(y, 40.0, 60.0))
            continue
        x = centre + (sx - BLOCK_CENTRE_X) * depth
        y = 50 + (sy - 50) * width + SLIDE * (by - 50)
        if not kickoff:
            pull = ATTRACT_OUT + (ATTRACT_IN - ATTRACT_OUT) * level
            d = to_m(bx - x, by - y)
            k = pull * exp(-((d / ATTRACT_M) ** 2))
            x, y = x + (bx - x) * k, y + (by - y) * k
        if kickoff:  # everyone in his own half, a step back from the ball
            x = min(x * 0.85, 48.0)
        # Outfield players never drop behind the keeper (he stays within 5 + ~2 of his line).
        out[slot.shirt] = (clamp(x, OUTFIELD_MIN_X, 98.0), clamp(y, 2.0, 98.0))
    return out


def to_shared(point: tuple[float, float], home: bool) -> tuple[float, float]:
    """Own attacking frame <-> shared tracking frame (the conversion is its own inverse)."""
    x, y = point
    return (x, y) if home else (100 - x, 100 - y)


def depth_m(shape: Mapping[int, tuple[float, float]], slots: Iterable[Slot]) -> float:
    """Outfield block depth in meters: deepest defender to highest forward."""
    xs = [shape[s.shirt][0] for s in slots if s.role != "GK"]
    return (max(xs) - min(xs)) * PITCH_LENGTH_M / 100
