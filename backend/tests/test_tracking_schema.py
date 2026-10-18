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


def test_frame_messages_blend_to_the_exact_time(tmp_path):
    import json

    from formline.tracking.frames import load_frames

    def at(t, x):
        return TrackingFrame(period=1, match_clock_ms=t, ball=Ball(x=x, y=50, z=0),
                             home=[TrackedPlayer(shirt=9, x=x, y=40)],
                             away=[TrackedPlayer(shirt=4, x=100 - x, y=60)])

    path = tracking_path(tmp_path, "m")
    write_tracking(path, [at(0, 10.0), at(100, 20.0), at(200, 30.0)])
    index = load_frames(path)
    exact = json.loads(index.message(1, 100))
    assert exact["t"] == 100 and exact["h"] == [[9, 20.0, 40.0]]
    mid = json.loads(index.message(1, 125))
    assert mid["t"] == 125 and mid["h"] == [[9, 22.5, 40.0]] and mid["a"] == [[4, 77.5, 60.0]]
    assert mid["b"] == [22.5, 50.0, 0.0]
    assert index.message(1, 5_000) is None and index.message(2, 0) is None
