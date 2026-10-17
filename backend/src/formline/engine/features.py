"""Shot features (DATA_SCHEMA.md §6.1): deterministic, derived only from raw fields.

Everything here is a pure function of one shot event plus squad data (the
shooter's preferred foot), so it can be recomputed at any time from the event log.

xG and post-shot xG use fixed, documented logistic formulas. Their shape follows
the public football analytics literature (distance, angle, header, pressure,
blockers); only the intercepts are calibrated, to the league-average conversion
rate (~11%). They are deliberately NOT fitted to our synthetic outcomes, which
would just learn the generator back.
"""

from dataclasses import dataclass
from datetime import datetime
from math import exp, hypot, log, radians

from formline.pitch import (
    BOX_X,
    BOX_Y_HIGH,
    BOX_Y_LOW,
    GOAL_HEIGHT_M,
    GOAL_WIDTH_M,
    PITCH_LENGTH_M,
    PITCH_WIDTH_M,
    POST_HIGH_Y,
    POST_LOW_Y,
    SIX_YARD_X,
    SIX_YARD_Y_HIGH,
    SIX_YARD_Y_LOW,
    goal_angle_deg,
    goal_distance_m,
)
from formline.schema.events import ShotEvent
from formline.schema.reference import Player

PRESSURE_RADIUS_M = 2.3  # a defender this close = under pressure
CENTRAL_HALF_WIDTH_M = 9.0  # "central" = within 9 m of the goal's centre line
PENALTY_XG = 0.76

Zone = str  # six_yard, box_central, box_wide, outside_central, long_range
BodyGroup = str  # strong_foot, weak_foot, head, other
PressureBucket = str  # pressured, open


@dataclass(frozen=True)
class ShotFeatures:
    event_id: str
    match_id: str
    player_id: str
    team_id: str
    event_time: datetime
    period: int
    match_clock_ms: int
    key_pass_event_id: str | None
    shot_type: str
    outcome: str
    distance_m: float
    angle_deg: float
    zone: Zone
    body_group: BodyGroup
    pressure: PressureBucket
    nearest_defender_m: float | None
    defenders_in_cone: int
    gk_off_line_m: float | None
    shot_speed_kmh: float
    on_target: bool
    goal_y_m: float | None  # goal-mouth point, metres from the centre (on target only)
    goal_z_m: float | None
    placement: float | None  # 0 (straight at the keeper's centre) … 1 (top corner)
    xg: float
    psxg: float | None  # post-shot xG; on-target shots only


def _sigmoid(v: float) -> float:
    return 1 / (1 + exp(-v))


def zone_of(x: float, y: float) -> Zone:
    if x >= SIX_YARD_X and SIX_YARD_Y_LOW <= y <= SIX_YARD_Y_HIGH:
        return "six_yard"
    central = abs(y - 50) * PITCH_WIDTH_M / 100 <= CENTRAL_HALF_WIDTH_M
    if x >= BOX_X and BOX_Y_LOW <= y <= BOX_Y_HIGH:
        return "box_central" if central else "box_wide"
    if goal_distance_m(x, y) <= 25 and central:
        return "outside_central"
    return "long_range"


def body_group_of(body_part: str, player: Player | None) -> BodyGroup:
    if body_part in ("head", "other"):
        return body_part
    if player is None:
        return "strong_foot"
    strong = "left_foot" if player.preferred_foot == "left" else "right_foot"
    return "strong_foot" if body_part == strong else "weak_foot"


def _in_triangle(px: float, py: float, a, b, c) -> bool:
    def side(p1, p2, p3) -> float:
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1, d2, d3 = side((px, py), a, b), side((px, py), b, c), side((px, py), c, a)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


def _m(dx: float, dy: float) -> float:
    return hypot(dx * PITCH_LENGTH_M / 100, dy * PITCH_WIDTH_M / 100)


