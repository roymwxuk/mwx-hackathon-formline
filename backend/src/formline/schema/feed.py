"""Feed envelope (DATA_SCHEMA.md §3): how events arrive on a live provider feed."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator

from formline.schema.events import MatchEvent


class FeedMessage(BaseModel):
    """`update` carries the full payload and replaces the previous version."""

    message_id: str
    op: Literal["create", "update", "delete"]
    event_id: str
    version: int
    emitted_at: datetime
    sequence: int
    event: MatchEvent | None

    @model_validator(mode="after")
    def _payload_matches_op(self) -> "FeedMessage":
        if (self.op == "delete") != (self.event is None):
            raise ValueError("delete carries no event; create/update must carry one")
        if self.event is not None and self.event.event_id != self.event_id:
            raise ValueError("envelope event_id must match the payload")
        return self
