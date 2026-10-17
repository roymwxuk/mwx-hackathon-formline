import statistics as st

import pytest

from formline.engine.features import (
    PENALTY_XG,
    body_group_of,
    placement_score,
    shot_features,
    xg_model,
    zone_of,
)
from formline.engine.log import current_events
from formline.generator.season import generate_season
from formline.pitch import goal_distance_m


@pytest.fixture(scope="module")
def season():
    return generate_season(2026)


@pytest.fixture(scope="module")
def players(season):
    return {p.player_id: p for p in season.league.players}


@pytest.fixture(scope="module")
def history_features(season, players):
    out = []
    for gm in season.matches:
        if gm.match.is_live_demo:
            continue
        out += [shot_features(e, players[e.player_id])
                for e in current_events(gm.feed) if e.type == "shot"]
    return out


# ---------- geometry ----------

def test_penalty_spot_is_eleven_metres():
    assert goal_distance_m(100 - 11 / 1.05, 50) == pytest.approx(11.0, abs=0.01)


@pytest.mark.parametrize("x,y,zone", [
    (97, 50, "six_yard"),
    (88, 50, "box_central"),
    (88, 25, "box_wide"),
    (78, 50, "outside_central"),
    (70, 20, "long_range"),
])
def test_zones(x, y, zone):
    assert zone_of(x, y) == zone


def test_body_group_uses_preferred_foot(players):
    right_footed = players["ply_0107"]  # Reyner
    assert body_group_of("right_foot", right_footed) == "strong_foot"
    assert body_group_of("left_foot", right_footed) == "weak_foot"
    assert body_group_of("head", right_footed) == "head"


# ---------- models ----------

def test_xg_behaves_sensibly():
    near = xg_model(8, 45, "strong_foot", False, 0, "open_play")
    far = xg_model(25, 15, "strong_foot", False, 0, "open_play")
    header = xg_model(8, 45, "head", False, 0, "open_play")
    pressured = xg_model(8, 45, "strong_foot", True, 0, "open_play")
    blocked_view = xg_model(8, 45, "strong_foot", False, 2, "open_play")
    assert near > far and near > header and near > pressured and near > blocked_view
    assert xg_model(11, 36, "strong_foot", False, 0, "penalty") == PENALTY_XG


def test_placement_rewards_corners():
    top_corner = placement_score(3.5, 2.3)
    bottom_corner = placement_score(3.5, 0.1)
    central = placement_score(0.0, 1.0)
    assert central == 0.0
    assert top_corner > bottom_corner > central
    assert 0 <= top_corner <= 1


# ---------- on generated data ----------

def test_derived_fields_are_consistent(season, players):
    for gm in season.matches:
        for e in current_events(gm.feed):
            if e.type != "shot":
                continue
            f = shot_features(e, players[e.player_id])
            if e.shot_type != "penalty":
                assert (f.pressure == "pressured") == e.under_pressure
            assert (f.placement is not None) == f.on_target == (f.psxg is not None)
            assert 0 < f.xg < 1


def test_xg_is_calibrated_to_league_conversion(history_features):
    fs = history_features
    goals = [f for f in fs if f.outcome == "goal"]
    assert 0.09 <= st.mean(f.xg for f in fs) <= 0.13  # league conversion ~11%
    assert 0.8 <= sum(f.xg for f in fs) / len(goals) <= 1.25


def test_models_separate_goals_from_misses(history_features):
    def auc(pos, neg):
        return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))

    fs = history_features
    assert auc([f.xg for f in fs if f.outcome == "goal"],
               [f.xg for f in fs if f.outcome != "goal"]) > 0.65
    on_target = [f for f in fs if f.on_target]
    assert auc([f.psxg for f in on_target if f.outcome == "goal"],
               [f.psxg for f in on_target if f.outcome != "goal"]) > 0.65


def test_live_slow_shot_features(season, players):
    live = next(gm for gm in season.matches if gm.match.is_live_demo)
    shot = next(e for e in current_events(live.feed) if e.type == "shot"
                and e.player_id == "ply_0107" and e.match_clock_ms == (40 * 60 + 12) * 1000)
    f = shot_features(shot, players["ply_0107"])
    assert f.zone == "outside_central"
    assert f.pressure == "pressured" and f.body_group == "strong_foot"
    assert f.shot_speed_kmh == 84.1 and f.on_target