def placement_score(goal_y_m: float, goal_z_m: float) -> float:
    """How far from the keeper's reach the ball went: corners score high.

    Weighted mix of horizontal offset from the centre and vertical distance from
    the keeper's waist height (~1 m), each scaled to 0–1.
    """
    horizontal = min(1.0, abs(goal_y_m) / (GOAL_WIDTH_M / 2))
    vertical = min(1.0, abs(goal_z_m - 1.0) / (GOAL_HEIGHT_M - 1.0))
    return round(0.65 * horizontal + 0.35 * vertical, 3)


def xg_model(distance_m: float, angle_deg: float, body_group: BodyGroup, pressured: bool,
             defenders_in_cone: int, shot_type: str) -> float:
    if shot_type == "penalty":
        return PENALTY_XG
    logit = (-1.55 - 0.11 * distance_m + 1.6 * radians(angle_deg)
             - 0.9 * (body_group == "head") - 0.35 * pressured - 0.3 * defenders_in_cone)
    if shot_type == "free_kick":
        logit -= 0.4
    return round(_sigmoid(logit), 4)


def psxg_model(xg: float, placement: float, speed_kmh: float, distance_m: float) -> float:
    """Chance an on-target shot scores, given where and how hard it was struck."""
    base = min(0.999, xg)
    logit = (0.5 * (_logit(base) + 2.0) - 2.5 + 3.2 * placement
             + 0.035 * (speed_kmh - 75) - 0.03 * (distance_m - 12))
    return round(_sigmoid(logit), 4)


def _logit(p: float) -> float:
    return log(p / (1 - p))


def shot_features(shot: ShotEvent, player: Player | None = None) -> ShotFeatures:
    x, y = shot.x, shot.y
    distance = goal_distance_m(x, y)
    angle = goal_angle_deg(x, y)
    defenders = [p for p in shot.freeze_frame if not p.teammate and not p.goalkeeper]
    keeper = next((p for p in shot.freeze_frame if p.goalkeeper), None)
    nearest = min((_m(p.x - x, p.y - y) for p in defenders), default=None)
    pressured = nearest is not None and nearest < PRESSURE_RADIUS_M
    cone = (x, y), (100.0, POST_LOW_Y), (100.0, POST_HIGH_Y)
    in_cone = sum(_in_triangle(p.x, p.y, *cone) for p in defenders)
    body = body_group_of(shot.body_part, player)

    on_target = shot.outcome in ("goal", "saved")
    goal_y = goal_z = placement = psxg = None
    xg = xg_model(distance, angle, body, pressured, in_cone, shot.shot_type)
    if on_target:
        goal_y = round((shot.end_y - 50) * PITCH_WIDTH_M / 100, 2)
        goal_z = round(shot.end_z, 2)
        placement = placement_score(goal_y, goal_z)
        psxg = psxg_model(xg, placement, shot.tracking.shot_speed_kmh, distance)

    return ShotFeatures(
        event_id=shot.event_id,
        match_id=shot.match_id,
        player_id=shot.player_id,
        team_id=shot.team_id,
        event_time=shot.event_time,
        period=shot.period,
        match_clock_ms=shot.match_clock_ms,
        key_pass_event_id=shot.key_pass_event_id,
        shot_type=shot.shot_type,
        outcome=shot.outcome,
        distance_m=round(distance, 2),
        angle_deg=round(angle, 2),
        zone=zone_of(x, y),
        body_group=body,
        pressure="pressured" if pressured else "open",
        nearest_defender_m=None if nearest is None else round(nearest, 2),
        defenders_in_cone=in_cone,
        gk_off_line_m=None if keeper is None else round((100 - keeper.x) * 1.05, 2),
        shot_speed_kmh=shot.tracking.shot_speed_kmh,
        on_target=on_target,
        goal_y_m=goal_y,
        goal_z_m=goal_z,
        placement=placement,
        xg=xg,
        psxg=psxg,
    )
