from formline.schema.tracking import Ball, TrackedPlayer, TrackingFrame
from formline.tracking.anchors import Anchor
from formline.tracking.realism import tracking_checks


def frames(minutes: int, speed_x: float):
    """One outfield player (shirt 9) moving steadily along x, a keeper standing still."""
    out = []
    n = minutes * 60 * 10
    for i in range(n):
        u = (speed_x * i / 10) % 120  # back and forth over 60 units, at speed_x units/s
        x = 20 + (u if u <= 60 else 120 - u)
        out.append(TrackingFrame(period=1, match_clock_ms=i * 100, ball=Ball(x=50, y=50),
                                 home=[TrackedPlayer(shirt=9, x=x, y=50), TrackedPlayer(shirt=1, x=5, y=50)],
                                 away=[]))
    return out


def test_distance_and_speed_per_90():
    # 1 unit/s along x = 1.05 m/s -> 5.67 km per 90
    checks, extra = tracking_checks(frames(50, 1.0))
    by = {c.metric: c for c in checks}
    km = by["Distance per 90, outfield (km)"].value
    assert 5.0 < km < 6.0
    assert by["Peak speed, outfield median (m/s)"].value > 1.0
    assert by["Distance per 90, goalkeepers (km)"].value == 0.0
    assert extra["players"] == 2


def test_event_spot_accuracy():
    fr = frames(46, 0.0)
    on = Anchor(1, 1000, True, 9, 20.0, 50.0, "passer", "e1")
    off = Anchor(1, 2000, True, 9, 30.0, 50.0, "receiver", "e2")
    checks, _ = tracking_checks(fr, [on, off])
    spot = next(c for c in checks if c.metric.startswith("Players on their event spots"))
    assert spot.value == 50.0 and not spot.ok
