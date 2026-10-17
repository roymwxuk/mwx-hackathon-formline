from itertools import pairwise

import pytest

from formline.engine.log import current_events
from formline.generator.season import generate_season
from formline.pitch import to_m
from formline.schema.tracking import FRAME_MS
from formline.tracking.anchors import event_anchors
from formline.tracking.motion import MAX_SPEED, build_frames

LIMIT_MS = 6 * 60_000  # the first six minutes of each half keep the test quick


@pytest.fixture(scope="module")
def match():
    season = generate_season(2026)
    gm = next(g for g in season.matches if g.match.is_live_demo)
    players = {p.player_id: p for p in season.league.players}
    events = current_events(gm.feed)
    args = (events, gm.match.home_club_id, players, season.league.starters)
    return args, build_frames(*args, limit_ms=LIMIT_MS)


def test_frames_cover_both_halves_at_10_hz_with_22_players(match):
    _, frames = match
    for period in (1, 2):
        ts = [f.match_clock_ms for f in frames if f.period == period]
        assert ts and all(b - a == FRAME_MS for a, b in pairwise(ts))
        assert ts[-1] - ts[0] == LIMIT_MS
    assert all(len(f.home) == 11 and len(f.away) == 11 for f in frames)
    assert all(0 <= p.x <= 100 and 0 <= p.y <= 100 for f in frames for p in f.home + f.away)


def test_nobody_runs_faster_than_a_sprint(match):
    _, frames = match
    for a, b in pairwise(frames):
        if a.period != b.period:
            continue
        for side_a, side_b in ((a.home, b.home), (a.away, b.away)):
            nxt = {p.shirt: p for p in side_b}
            for p in side_a:
                q = nxt[p.shirt]
                assert to_m(q.x - p.x, q.y - p.y) / (FRAME_MS / 1000) <= MAX_SPEED + 1e-6


def test_players_pass_through_their_event_anchors(match):
    args, frames = match
    by_time = {(f.period, f.match_clock_ms): f for f in frames}
    errors = []
    for a in event_anchors(*args):
        f = by_time.get((a.period, round(a.t_ms / FRAME_MS) * FRAME_MS))
        if f is None:
            continue  # outside the tested slice
        p = next(p for p in (f.home if a.home else f.away) if p.shirt == a.shirt)
        errors.append(to_m(p.x - a.x, p.y - a.y))
    assert len(errors) > 200
    assert sum(e <= 0.5 for e in errors) / len(errors) >= 0.98


def test_ball_starts_on_the_centre_spot_and_flies_over_lofted_passes(match):
    _, frames = match
    first = frames[0]
    assert (first.ball.x, first.ball.y) == (50, 50)
    assert max(f.ball.z for f in frames) > 2.0  # high balls leave the ground
    assert all(f.ball.z >= 0 for f in frames)


def test_kick_off_keeps_each_team_in_its_own_half(match):
    _, frames = match
    first = frames[0]
    assert all(p.x <= 50 for p in first.home)  # home attacks toward x = 100
    assert all(p.x >= 50 for p in first.away)


def test_same_seed_same_tracking(match):
    args, _ = match
    one = build_frames(*args, limit_ms=30_000)
    two = build_frames(*args, limit_ms=30_000)
    assert [f.to_row() for f in one] == [f.to_row() for f in two]
    other = build_frames(*args, limit_ms=30_000, seed=7)
    assert [f.to_row() for f in other] != [f.to_row() for f in one]  # drift is seeded
