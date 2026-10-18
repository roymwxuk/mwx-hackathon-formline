"""Reference data (DATA_SCHEMA.md §2). Clubs, players and venues are fictional."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

PositionGroup = Literal["GK", "DEF", "MID", "FWD"]

POSITION_GROUPS: dict[str, PositionGroup] = {
    "GK": "GK",
    "CB": "DEF",
    "LB": "DEF",
    "RB": "DEF",
    "DM": "MID",
    "CM": "MID",
    "AM": "MID",
    "LW": "FWD",
    "RW": "FWD",
    "ST": "FWD",
}


class ClubColors(BaseModel):
    primary: str
    secondary: str


class Club(BaseModel):
    club_id: str
    name: str
    short_name: str
    colors: ClubColors


class Player(BaseModel):
    player_id: str
    display_name: str
    display_name_ja: str
    club_id: str
    shirt_number: int
    position: str
    position_group: PositionGroup
    preferred_foot: Literal["left", "right"]


class MatchConditions(BaseModel):
    """Match-day metadata, as in professional match feeds (synthetic; the referee is fictional)."""

    weather: Literal["clear", "partly cloudy", "overcast", "light rain", "rain", "windy"]
    temperature_c: int
    attendance: int
    capacity: int
    referee: str
    referee_ja: str


class Match(BaseModel):
    match_id: str
    season: str
    matchday: int
    kickoff_at: datetime
    home_club_id: str
    away_club_id: str
    venue: str
    is_live_demo: bool
    conditions: MatchConditions | None = None
