import pytest
from pydantic import ValidationError

from formline.schema.tracking import (
    FRAME_MS,
    Ball,
    TrackedPlayer,
    TrackingFrame,
    read_tracking,
    tracking_path,
    write_tracking,
)


def frame(t: int, period: int = 1) -> TrackingFrame:
    return TrackingFrame(
        period=period, match_clock_ms=t, ball=Ball(x=50.04, y=49.96, z=0.0),
        home=[TrackedPlayer(shirt=n, x=10 + n, y=20 + n) for n in range(1, 12)],
        away=[TrackedPlayer(shirt=n, x=90 - n, y=80 - n) for n in range(1, 12)])


def test_row_is_compact_and_rounded():
    row = frame(12_300).to_row()
    assert set(row) == {"p", "t", "b", "h", "a"}
    assert row["b"] == [50.0, 50.0, 0.0]
    assert row["h"][0] == [1, 11.0, 21.0] and len(row["a"]) == 11


def test_round_trip_through_gzip(tmp_path):
    frames = [frame(i * FRAME_MS) for i in range(50)] + [frame(2_700_000, period=2)]
    path = tracking_path(tmp_path, "mtc_x")
    assert write_tracking(path, frames) == 51
    back = list(read_tracking(path))
    assert [f.to_row() for f in back] == [f.to_row() for f in frames]
    assert back[-1].period == 2


def test_rejects_impossible_values():
    with pytest.raises(ValidationError):
        Ball(x=50, y=50, z=-1)
    with pytest.raises(ValidationError):
        TrackedPlayer(shirt=0, x=1, y=1)
