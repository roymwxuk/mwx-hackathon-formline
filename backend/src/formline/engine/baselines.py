"""Personal baselines: each shot compared with the shooter's own comparable shots.

Like with like. A shot is filed under its player and under his position group, at
every level of a fallback ladder, from most specific to widest:

    L0  zone × body × pressure      (e.g. outside_central · strong_foot · pressured)
    L1  zone × body
    L2  area × body                 (area: inside or outside the box)
    L3  body                        (all his strong-foot shots)

A lookup uses the most specific level with at least MIN_N shots, and says which
level it used, so a narrator can be honest about the comparison ("all his
strong-foot shots" rather than "from this spot").

Exact and incremental. Values are stored as integers (fixed point), so adding and
removing a shot is exact and order does not matter: a corrected event can be
rolled back without recomputing anything, and a chaotic stream converges to
exactly the same state as a clean one. Each bucket keeps its values sorted, which
gives percentiles and season bests/worsts directly.
"""

from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass, field
from math import sqrt

from formline.engine.features import ShotFeatures

# Smallest sample a level must have before we compare against it. Deliberately low:
# a striker has ~35 shots a season, so fine buckets are thin. Shrinkage toward the
# position-group prior (same level) is what keeps small samples from overclaiming.
MIN_N = 5

# metric -> fixed-point scale (values have at most this many decimals)
METRICS = {"shot_speed_kmh": 10, "placement": 1000, "psxg": 10_000}

LEVELS = ("zone_body_pressure", "zone_body", "area_body", "body")
LEVEL_LABELS = {
    "zone_body_pressure": "same zone, body part and pressure",
    "zone_body": "same zone and body part",
    "area_body": "same area (inside/outside the box) and body part",
    "body": "same body part, anywhere",
}
INSIDE_BOX = {"six_yard", "box_central", "box_wide"}


def metric_values(f: ShotFeatures) -> dict[str, float]:
    """Which metrics this shot contributes to. Penalties and 'other' are excluded."""
    if f.shot_type == "penalty" or f.body_group == "other":
        return {}
    values = {"shot_speed_kmh": f.shot_speed_kmh}
    if f.on_target:
        values["placement"] = f.placement
        values["psxg"] = f.psxg
    return values


def bucket_keys(f: ShotFeatures) -> dict[str, tuple]:
    area = "inside_box" if f.zone in INSIDE_BOX else "outside_box"
    return {
        "zone_body_pressure": (f.zone, f.body_group, f.pressure),
        "zone_body": (f.zone, f.body_group),
        "area_body": (area, f.body_group),
        "body": (f.body_group,),
    }


@dataclass
class Bucket:
    """Exact running statistics over fixed-point integer values."""

    scale: int
    values: list[tuple[int, str]] = field(default_factory=list)  # sorted (value, event_id)
    total: int = 0
    total_sq: int = 0

    def add(self, value: float, event_id: str) -> None:
        v = round(value * self.scale)
        insort(self.values, (v, event_id))
        self.total += v
        self.total_sq += v * v

    def remove(self, value: float, event_id: str) -> None:
        v = round(value * self.scale)
        i = bisect_left(self.values, (v, event_id))
        if i == len(self.values) or self.values[i] != (v, event_id):
            raise KeyError(f"{event_id} not in bucket")
        del self.values[i]
        self.total -= v
        self.total_sq -= v * v

    @property
    def n(self) -> int:
        return len(self.values)

    @property
    def mean(self) -> float | None:
        return self.total / self.n / self.scale if self.n else None

    @property
    def sd(self) -> float | None:
        if self.n < 2:
            return None
        var = (self.total_sq - self.total * self.total / self.n) / (self.n - 1)
        return sqrt(max(var, 0.0)) / self.scale

    def percentile_of(self, value: float) -> float | None:
        """Share of stored values below `value` (ties count half), 0–100."""
        if not self.n:
            return None
        v = round(value * self.scale)
        below = bisect_left(self.values, (v, ""))
        equal = bisect_right(self.values, (v, "￿")) - below
        return 100 * (below + 0.5 * equal) / self.n

    def extremes(self) -> tuple[float, float] | None:
        if not self.n:
            return None
        return self.values[0][0] / self.scale, self.values[-1][0] / self.scale


@dataclass(frozen=True)
class BaselineView:
    """What a lookup returns: the player's bucket and the group's at the same level."""

    metric: str
    level: str
    key: tuple
    player: Bucket | None
    group: Bucket | None
    thin: bool  # no level reached MIN_N; this is the widest one with any data

    @property
    def label(self) -> str:
        return LEVEL_LABELS[self.level]


class BaselineStore:
    def __init__(self, position_groups: dict[str, str]):
        self.position_groups = position_groups  # player_id -> GK/DEF/MID/FWD
        self._buckets: dict[tuple, Bucket] = {}

    def _scopes(self, player_id: str) -> tuple[str, str]:
        return player_id, f"group:{self.position_groups[player_id]}"

    def _bucket(self, scope: str, metric: str, level: str, key: tuple) -> Bucket:
        k = (scope, metric, level, key)
        if k not in self._buckets:
            self._buckets[k] = Bucket(METRICS[metric])
        return self._buckets[k]

    def add(self, f: ShotFeatures) -> None:
        self._apply(f, remove=False)

    def remove(self, f: ShotFeatures) -> None:
        self._apply(f, remove=True)

    def _apply(self, f: ShotFeatures, remove: bool) -> None:
        keys = bucket_keys(f)
        for metric, value in metric_values(f).items():
            for scope in self._scopes(f.player_id):
                for level, key in keys.items():
                    b = self._bucket(scope, metric, level, key)
                    (b.remove if remove else b.add)(value, f.event_id)

    def lookup(self, f: ShotFeatures, metric: str, min_n: int = MIN_N) -> BaselineView | None:
        """The player's baseline for this shot's context, most specific level first."""
        player_scope, group_scope = self._scopes(f.player_id)
        widest: BaselineView | None = None
        for level, key in bucket_keys(f).items():
            pb = self._buckets.get((player_scope, metric, level, key))
            gb = self._buckets.get((group_scope, metric, level, key))
            if pb and pb.n >= min_n:
                return BaselineView(metric, level, key, pb, gb, thin=False)
            if pb and pb.n:
                widest = BaselineView(metric, level, key, pb, gb, thin=True)
        return widest

    def per_player_samples(self) -> dict[tuple[str, str, str], list[list[float]]]:
        """(metric, group, body_group) -> each player's values, for fitting priors."""
        out: dict[tuple[str, str, str], list[list[float]]] = {}
        for (scope, metric, level, key), b in sorted(self._buckets.items()):
            if level != "body" or scope.startswith("group:") or not b.n:
                continue
            group = self.position_groups[scope]
            out.setdefault((metric, group, key[0]), []).append(
                [v / b.scale for v, _ in b.values])
        return out

    def snapshot(self) -> dict[tuple, tuple]:
        """Exact, order-independent state, for convergence and rebuild checks."""
        return {k: (b.n, b.total, b.total_sq, tuple(b.values))
                for k, b in self._buckets.items() if b.n}
