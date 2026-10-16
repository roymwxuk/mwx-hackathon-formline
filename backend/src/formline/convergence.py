"""Convergence check: does a chaotic stream end in exactly the right state?

Truth is the final version of every event in the append-only log (ADR-007). For one
chaotic replay of a match we check, from strongest to most conditional:

1. **Baselines == rebuild from the log.** Incremental processing of the chaotic
   stream (duplicates, reordering, late messages, corrections, reverts, deletes)
   must give exactly the state of a batch rebuild from `current_events()`.
2. **Baselines == clean run**, when chaos injected no corrections or deletes (so the
   truth is the clean feed).
3. **Insights == clean run**, when there were also no beyond-window late messages.
   Insights describe what was known when the shot happened, so a shot that arrives
   after its window legitimately changes what later shots were compared against;
   within the window, the reorder buffer must make chaos invisible.

Run a sweep: `uv run python -m formline.convergence --runs 300`.
"""

import argparse
import copy
import random
import sys
from dataclasses import dataclass

from formline.chaos import ChaosConfig, ChaosReport, inject
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied, ingest_all
from formline.engine.log import current_events
from formline.engine.pipeline import LivePipeline
from formline.schema.feed import FeedMessage


@dataclass(frozen=True)
class ConvergenceResult:
    report: ChaosReport
    late_observed: int
    baselines_match_log: bool
    baselines_match_clean: bool | None  # None: not applicable (corrections/deletes injected)
    insights_match_clean: bool | None  # None: not applicable (also late messages)
    # Informational: with late messages (but no new truth), did insights still match?
    insights_match_clean_despite_late: bool | None


class ConvergenceChecker:
    """Holds the clean reference for one match so many chaotic runs can be compared."""

    def __init__(self, feed: list[FeedMessage], history: BaselineEngine):
        self.feed = feed
        self.history = history  # bootstrapped engine with frozen priors; never mutated
        clean = self._engine()
        clean.apply_all(ingest_all(feed))
        self.clean_snapshot = clean.store.snapshot()
        self.clean_insights = LivePipeline(self._engine()).run(feed)

    def _engine(self) -> BaselineEngine:
        return copy.deepcopy(self.history)

    def check(self, config: ChaosConfig) -> ConvergenceResult:
        chaotic = inject(self.feed, config)
        messages, report = chaotic.messages, chaotic.report

        pipeline = LivePipeline(self._engine())
        insights = pipeline.run(messages)
        incremental = pipeline.engine.store.snapshot()

        rebuilt = self._engine()
        rebuilt.apply_all(Applied(e) for e in current_events(messages))

        no_new_truth = report.corrections == 0 and report.deletes == 0
        late = pipeline.ingestor.stats.late
        in_window = no_new_truth and late == 0
        with_late = no_new_truth and late > 0
        return ConvergenceResult(
            report=report,
            late_observed=pipeline.ingestor.stats.late,
            baselines_match_log=incremental == rebuilt.store.snapshot(),
            baselines_match_clean=(incremental == self.clean_snapshot) if no_new_truth else None,
            insights_match_clean=(insights == self.clean_insights) if in_window else None,
            insights_match_clean_despite_late=(
                insights == self.clean_insights) if with_late else None,
        )


def random_config(rng: random.Random) -> ChaosConfig:
    return ChaosConfig(
        seed=rng.randrange(10**9),
        duplicate_rate=rng.uniform(0, 0.3),
        reorder_rate=rng.uniform(0, 0.3),
        late_rate=rng.choice([0.0, rng.uniform(0, 0.1)]),
        correction_rate=rng.choice([0.0, rng.uniform(0, 1)]),
        revert_rate=rng.uniform(0, 1),
        delete_rate=rng.choice([0.0, 0.0, rng.uniform(0, 0.05)]),
    )


def main(argv: list[str] | None = None) -> int:
    from formline.generator.season import generate_season

    parser = argparse.ArgumentParser(prog="python -m formline.convergence")
    parser.add_argument("--runs", type=int, default=300)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    season = generate_season(args.seed)
    history = BaselineEngine(season.league.players)
    history.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                      for e in current_events(gm.feed))
    history.fit_priors()
    live = next(gm.feed for gm in season.matches if gm.match.is_live_demo)
    checker = ConvergenceChecker(live, history)

    rng = random.Random(f"sweep:{args.seed}")
    totals = {"messages": 0, "duplicates": 0, "reordered": 0, "late_observed": 0,
              "corrections": 0, "reverts": 0, "deletes": 0}
    log_ok = clean_ok = clean_n = ins_ok = ins_n = late_same = late_n = 0
    failures = []
    for _ in range(args.runs):
        config = random_config(rng)
        r = checker.check(config)
        rep = r.report
        totals["messages"] += rep.messages_out
        for key in ("duplicates", "reordered", "corrections", "reverts", "deletes"):
            totals[key] += getattr(rep, key)
        totals["late_observed"] += r.late_observed
        log_ok += r.baselines_match_log
        if r.baselines_match_clean is not None:
            clean_n += 1
            clean_ok += r.baselines_match_clean
        if r.insights_match_clean is not None:
            ins_n += 1
            ins_ok += r.insights_match_clean
        if r.insights_match_clean_despite_late is not None:
            late_n += 1
            late_same += r.insights_match_clean_despite_late
        if not r.baselines_match_log or r.baselines_match_clean is False \
                or r.insights_match_clean is False:
            failures.append(config)

    print(f"chaotic replays: {args.runs} of the live match ({totals['messages']:,} messages)")
    print("injected: " + ", ".join(f"{v:,} {k.replace('_', ' ')}" for k, v in totals.items()
                                   if k != "messages"))
    print(f"baselines == rebuild from log: {log_ok}/{args.runs}")
    print(f"baselines == clean run (no corrections/deletes): {clean_ok}/{clean_n}")
    print(f"insights == clean run (also no late messages): {ins_ok}/{ins_n}")
    print(f"info: insights unchanged despite late messages: {late_same}/{late_n} "
          "(a late shot can change what later shots were compared against)")
    for config in failures[:5]:
        print(f"FAILED: {config}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
