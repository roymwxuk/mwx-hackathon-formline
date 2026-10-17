"""Tracking frames (DATA_SCHEMA.md §5.4): every player and the ball, 10 times a second.

Unlike events, tracking uses one shared frame for the whole match: 0–100 on both axes with
the home team attacking toward x = 100 in both periods (what the viewer draws). Meters:
x_m = x * 1.05, y_m = y * 0.68. The ball also has a height `z` in meters.

On disk and on the wire a frame is one compact row, so a 90-minute match at 10 Hz stays
small: `{"p": 1, "t": 12300, "b": [50.0, 50.0, 0.0], "h": [[1, 5.2, 50.0], ...], "a": [...]}`
where `h`/`a` list `[shirt number, x, y]` for each home/away player on the pitch.
"""

import gzip
import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import BaseModel, Field

FRAME_HZ = 10
FRAME_MS = 1000 // FRAME_HZ


class TrackedPlayer(BaseModel):
    shirt: int = Field(ge=1, le=99)
    x: float
    y: float


class Ball(BaseModel):
    x: float
    y: float
    z: float = Field(default=0.0, ge=0.0, description="height above the pitch, meters")


class TrackingFrame(BaseModel):
    period: int = Field(ge=1, le=2)
    match_clock_ms: int = Field(ge=0)
    ball: Ball
    home: list[TrackedPlayer]
    away: list[TrackedPlayer]

    def to_row(self) -> dict:
        def players(ps: list[TrackedPlayer]) -> list[list]:
            return [[p.shirt, round(p.x, 1), round(p.y, 1)] for p in ps]

        b = self.ball
        return {"p": self.period, "t": self.match_clock_ms,
                "b": [round(b.x, 1), round(b.y, 1), round(b.z, 1)],
                "h": players(self.home), "a": players(self.away)}

    @classmethod
    def from_row(cls, row: dict) -> "TrackingFrame":
        def players(rows: list[list]) -> list[TrackedPlayer]:
            return [TrackedPlayer(shirt=n, x=x, y=y) for n, x, y in rows]

        x, y, z = row["b"]
        return cls(period=row["p"], match_clock_ms=row["t"], ball=Ball(x=x, y=y, z=z),
                   home=players(row["h"]), away=players(row["a"]))


def tracking_path(data_dir: Path, match_id: str) -> Path:
    return data_dir / "tracking" / f"{match_id}.jsonl.gz"


def write_tracking(path: Path, frames: Iterable[TrackingFrame]) -> int:
    """Write frames as gzipped JSONL; returns how many were written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for frame in frames:
            f.write(json.dumps(frame.to_row(), separators=(",", ":")) + "\n")
            n += 1
    return n


def read_tracking(path: Path) -> Iterator[TrackingFrame]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield TrackingFrame.from_row(json.loads(line))
