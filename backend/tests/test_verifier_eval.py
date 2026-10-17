"""The verifier's measured catch rate must not regress."""

import pytest

from formline.agents.verifier_eval import build_world, render, run


@pytest.fixture(scope="module")
def result():
    return run(build_world(2026))


def test_no_false_positives_on_valid_cards(result):
    assert result.base_cases == 88
    assert result.false_positives == 0


def test_overall_catch_rate(result):
    assert result.applied > 1000
    assert result.caught / result.applied >= 0.98


@pytest.mark.parametrize("family", ["Entities", "Estimates", "Certainty", "Structure",
                                    "Language"])
def test_non_numeric_families_are_fully_caught(result, family):
    rs = [r for r in result.results.values() if r.family == family]
    assert sum(r.applied for r in rs) > 0
    assert sum(r.caught for r in rs) == sum(r.applied for r in rs)


def test_number_errors_are_mostly_caught(result):
    rs = [r for r in result.results.values() if r.family == "Numbers"]
    assert sum(r.caught for r in rs) / sum(r.applied for r in rs) >= 0.97


def test_runs_are_deterministic(result):
    again = run(build_world(2026))
    assert {k: (r.applied, r.caught) for k, r in again.results.items()} == \
           {k: (r.applied, r.caught) for k, r in result.results.items()}


def test_report_renders(result):
    text = render(result)
    assert "Overall:" in text and "Known limits" in text
