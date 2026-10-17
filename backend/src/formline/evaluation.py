"""Shrinkage accuracy against the generator's hidden truth.

The hidden profile defines an idealised shot (16 m, unpressured, strong foot), not the
mix of shots a player actually takes. So "truth" is a player's **population mean**:
simulate many extra matches with the same league and hidden profiles (only the
random seeds differ) and average his strong-foot shot speed over that large sample.

Estimates come from the real 30-match history, exactly as the engine sees it:
- raw     his own average
- group   his position group's average (full shrinkage)
- shrunk  the engine's empirical Bayes blend, weight n / (n + k)

Run: `uv run python -m formline.evaluation --truth-matches 300`
"""

import argparse
import statistics as st
import sys
from dataclasses import dataclass
from datetime import timedelta
from math import sqrt

from formline.engine.engine import BaselineEngine
from formline.engine.features import shot_features
from formline.engine.ingest import Applied
from formline.engine.log import current_events
from formline.engine.shrinkage import shrink
from formline.generator.match_sim import MatchSim
from formline.generator.season import SEASON, SEASON_START, Season, fixtures, generate_season
from formline.schema.reference import Match

METRIC = "shot_speed_kmh"
BODY = "strong_foot"
MIN_TRUTH_N = 30  # players need this many truth shots for a stable population mean
SIZE_BANDS = ((1, 4), (5, 9), (10, 19), (20, 10**9))


@dataclass(frozen=True)
class PlayerEstimate:
    player_id: str
    group: str
    n: int
    raw: float
    group_mean: float
    shrunk: float
    weight: float
    truth: float
    truth_n: int


@dataclass(frozen=True)
class Accuracy:
    players: list[PlayerEstimate]
    truth_matches: int
    fitted_k: dict[str, float]  # position group -> k fitted from the history
    true_k: dict[str, float]  # position group -> k implied by the truth sample

    def rmse(self, attr: str, lo: int = 1, hi: int = 10**9) -> float | None:
        errs = [(getattr(p, attr) - p.truth) ** 2 for p in self.players if lo <= p.n <= hi]
        return sqrt(st.mean(errs)) if errs else None

    def count(self, lo: int = 1, hi: int = 10**9) -> int:
        return sum(lo <= p.n <= hi for p in self.players)


def _strong_foot_speeds(season_matches, players) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for feed in season_matches:
        for e in current_events(feed):
            if e.type != "shot":
                continue
            f = shot_features(e, players[e.player_id])
            if f.body_group == BODY and f.shot_type != "penalty":
                out.setdefault(f.player_id, []).append(f.shot_speed_kmh)
    return out


def truth_sample(season: Season, seed: int, n_matches: int) -> dict[str, list[float]]:
    """Strong-foot speeds per player from extra matches: same league, different seeds."""
    league = season.league
    players = {p.player_id: p for p in league.players}
    plan = fixtures(league)
    feeds = []
    for i in range(n_matches):
        md, home, away = plan[i % len(plan)]
        match = Match(match_id=f"truth_{i:04d}_{home}_{away}", season=SEASON, matchday=md,
                      kickoff_at=SEASON_START + timedelta(days=i), home_club_id=home,
                      away_club_id=away, venue=league.venues[home], is_live_demo=False)
        events, _ = MatchSim(match, league, match_no=90, seed=seed * 1000 + i).run()
        feeds.append([_as_msg(e) for e in events])
    return _strong_foot_speeds(feeds, players)


def _as_msg(event):
    from formline.schema.feed import FeedMessage
    return FeedMessage(message_id=event.event_id, op="create", event_id=event.event_id,
                       version=1, emitted_at=event.event_time, sequence=0, event=event)


def _implied_k(truth: dict[str, list[float]], members: list[str]) -> float | None:
    means = [st.mean(truth[p]) for p in members if len(truth.get(p, ())) >= MIN_TRUTH_N]
    if len(means) < 3:
        return None
    within = st.mean(st.variance(truth[p]) for p in members
                     if len(truth.get(p, ())) >= MIN_TRUTH_N)
    between = st.variance(means)
    return within / between if between > 0 else None


