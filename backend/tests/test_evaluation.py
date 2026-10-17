"""Shrinkage must beat raw averages against the generator's hidden truth."""

import pytest

from formline.evaluation import MIN_TRUTH_N, evaluate, render


@pytest.fixture(scope="module")
def accuracy():
    return evaluate(seed=2026, truth_matches=180)


def test_enough_players_are_evaluated(accuracy):
    assert len(accuracy.players) >= 25
    assert all(p.truth_n >= MIN_TRUTH_N and p.n >= 1 for p in accuracy.players)


def test_shrinkage_beats_raw_and_group_averages(accuracy):
    raw, group, shrunk = (accuracy.rmse(a) for a in ("raw", "group_mean", "shrunk"))
    assert shrunk < raw
    assert shrunk < group


def test_shrinkage_helps_most_for_small_samples(accuracy):
    small_raw, small_shrunk = accuracy.rmse("raw", 1, 9), accuracy.rmse("shrunk", 1, 9)
    assert small_shrunk < small_raw
    assert (1 - small_shrunk / small_raw) > (1 - accuracy.rmse("shrunk", 20) /
                                             accuracy.rmse("raw", 20))


def test_estimates_sit_between_raw_and_group(accuracy):
    for p in accuracy.players:
        assert 0 < p.weight < 1
        assert min(p.raw, p.group_mean) - 1e-9 <= p.shrunk <= max(p.raw, p.group_mean) + 1e-9


def test_report_renders(accuracy):
    text = render(accuracy)
    assert "Error vs truth" in text and "Fitted k" in text
