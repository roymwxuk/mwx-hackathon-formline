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
    percentile: float | None  # where this shot ranks among his comparable shots, 0–100
    group_n: int
    group_mean: float | None
    group_sd: float | None
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
                group_n=g.n if g else 0,
                group_mean=g.mean if g else None,
                group_sd=g.sd if g else None,
                season_best=ext is not None and scaled > round(ext[1] * METRICS[metric]),
                season_worst=ext is not None and scaled < round(ext[0] * METRICS[metric]),
            )
        return ShotComparison(f, out, revision)
