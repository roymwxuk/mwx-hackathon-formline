"""Overlay output contract (DATA_SCHEMA.md §6.5), mirroring frontend/src/lib/types.ts.

The backend fills one template from a fixed catalog; the viewer only renders it.
Every overlay cites the events it was derived from (`source_event_ids`), which is
how a feed correction finds and retracts dependent overlays.

Op semantics:
- show     display a new overlay
- correct  replace `supersedes_overlay_id` because its source data was corrected
- retract  withdraw `supersedes_overlay_id`; slots carry no content
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TemplateId = Literal["shot_speed_card", "placement_card", "finish_quality_card",
                     "correction_banner"]
OverlayMetric = Literal["shot_speed", "finishing"]
AudienceMode = Literal["casual", "analyst"]
Lang = Literal["en", "ja"]


class Bar(BaseModel):
    """One bar of a casual card: this value vs the player's own norm."""

    label: str
    value: float
    display: str
    highlight: bool


class Row(BaseModel):
    """One label/value row of an analyst card."""

    label: str
    value: str


class OverlaySlots(BaseModel):
    tag: str
    headline: str
    stat: str | None = None
    sub: str | None = None
    bars: list[Bar] | None = None
    rows: list[Row] | None = None


class Overlay(BaseModel):
    overlay_id: str
    op: Literal["show", "correct", "retract"]
    supersedes_overlay_id: str | None
    match_clock_ms: int = Field(ge=0)
    ttl_ms: int = Field(ge=0)
    template_id: TemplateId
    priority: int = Field(ge=1, description="1 = most important")
    audience_mode: AudienceMode
    lang: Lang
    slots: OverlaySlots
    insight_id: str
    player_id: str | None
    metric: OverlayMetric | None
    source_event_ids: list[str] = Field(min_length=1)
    verified: bool

    @model_validator(mode="after")
    def _op_rules(self) -> "Overlay":
        if self.op in ("correct", "retract") and not self.supersedes_overlay_id:
            raise ValueError(f"{self.op} must name the overlay it supersedes")
        if self.op == "show" and self.supersedes_overlay_id:
            raise ValueError("show must not supersede another overlay")
        return self


def overlay_json(overlay: Overlay) -> dict:
    """JSON for the viewer: top-level nulls stay (the TS type expects the keys), but
    optional slots that are empty are omitted."""
    data = overlay.model_dump(mode="json")
    data["slots"] = {k: v for k, v in data["slots"].items() if v is not None}
    return data


def overlay_message(overlay: Overlay) -> dict:
    """The viewer's StreamMessage for an overlay (SSE `data:` payload)."""
    return {"kind": "overlay", "overlay": overlay_json(overlay)}
