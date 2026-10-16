"""Match events (DATA_SCHEMA.md §4–5) as one discriminated union on `type`.

Coordinates: 0–100 on both axes, normalized so the acting team attacks toward
x = 100 in both periods. Meters: x_m = x * 1.05, y_m = y * 0.68.
Match-level events (half_start, half_end, VAR) have no team, player or location.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

PlayPattern = Literal[
    "regular_play",
    "from_counter",
    "from_corner",
    "from_free_kick",
    "from_throw_in",
    "from_goal_kick",
    "from_kick_off",
]


class FreezeFramePlayer(BaseModel):
    x: float
    y: float
    teammate: bool
    goalkeeper: bool


class ShotTracking(BaseModel):
    shot_speed_kmh: float


class PassTracking(BaseModel):
    ball_speed_kmh: float


class EventBase(BaseModel):
    event_id: str
    match_id: str
    period: Literal[1, 2]
    match_clock_ms: int
    event_time: datetime
    team_id: str | None
    player_id: str | None
    position: str | None
    possession: int
    possession_team_id: str | None
    play_pattern: PlayPattern
    x: float | None
    y: float | None
    under_pressure: bool = False
    duration_ms: int | None = None
    related_event_ids: list[str] = []


class ShotEvent(EventBase):
    type: Literal["shot"] = "shot"
    body_part: Literal["left_foot", "right_foot", "head", "other"]
    technique: Literal[
        "normal", "volley", "half_volley", "lob", "backheel", "diving_header", "overhead_kick"
    ]
    shot_type: Literal["open_play", "free_kick", "penalty", "corner"]
    first_time: bool
    deflected: bool
    end_x: float
    end_y: float
    end_z: float = Field(description="Height in meters where the shot ended")
    outcome: Literal["goal", "saved", "off_target", "post", "blocked"]
    key_pass_event_id: str | None
    freeze_frame: list[FreezeFramePlayer]
    tracking: ShotTracking


class PassEvent(EventBase):
    type: Literal["pass"] = "pass"
    recipient_id: str | None
    end_x: float
    end_y: float
    length_m: float
    height: Literal["ground", "low", "high"]
    pass_type: Literal["open_play", "corner", "free_kick", "goal_kick", "throw_in", "kick_off"]
    cross: bool
    through_ball: bool
    outcome: Literal["complete", "incomplete", "out", "offside"]
    tracking: PassTracking | None = None


class PressureEvent(EventBase):
    type: Literal["pressure"] = "pressure"
    counterpress: bool


class DuelEvent(EventBase):
    type: Literal["duel"] = "duel"
    duel_type: Literal["tackle", "aerial"]
    outcome: Literal["won", "lost"]


class InterceptionEvent(EventBase):
    type: Literal["interception"] = "interception"
    outcome: Literal["won", "lost"]


class BallRecoveryEvent(EventBase):
    type: Literal["ball_recovery"] = "ball_recovery"
    recovery_failure: bool


class FoulCommittedEvent(EventBase):
    type: Literal["foul_committed"] = "foul_committed"
    card: Literal["none", "yellow", "red"]
    penalty: bool


class CardEvent(EventBase):
    type: Literal["card"] = "card"
    card: Literal["yellow", "second_yellow", "red"]


class SubstitutionEvent(EventBase):
    type: Literal["substitution"] = "substitution"
    player_off_id: str
    player_on_id: str


class VarReviewStartEvent(EventBase):
    type: Literal["var_review_start"] = "var_review_start"
    review_subject: Literal["goal", "penalty", "red_card"]


class VarReviewEndEvent(EventBase):
    type: Literal["var_review_end"] = "var_review_end"
    outcome: Literal["goal", "no_goal", "penalty", "no_penalty", "red_card", "no_red_card"]


class HalfStartEvent(EventBase):
    type: Literal["half_start"] = "half_start"


class HalfEndEvent(EventBase):
    type: Literal["half_end"] = "half_end"


MatchEvent = Annotated[
    ShotEvent
    | PassEvent
    | PressureEvent
    | DuelEvent
    | InterceptionEvent
    | BallRecoveryEvent
    | FoulCommittedEvent
    | CardEvent
    | SubstitutionEvent
    | VarReviewStartEvent
    | VarReviewEndEvent
    | HalfStartEvent
    | HalfEndEvent,
    Field(discriminator="type"),
]
