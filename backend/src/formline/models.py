"""Shared event and insight schemas used across every pipeline stage."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class EventType(StrEnum):
    PASS = "pass"
    SHOT = "shot"
    TACKLE = "tackle"
    POSSESSION_CHANGE = "possession_change"
    PRESSURE = "pressure"
    GOAL = "goal"
    KICKOFF = "kickoff"
    FULL_TIME = "full_time"


class MatchEvent(BaseModel):
    """A single synthetic match event (stage a: ingest)."""

    id: int
    match_id: str
    minute: int
    second: int
    type: EventType
    team: str
    player: str | None = None
    x: float = Field(ge=0, le=100, description="Pitch x, 0-100 (attacking left to right)")
    y: float = Field(ge=0, le=100)
    end_x: float | None = None
    end_y: float | None = None
    outcome: Literal["success", "fail"] | None = None
    speed_kmh: float | None = None


class Insight(BaseModel):
    """A timed, machine-readable insight that can render as an overlay (stage d)."""

    match_id: str
    minute: int
    kind: Literal["stat", "moment", "narrative", "recap"]
    headline: str
    explanation: str
    importance: float = Field(ge=0, le=1)
    related_event_ids: list[int] = []
    display_seconds: int = 8


class FanProfile(BaseModel):
    """Personalization inputs (stage e)."""

    mode: Literal["casual", "analyst", "player_focus"] = "casual"
    language: str = "en"
    favorite_team: str | None = None
    favorite_player: str | None = None
