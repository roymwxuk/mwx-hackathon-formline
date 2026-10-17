"""Property-based convergence tests (ADR-007): chaos must not change the final state."""

from functools import cache

from hypothesis import given, settings
from hypothesis import strategies as st

from formline.chaos import ChaosConfig
from formline.convergence import ConvergenceChecker
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.log import current_events
from formline.generator.season import generate_season

rates = st.floats(min_value=0.0, max_value=0.3)


@cache
def checker() -> ConvergenceChecker:
    season = generate_season(2026)
    history = BaselineEngine(season.league.players)
    history.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                      for e in current_events(gm.feed))
    history.fit_priors()
    live = next(gm.feed for gm in season.matches if gm.match.is_live_demo)
    return ConvergenceChecker(live, history)


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(0, 10**9), dup=rates, reorder=rates,
       late=st.floats(0.0, 0.1), corr=st.floats(0.0, 1.0), revert=st.floats(0.0, 1.0),
       delete=st.floats(0.0, 0.05))
def test_baselines_always_equal_a_rebuild_from_the_log(seed, dup, reorder, late, corr, revert,
                                                       delete):
    result = checker().check(ChaosConfig(seed=seed, duplicate_rate=dup, reorder_rate=reorder,
                                         late_rate=late, correction_rate=corr,
                                         revert_rate=revert, delete_rate=delete))
    assert result.baselines_match_log


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10**9), dup=rates, reorder=rates, late=st.floats(0.0, 0.1))
def test_without_new_truth_baselines_equal_the_clean_run(seed, dup, reorder, late):
    result = checker().check(ChaosConfig(seed=seed, duplicate_rate=dup, reorder_rate=reorder,
                                         late_rate=late, correction_rate=0.0, delete_rate=0.0))
    assert result.baselines_match_clean is True


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10**9), dup=rates, reorder=rates)
def test_within_the_window_insights_equal_the_clean_run(seed, dup, reorder):
    result = checker().check(ChaosConfig(seed=seed, duplicate_rate=dup, reorder_rate=reorder,
                                         late_rate=0.0, correction_rate=0.0, delete_rate=0.0))
    assert result.late_observed == 0
    assert result.insights_match_clean is True


def test_heavy_chaos_still_converges():
    heavy = ChaosConfig(seed=42, duplicate_rate=0.5, reorder_rate=0.5, late_rate=0.2,
                        correction_rate=1.0, revert_rate=0.5, delete_rate=0.1)
    result = checker().check(heavy)
    rep = result.report
    assert rep.duplicates > 500 and rep.corrections > 10 and rep.deletes > 50
    assert result.late_observed > 0
    assert result.baselines_match_log
