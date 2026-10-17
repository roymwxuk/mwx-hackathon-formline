"""Insight detection and lineage.

Detection decides *why a shot matters* against the shooter's own baseline. It is
deterministic: the LLM narrator (milestone 3) only words what is found here, and the
verifier checks every number against `Insight.facts`.

Lineage: each insight lists `source_event_ids` (the shot and its key pass). When a
source event is revised (a VAR overturn, a changed outcome or shooter), the tracker
re-detects from the corrected shot and, for every insight that depended on it, emits
nothing (still true), a correction (same insight, new facts) or a retraction (no
longer true). The same mechanism serves explainability and consistency.

Known limit: a revision rolls the baseline back exactly, but insights already shown
for *later* shots are not recomputed, even though their baseline briefly included the
revised shot. One shot shifts a baseline of 5+ shots only slightly.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from formline.engine.engine import MetricComparison, ShotComparison

NOTABLE_LOW = 25.0  # estimated percentile at or below which a shot is notable
NOTABLE_HIGH = 75.0
MIN_SEASON_N = 5  # a season record needs at least this many earlier shots to beat
MIN_THIN_N = 3  # below this, a thin comparison is noise, not an insight

INSIGHT_TYPES = {
    "shot_speed_kmh": "shot_speed_vs_norm",
    "placement": "placement_vs_norm",
    "psxg": "finish_vs_norm",
}
SEASON_TYPES = {"best": "season_best", "worst": "season_worst"}


@dataclass(frozen=True)
class Insight:
    insight_id: str
    type: str
    metric: str
    player_id: str
    team_id: str
    match_id: str
    period: int
    match_clock_ms: int
    direction: str  # above / below
    salience: float  # 0–1, higher = more worth showing
    confidence: str  # high / medium / low (sample support after shrinkage)
    facts: dict  # every number a narrator may use, already rounded for display
    source_event_ids: tuple[str, ...]
    version: int = 1
    status: str = "active"  # active / corrected / retracted
    supersedes: str | None = None


@dataclass(frozen=True)
class InsightCreated:
    insight: Insight


@dataclass(frozen=True)
class InsightCorrected:
    before: Insight
    after: Insight
    reason: str


@dataclass(frozen=True)
class InsightRetracted:
    insight: Insight
    reason: str


InsightChange = InsightCreated | InsightCorrected | InsightRetracted


def _confidence(m: MetricComparison) -> str:
    if m.thin or m.weight < 0.4:
        return "low"
    return "high" if m.weight >= 0.7 else "medium"


def _facts(c: ShotComparison, m: MetricComparison) -> dict:
    f = c.features
    scale = {"shot_speed_kmh": 1, "placement": 3, "psxg": 2}[m.metric]
    facts = {
        "metric": m.metric,
        "value": round(m.value, scale),
        "norm": round(m.shrunk_mean, scale),
        "delta": round(m.value - m.shrunk_mean, scale),
        "est_percentile": round(m.est_percentile),
        "sample_n": m.n,
        "comparison": m.level_label,
        "comparison_level": m.level,
        "weight_on_own_shots": round(m.weight, 2),
        "group_prior": round(m.prior_mean, scale),
        "thin_sample": m.thin,
        "season_record": ("best" if m.season_best else "worst" if m.season_worst else None)
        if m.season_n >= MIN_SEASON_N else None,
        "season_sample_n": m.season_n,
        "zone": f.zone,
        "body_group": f.body_group,
        "pressure": f.pressure,
        "distance_m": round(f.distance_m, 1),
        "outcome": f.outcome,
        "xg": round(f.xg, 2),
        "shot_speed_kmh": f.shot_speed_kmh,
    }
    if f.psxg is not None:
        facts["psxg"] = round(f.psxg, 2)
    return facts


def detect(c: ShotComparison) -> list[Insight]:
    """Notable metrics of one compared shot, as insights (not yet chosen for display)."""
    f = c.features
    out: list[Insight] = []
    sources = (f.event_id,) + ((f.key_pass_event_id,) if f.key_pass_event_id else ())
    for metric, m in c.metrics.items():
        if m.thin and m.n < MIN_THIN_N:
            continue
        notable = m.est_percentile <= NOTABLE_LOW or m.est_percentile >= NOTABLE_HIGH
        above = m.value >= m.shrunk_mean
        season = None
        # Season records only for speed (placement/PSxG are too noisy), only with enough
        # earlier shots to beat, and only when the record agrees with the baseline.
        if metric == "shot_speed_kmh" and m.season_n >= MIN_SEASON_N:
            if m.season_best and above:
                season = "best"
            elif m.season_worst and not above:
                season = "worst"
        if not notable and not season:
            continue
        extremity = abs(m.est_percentile - 50) / 50
        salience = extremity * (0.5 + 0.5 * m.weight) + (0.25 if season else 0.0)
        salience += 0.1 if f.outcome == "goal" else 0.0
        kind = SEASON_TYPES[season] if season else INSIGHT_TYPES[metric]
        out.append(Insight(
            insight_id=f"ins_{f.event_id}_{kind}",
            type=kind,
            metric=metric,
            player_id=f.player_id,
            team_id=f.team_id,
            match_id=f.match_id,
            period=f.period,
            match_clock_ms=f.match_clock_ms,
            direction="above" if above else "below",
            salience=round(min(1.0, salience), 3),
            confidence=_confidence(m),
            facts=_facts(c, m),
            source_event_ids=sources,
        ))
    return out


def _diff(before: dict, after: dict) -> str:
    keys = ("outcome", "value", "norm", "est_percentile", "body_group", "zone")
    changed = [f"{k} {before.get(k)} → {after.get(k)}" for k in keys
               if before.get(k) != after.get(k)]
    return "; ".join(changed) or "facts changed"


@dataclass
class InsightTracker:
    """Keeps the live insight set and the lineage index (event_id → insight ids)."""

    insights: dict[str, Insight] = field(default_factory=dict)  # current version by id
    by_event: dict[str, set[str]] = field(default_factory=dict)

    def active(self) -> list[Insight]:
        return sorted((i for i in self.insights.values() if i.status != "retracted"),
                      key=lambda i: (i.period, i.match_clock_ms, i.insight_id))

    def _index(self, insight: Insight) -> None:
        self.insights[insight.insight_id] = insight
        for eid in insight.source_event_ids:
            self.by_event.setdefault(eid, set()).add(insight.insight_id)

    def on_comparisons(self, comparisons: Iterable[ShotComparison]) -> list[InsightChange]:
        changes: list[InsightChange] = []
        for c in comparisons:
            if c.revision:
                changes += self._revise(c.features.event_id, detect(c), "revision", c)
            else:
                for ins in detect(c):
                    self._index(ins)
                    changes.append(InsightCreated(ins))
        return changes

    def on_deleted(self, event_id: str) -> list[InsightChange]:
        return self._revise(event_id, [], "source event deleted")

    def _revise(self, event_id: str, fresh: list[Insight], why: str,
                revised: ShotComparison | None = None) -> list[InsightChange]:
        changes: list[InsightChange] = []
        fresh_by_id = {i.insight_id: i for i in fresh}
        for iid in sorted(self.by_event.get(event_id, set())):
            old = self.insights[iid]
            if old.status == "retracted":
                continue
            new = fresh_by_id.pop(iid, None)
            if new is None:
                gone = replace(old, status="retracted")
                self.insights[iid] = gone
                if revised is not None and old.metric not in revised.metrics:
                    reason = (f"{why}: {old.metric} no longer applies "
                              f"(outcome {revised.features.outcome})")
                else:
                    reason = f"{why}: no longer notable"
                changes.append(InsightRetracted(gone, reason))
            elif new.facts != old.facts:
                corrected = replace(new, version=old.version + 1, status="corrected",
                                    supersedes=old.insight_id)
                self._index(corrected)
                changes.append(InsightCorrected(old, corrected, _diff(old.facts, new.facts)))
        for ins in fresh_by_id.values():  # newly notable after the correction
            self._index(ins)
            changes.append(InsightCreated(ins))
        return changes
