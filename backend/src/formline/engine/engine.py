"""Baseline engine: consumes ingestion changes and keeps personal baselines current.

For every shot it first compares the shot with the shooter's baselines (so a shot
is never compared with itself), then adds it. A revision removes the old version's
contribution and re-applies the new one, so corrections never need a recompute.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from formline.engine.baselines import METRICS, BaselineStore, metric_values
from formline.engine.features import ShotFeatures, shot_features
from formline.engine.ingest import Applied, Change, Revised
from formline.engine.shrinkage import (
    DEFAULT_K,
    Prior,
    estimated_percentile,
    fit_priors,
    shrink,
)
from formline.schema.reference import Player


@dataclass(frozen=True)
class MetricComparison:
    """One metric of one shot vs the shooter's own comparable shots (frozen numbers)."""

    metric: str
    value: float
    level: str
    level_label: str
    thin: bool
    n: int
    mean: float | None
    sd: float | None
    percentile: float | None  # raw rank among his comparable shots, 0–100
    shrunk_mean: float  # his baseline after shrinkage toward the group (model estimate)
    weight: float  # share of shrunk_mean that comes from his own shots
    prior_mean: float  # group mean at the same level, excluding him
    k: float  # shrinkage strength: shots' worth of weight given to the group
    est_percentile: float  # model-estimated percentile vs his shrunk baseline, 1–99
    group_n: int
    group_mean: float | None
    group_sd: float | None
    season_n: int  # his previous values with the same body part (season-record sample)
    season_best: bool  # beats every previous value with the same body part
    season_worst: bool


@dataclass(frozen=True)
class ShotComparison:
    features: ShotFeatures
    metrics: dict[str, MetricComparison]
    revision: bool = False  # True when produced by a correction


class BaselineEngine:
    def __init__(self, players: Iterable[Player]):
        self.players = {p.player_id: p for p in players}
        self.store = BaselineStore({p.player_id: p.position_group for p in self.players.values()})
        self.features: dict[str, ShotFeatures] = {}  # event_id -> features currently applied
        self.priors: dict[tuple, Prior] = {}

    def fit_priors(self) -> dict[tuple, Prior]:
        """Estimate shrinkage priors from everything applied so far, then freeze them.

        Call once after the historical bootstrap; live updates keep the same priors.
        """
        self.priors = fit_priors(self.store.per_player_samples())
        return self.priors

    def _prior(self, metric: str, f: ShotFeatures, group_bucket) -> Prior:
        group = self.players[f.player_id].position_group
        prior = self.priors.get((metric, group, f.body_group))
        if prior is not None:
            return prior
        var = (group_bucket.sd or 1.0) ** 2 if group_bucket else 1.0
        mean = group_bucket.mean if group_bucket and group_bucket.n else 0.0
        return Prior(metric, group, f.body_group, var, var / DEFAULT_K, mean, 0, "default")

    def season_norm(self, player_id: str, metric: str = "shot_speed_kmh",
                    body_group: str = "strong_foot") -> float | None:
        """His shrunk season baseline for one metric and body part, anywhere on the pitch."""
        player = self.players.get(player_id)
        if player is None or player.position_group == "GK":
            return None
        prior = self.priors.get((metric, player.position_group, body_group))
        bucket = self.store.bucket(player_id, metric, "body", (body_group,))
        if prior is None:
            return bucket.mean if bucket else None
        n = bucket.n if bucket else 0
        return shrink(n, bucket.mean if bucket else None, prior.mean, prior).mean

    # ---------- change handling ----------

    def apply(self, change: Change) -> list[ShotComparison]:
        if isinstance(change, Applied):
            return self._add(change.event, revision=False)
        if isinstance(change, Revised):
            self._remove(change.before)
            return self._add(change.after, revision=True) if change.after is not None else []
        raise TypeError(change)

    def apply_all(self, changes: Iterable[Change]) -> list[ShotComparison]:
        return [c for change in changes for c in self.apply(change)]

    def _add(self, event, revision: bool) -> list[ShotComparison]:
        if event.type != "shot":
            return []
        f = shot_features(event, self.players.get(event.player_id))
        comparison = self.compare(f, revision)
        self.store.add(f)
        self.features[f.event_id] = f
        return [comparison]

    def _remove(self, event) -> None:
        f = self.features.pop(event.event_id, None)
        if f is not None:
            self.store.remove(f)

    # ---------- comparison ----------

    def compare(self, f: ShotFeatures, revision: bool = False) -> ShotComparison:
        out: dict[str, MetricComparison] = {}
        for metric, value in metric_values(f).items():
            view = self.store.lookup(f, metric)
            if view is None:
                continue
            p, g = view.player, view.group
            widest = self.store.lookup(f, metric, min_n=10**9)  # player's body-level bucket
            ext = widest.player.extremes() if widest and widest.player else None
            scaled = round(value * METRICS[metric])
            prior = self._prior(metric, f, g)
            # Group mean at the same level, leaving this player out.
            if g and g.n > p.n:
                prior_mean = (g.total - p.total) / (g.n - p.n) / METRICS[metric]
            else:
                prior_mean = prior.mean
            s = shrink(p.n, p.mean, prior_mean, prior)
            out[metric] = MetricComparison(
                metric=metric,
                value=value,
                level=view.level,
                level_label=view.label,
                thin=view.thin,
                n=p.n,
                mean=p.mean,
                sd=p.sd,
                percentile=p.percentile_of(value),
                shrunk_mean=s.mean,
                weight=s.weight,
                prior_mean=s.prior_mean,
                k=s.k,
                est_percentile=estimated_percentile(value, s, p.n),
                group_n=g.n if g else 0,
                group_mean=g.mean if g else None,
                group_sd=g.sd if g else None,
                season_n=widest.player.n if widest and widest.player else 0,
                season_best=ext is not None and scaled > round(ext[1] * METRICS[metric]),
                season_worst=ext is not None and scaled < round(ext[0] * METRICS[metric]),
            )
        return ShotComparison(f, out, revision)
