"""Empirical Bayes shrinkage: never show a confident baseline from a handful of shots.

Model (normal–normal, per metric × position group × body part):
    a player's true mean   μ_i ~ N(μ_group, τ²)      τ² = spread between players
    each of his shots      x_ij ~ N(μ_i, σ²)          σ² = spread between shots

Posterior mean of μ_i after n shots with average x̄:
    shrunk = (n·x̄ + k·μ_group) / (n + k),   k = σ² / τ²
so the weight on his own shots is w = n / (n + k). With n = 5 and k = 10 he gets a
third of the say; with n = 40, 80%.

σ² and τ² are estimated from the history by the method of moments, so k is learned
from the data rather than hand-picked. They are fitted once (after the historical
bootstrap) and then frozen, so live updates and corrections stay exact.

A shot's percentile is a model estimate: where it falls in the predictive
distribution N(shrunk, σ² + σ²/(n+k)).
"""

import statistics as st
from dataclasses import dataclass
from math import erf, sqrt

DEFAULT_K = 10.0
MIN_SHOTS_PER_PLAYER = 3  # players with fewer shots don't inform the estimate
MIN_PLAYERS = 4
MAX_K = 50.0  # floor on τ² so a near-zero between-player spread can't erase players


@dataclass(frozen=True)
class Prior:
    metric: str
    group: str
    body_group: str
    sigma2: float  # within-player (shot-to-shot) variance
    tau2: float  # between-player variance of true means
    mean: float  # group mean
    n_players: int
    source: str  # "fitted", "pooled" (all body parts) or "default"

    @property
    def k(self) -> float:
        return min(MAX_K, self.sigma2 / self.tau2) if self.tau2 > 0 else MAX_K

    @property
    def sigma(self) -> float:
        return sqrt(self.sigma2)


def _moments(samples: list[list[float]]) -> tuple[float, float, float] | None:
    """(σ², τ², grand mean) from per-player samples, or None if too little data."""
    usable = [s for s in samples if len(s) >= MIN_SHOTS_PER_PLAYER]
    if len(usable) < MIN_PLAYERS:
        return None
    dof = sum(len(s) - 1 for s in usable)
    sigma2 = sum((len(s) - 1) * st.variance(s) for s in usable) / dof
    means = [st.mean(s) for s in usable]
    between = st.variance(means)
    noise = st.mean(sigma2 / len(s) for s in usable)
    tau2 = max(between - noise, sigma2 / MAX_K)
    grand = st.mean(v for s in usable for v in s)
    return sigma2, tau2, grand


def fit_priors(samples: dict[tuple[str, str, str], list[list[float]]]) -> dict[tuple, Prior]:
    """samples: (metric, group, body_group) -> one list of values per player.

    Fallback when a group has too few players: the same body part across all
    position groups ("pooled"), then a weak default. The prior mean always comes
    from the key's own values when there are any, so headers never inherit a
    foot-shot average.
    """
    by_body: dict[tuple[str, str], list[list[float]]] = {}
    for (metric, _group, body), per_player in samples.items():
        by_body.setdefault((metric, body), []).extend(per_player)
    priors: dict[tuple, Prior] = {}
    for (metric, group, body), per_player in samples.items():
        own = [v for s in per_player for v in s]
        m = _moments(per_player)
        source = "fitted"
        if m is None:
            m, source = _moments(by_body[(metric, body)]), "pooled"
        if m is None:
            var = st.variance(own) if len(own) > 1 else 1.0
            m, source = (var, var / DEFAULT_K, 0.0), "default"
        sigma2, tau2, mean = m
        if source != "fitted" and own:
            mean = st.mean(own)
        n_players = sum(len(s) >= MIN_SHOTS_PER_PLAYER for s in per_player)
        priors[(metric, group, body)] = Prior(metric, group, body, sigma2, tau2, mean,
                                              n_players, source)
    return priors


@dataclass(frozen=True)
class Shrunk:
    mean: float
    weight: float  # share of the estimate that comes from his own shots
    prior_mean: float
    k: float
    sigma: float


def shrink(n: int, raw_mean: float | None, prior_mean: float, prior: Prior) -> Shrunk:
    k = prior.k
    w = n / (n + k) if n else 0.0
    mean = prior_mean if not n or raw_mean is None else w * raw_mean + (1 - w) * prior_mean
    return Shrunk(mean=mean, weight=w, prior_mean=prior_mean, k=k, sigma=prior.sigma)


def estimated_percentile(value: float, s: Shrunk, n: int) -> float:
    """Model estimate of where `value` falls among his comparable shots, 1–99."""
    spread = sqrt(s.sigma ** 2 * (1 + 1 / (n + s.k)))
    z = (value - s.mean) / spread if spread > 0 else 0.0
    pct = 50 * (1 + erf(z / sqrt(2)))
    return max(1.0, min(99.0, pct))