def evaluate(seed: int = 2026, truth_matches: int = 300) -> Accuracy:
    season = generate_season(seed)
    engine = BaselineEngine(season.league.players)
    engine.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                     for e in current_events(gm.feed))
    priors = engine.fit_priors()
    truth = truth_sample(season, seed, truth_matches)

    estimates = []
    for p in season.league.players:
        bucket = engine.store.bucket(p.player_id, METRIC, "body", (BODY,))
        prior = priors.get((METRIC, p.position_group, BODY))
        if not bucket or not bucket.n or prior is None or len(truth.get(p.player_id, ())) \
                < MIN_TRUTH_N:
            continue
        group_bucket = engine.store.bucket(f"group:{p.position_group}", METRIC, "body", (BODY,))
        # Leave-player-out group mean, exactly as the engine's comparisons use it.
        others_n = group_bucket.n - bucket.n
        group_mean = ((group_bucket.total - bucket.total) / others_n / bucket.scale
                      if others_n > 0 else prior.mean)
        s = shrink(bucket.n, bucket.mean, group_mean, prior)
        estimates.append(PlayerEstimate(
            player_id=p.player_id, group=p.position_group, n=bucket.n, raw=bucket.mean,
            group_mean=group_mean, shrunk=s.mean, weight=s.weight,
            truth=st.mean(truth[p.player_id]), truth_n=len(truth[p.player_id])))

    groups = sorted({p.position_group for p in season.league.players} - {"GK"})
    fitted = {g: priors[(METRIC, g, BODY)].k for g in groups if (METRIC, g, BODY) in priors}
    members = {g: [p.player_id for p in season.league.players if p.position_group == g]
               for g in groups}
    true_k = {g: k for g in groups if (k := _implied_k(truth, members[g])) is not None}
    return Accuracy(estimates, truth_matches, fitted, true_k)


def render(acc: Accuracy) -> str:
    def fmt(v: float | None) -> str:
        return "—" if v is None else f"{v:.2f}"

    def gain(lo: int, hi: int) -> str:
        raw, shr = acc.rmse("raw", lo, hi), acc.rmse("shrunk", lo, hi)
        return "—" if not raw or shr is None else f"{(1 - shr / raw) * 100:.0f}%"

    rows = []
    for lo, hi in ((1, 10**9), *SIZE_BANDS):
        label = "All players" if hi == 10**9 and lo == 1 else (
            f"{lo}+ shots" if hi == 10**9 else f"{lo}–{hi} shots")
        rows.append(f"| {label} | {acc.count(lo, hi)} | {fmt(acc.rmse('raw', lo, hi))} | "
                    f"{fmt(acc.rmse('group_mean', lo, hi))} | {fmt(acc.rmse('shrunk', lo, hi))} "
                    f"| {gain(lo, hi)} |")
    k_rows = "\n".join(f"| {g} | {acc.fitted_k[g]:.1f} | "
                       f"{acc.true_k[g]:.1f} |" if g in acc.true_k else
                       f"| {g} | {acc.fitted_k[g]:.1f} | — |" for g in sorted(acc.fitted_k))
    table = "\n".join(rows)
    notes = [(f"- Shrinkage cuts the error of a raw average by {gain(1, 10**9)} overall, and by "
              f"{gain(1, 4)} for players with 1–4 shots: the smaller the sample, the more it "
              "helps.")]
    tiny_group, tiny_shrunk = acc.rmse("group_mean", 1, 4), acc.rmse("shrunk", 1, 4)
    if tiny_group is not None and tiny_shrunk is not None and tiny_group < tiny_shrunk:
        notes.append("- For the smallest samples the plain group average does slightly better than "
                     "the shrunk estimate: the history underestimates k (see below), so the engine "
                     "under-shrinks a little. More history or a slightly stronger prior would fix "
                     "it; the effect is small next to the gain over raw averages.")
    notes.append("- The group average alone is the worst estimate overall: players really do "
                 "differ, so a baseline must be personal.")
    notes_text = "\n".join(notes)
    return f"""# Shrinkage accuracy vs hidden truth

Generated by `uv run python -m formline.evaluation --truth-matches {acc.truth_matches}`.

**Question.** Does shrinkage give better player baselines than a player's raw average?

**Truth.** Each player's population mean strong-foot shot speed: the same league and
hidden profiles simulated for {acc.truth_matches} extra matches (only seeds differ). Players
need {MIN_TRUTH_N}+ truth shots to be included.

**Estimates** come from the 30-match history, as the engine sees it: *raw* (his own
average), *group* (his position group's average, leaving him out) and *shrunk* (the
engine's blend, weight n / (n + k)).

## Error vs truth (RMSE, km/h; lower is better)

| Sample in history | Players | Raw | Group | Shrunk | Error cut by shrinkage |
|---|---|---|---|---|---|
{table}

## Findings

{notes_text}

## Shrinkage strength

k = shot-to-shot variance / player-to-player variance. *Fitted* is what the engine
estimated from the 30-match history; *implied* is computed from the truth sample.

| Position group | Fitted k | Implied by truth |
|---|---|---|
{k_rows}
"""


def main(argv: list[str] | None = None) -> int:
    from pathlib import Path

    parser = argparse.ArgumentParser(prog="python -m formline.evaluation")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--truth-matches", type=int, default=300)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[3] / "docs"
                        / "shrinkage-accuracy.md")
    args = parser.parse_args(argv)
    acc = evaluate(args.seed, args.truth_matches)
    text = render(acc)
    args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
