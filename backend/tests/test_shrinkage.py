import random

import pytest

from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied, ingest_all
from formline.engine.log import current_events
from formline.engine.shrinkage import (
    MIN_PLAYERS,
    Prior,
    _moments,
    estimated_percentile,
    fit_priors,
    shrink,
)
from formline.generator.season import generate_season


def prior(sigma2=81.0, tau2=27.0, mean=84.0) -> Prior:
    return Prior("shot_speed_kmh", "FWD", "strong_foot", sigma2, tau2, mean, 10, "fitted")


# ---------- the estimator ----------

def test_method_of_moments_recovers_known_spreads():
    rng = random.Random(7)
    sigma, tau, mu = 8.0, 5.0, 84.0
    samples = []
    for _ in range(60):
        true_mean = rng.gauss(mu, tau)
        samples.append([rng.gauss(true_mean, sigma) for _ in range(25)])
    sigma2, tau2, grand = _moments(samples)
    assert sigma2 ** 0.5 == pytest.approx(sigma, rel=0.1)
    assert tau2 ** 0.5 == pytest.approx(tau, rel=0.25)
    assert grand == pytest.approx(mu, abs=2.0)


def test_too_few_players_returns_none():
    assert _moments([[80.0, 82.0, 85.0]] * (MIN_PLAYERS - 1)) is None


def test_fallback_pools_same_body_part_but_keeps_own_mean():
    rng = random.Random(3)
    fwd_heads = [[rng.gauss(52, 5) for _ in range(8)] for _ in range(6)]
    mid_heads = [[rng.gauss(48, 5) for _ in range(4)]]  # one player only
    priors = fit_priors({
        ("shot_speed_kmh", "FWD", "head"): fwd_heads,
        ("shot_speed_kmh", "MID", "head"): mid_heads,
    })
    mid = priors[("shot_speed_kmh", "MID", "head")]
    assert mid.source == "pooled"
    assert mid.mean == pytest.approx(sum(mid_heads[0]) / 4)
    assert mid.sigma == pytest.approx(5.0, rel=0.3)  # spread borrowed from all headers


# ---------- shrinking ----------

def test_weight_grows_with_sample_size():
    p = prior()  # k = 3
    weights = [shrink(n, 90.0, 84.0, p).weight for n in (0, 1, 5, 20, 200)]
    assert weights == sorted(weights)
    assert weights[0] == 0 and weights[-1] > 0.98
    assert shrink(5, 90.0, 84.0, p).weight == pytest.approx(5 / 8)


def test_shrunk_mean_lies_between_raw_and_prior():
    s = shrink(5, 90.0, 84.0, prior())
    assert 84.0 < s.mean < 90.0
    assert shrink(0, None, 84.0, prior()).mean == 84.0


def test_estimated_percentile_is_centred_and_bounded():
    s = shrink(10, 88.0, 84.0, prior())
    assert estimated_percentile(s.mean, s, 10) == pytest.approx(50.0)
    assert estimated_percentile(s.mean + 100, s, 10) == 99.0
    assert estimated_percentile(s.mean - 100, s, 10) == 1.0


# ---------- in the engine ----------

@pytest.fixture(scope="module")
def season():
    return generate_season(2026)


@pytest.fixture(scope="module")
def live_comparisons(season):
    eng = BaselineEngine(season.league.players)
    eng.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                  for e in current_events(gm.feed))
    priors = dict(eng.fit_priors())
    live = next(gm.feed for gm in season.matches if gm.match.is_live_demo)
    comparisons = eng.apply_all(ingest_all(live))
    return eng, priors, comparisons


def test_priors_stay_frozen_during_live_updates(live_comparisons):
    eng, priors_before, _ = live_comparisons
    assert eng.priors == priors_before


def test_small_samples_are_pulled_toward_the_group(live_comparisons):
    _, _, comparisons = live_comparisons
    checked = 0
    for c in comparisons:
        for m in c.metrics.values():
            assert min(m.mean, m.prior_mean) - 1e-9 <= m.shrunk_mean <= max(m.mean, m.prior_mean) + 1e-9
            assert m.weight == pytest.approx(m.n / (m.n + m.k))
            checked += 1
    assert checked > 50


def test_shrinkage_tempers_a_thin_extreme(live_comparisons):
    """Okafor's pressured header: last of 5 raw, but not an extreme after shrinkage."""
    _, _, comparisons = live_comparisons
    header = next(c.metrics["shot_speed_kmh"] for c in comparisons
                  if c.features.player_id == "ply_0210" and c.features.body_group == "head"
                  and c.metrics.get("shot_speed_kmh") and c.metrics["shot_speed_kmh"].n <= 6
                  and c.metrics["shot_speed_kmh"].percentile in (0.0, 100.0))
    assert header.percentile in (0.0, 100.0)
    assert 10 < header.est_percentile < 90
