import pytest
from hypothesis import given
from hypothesis import strategies as st

from formline.tracking.shape import (
    ROLE_LINE,
    assign_roles,
    depth_m,
    team_shape,
    to_shared,
)

XI = [(1, "GK"), (2, "RB"), (4, "CB"), (5, "CB"), (3, "LB"), (6, "DM"), (8, "CM"),
      (10, "AM"), (7, "RW"), (9, "ST"), (11, "LW")]
SLOTS = assign_roles(XI)
balls = st.tuples(st.floats(0, 100), st.floats(0, 100))
possession = st.sampled_from([True, False, None])


def line_mean(shape, line):
    xs = [shape[s.shirt][0] for s in SLOTS if ROLE_LINE[s.role] == line]
    return sum(xs) / len(xs)


def test_roles_cover_the_4_3_3():
    roles = {s.shirt: s.role for s in SLOTS}
    assert roles[4] == "RCB" and roles[5] == "LCB"
    assert roles[8] == "RCM" and roles[10] == "LCM"
    assert len(set(roles.values())) == 11


def test_unknown_position_is_rejected():
    with pytest.raises(ValueError):
        assign_roles([(1, "SWEEPER")])


@given(balls, possession)
def test_everyone_stays_on_the_pitch_in_line_order(ball, has_ball):
    shape = team_shape(SLOTS, ball, has_ball)
    assert len(shape) == 11
    assert all(0 < x < 100 and 0 < y < 100 for x, y in shape.values())
    lines = [line_mean(shape, n) for n in range(4)]
    assert lines == sorted(lines)  # keeper, defence, midfield, attack
    assert shape[2][1] < shape[3][1]  # right back on the right (y < 50 side)


@given(balls)
def test_compact_without_the_ball_and_stretched_with_it(ball):
    with_ball = depth_m(team_shape(SLOTS, ball, True), SLOTS)
    without = depth_m(team_shape(SLOTS, ball, False), SLOTS)
    assert without < with_ball
    assert 20 <= without <= 40 and with_ball <= 55


def test_block_follows_the_ball_up_the_pitch_and_across():
    low = team_shape(SLOTS, (20, 50), True)
    high = team_shape(SLOTS, (80, 50), True)
    assert line_mean(high, 1) > line_mean(low, 1) + 20
    right = team_shape(SLOTS, (50, 10), False)
    left = team_shape(SLOTS, (50, 90), False)
    assert sum(y for _, y in right.values()) < sum(y for _, y in left.values())


def test_keeper_stays_near_goal_and_shades_toward_the_ball():
    near = team_shape(SLOTS, (10, 20), False)[1]
    far = team_shape(SLOTS, (90, 80), True)[1]
    assert near[0] <= 8 and near[1] < 50
    assert far[0] <= 16 and far[1] > 50


def test_kickoff_keeps_everyone_in_his_own_half():
    shape = team_shape(SLOTS, (50, 50), True, kickoff=True)
    assert all(x < 50 for x, _ in shape.values())


def test_shared_frame_flips_the_away_side():
    assert to_shared((20, 30), home=True) == (20, 30)
    assert to_shared((20, 30), home=False) == (80, 70)
    assert to_shared(to_shared((12.5, 40), home=False), home=False) == (12.5, 40)


def test_a_half_finished_transition_sits_between_the_two_shapes():
    ball = (60, 50)
    attack, defend = team_shape(SLOTS, ball, True), team_shape(SLOTS, ball, False)
    mid = team_shape(SLOTS, ball, 0.5)
    for shirt in (2, 9, 11):  # a full back and two forwards move most between shapes
        lo, hi = sorted((attack[shirt][0], defend[shirt][0]))
        assert lo < mid[shirt][0] < hi
    assert team_shape(SLOTS, ball, 1.0) == attack and team_shape(SLOTS, ball, 0.0) == defend
