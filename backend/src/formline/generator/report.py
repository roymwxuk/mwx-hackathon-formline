"""Realism report: generated aggregates vs public league figures."""

import json
import statistics as st
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from formline.generator.output import read_feed
from formline.generator.pitch import in_box
from formline.schema.feed import FeedMessage

SOURCES = {
    "pl_trends": "https://www.premierleague.com/news/4271974",
    "pl_passes": "https://www.premierleague.com/en/news/4461793/what-are-the-biggest-trends-from-202526-so-far",
    "goals": "https://extratime.com/stats/2129/2287/premier-league/",
    "shot_speed": "https://www.bundesliga.com/en/bundesliga/news/new-match-fact-aws-shot-speed-stat-25227",
}


@dataclass
class Check:
    metric: str
    value: float
    lo: float
    hi: float
    reference: str
    fmt: str = "{:.1f}"

    @property
    def ok(self) -> bool:
        return self.lo <= self.value <= self.hi


def latest_events(feed: list[FeedMessage]) -> list:
    """Apply the feed: highest version per event_id wins; deletes remove."""
    best: dict[str, FeedMessage] = {}
    for msg in feed:
        prev = best.get(msg.event_id)
        if prev is None or msg.version > prev.version:
            best[msg.event_id] = msg
    return sorted((m.event for m in best.values() if m.event is not None),
                  key=lambda e: e.event_time)


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[round(q * (len(s) - 1))]


def compute(data: Path) -> tuple[list[Check], dict]:
    matches = json.loads((data / "matches.json").read_text())
    history = [m for m in matches if not m["is_live_demo"]]
    per_match = []
    foot, head, shooters = [], [], Counter()
    for m in history:
        events = latest_events(read_feed(data / "feeds" / f"{m['match_id']}.jsonl"))
        passes = [e for e in events if e.type == "pass"]
        shots = [e for e in events if e.type == "shot"]
        per_match.append({
            "passes": len(passes),
            "completion": sum(p.outcome == "complete" for p in passes) / len(passes),
            "shots": len(shots),
            "goals": sum(s.outcome == "goal" for s in shots),
            "on_target": sum(s.outcome in ("goal", "saved") for s in shots) / len(shots),
            "in_box": sum(in_box(s.x, s.y) for s in shots) / len(shots),
            "fouls": sum(e.type == "foul_committed" for e in events),
            "cards": sum(e.type == "card" for e in events),
            "pressures": sum(e.type == "pressure" for e in events),
        })
        for s in shots:
            shooters[s.player_id] += 1
            (head if s.body_part == "head" else foot).append(s.tracking.shot_speed_kmh)

    def avg(key: str) -> float:
        return st.mean(pm[key] for pm in per_match)

    total_goals = sum(pm["goals"] for pm in per_match)
    total_shots = sum(pm["shots"] for pm in per_match)
    checks = [
        Check("Passes per match", avg("passes"), 850, 1050,
              "~900 attempts (748 completed/match, PL 2024/25)", "{:.0f}"),
        Check("Pass completion", avg("completion") * 100, 78, 86,
              "~83% (748 completed of ~900)", "{:.1f}%"),
        Check("Shots per match", avg("shots"), 22, 30, "26.1 (PL 2024/25)"),
        Check("Goals per match", avg("goals"), 2.4, 3.4, "2.97 (PL 2024/25)", "{:.2f}"),
        Check("Shot conversion", total_goals / total_shots * 100, 9, 13, "11% (PL 2024/25)",
              "{:.1f}%"),
        Check("Shots on target", avg("on_target") * 100, 30, 38, "about a third (assumption)",
              "{:.1f}%"),
        Check("Shots from inside the box", avg("in_box") * 100, 60, 82,
              "most shots (assumption)", "{:.1f}%"),
        Check("Foot shot speed, median (km/h)", pct(foot, 0.5), 70, 90,
              "most shots well under 100 km/h"),
        Check("Foot shots above 100 km/h", sum(v > 100 for v in foot) / len(foot) * 100, 1, 10,
              ">100 km/h is highlighted as notable", "{:.1f}%"),
        Check("Header speed, median (km/h)", pct(head, 0.5), 40, 65,
              "headers much slower than foot shots"),
        Check("Fouls per match", avg("fouls"), 16, 26, "about 20 (assumption)"),
        Check("Cards per match", avg("cards"), 2, 5, "about 3.5 (assumption)"),
    ]
    extra = {
        "matches": len(history),
        "foot_speed": {q: pct(foot, q / 100) for q in (10, 25, 50, 75, 90, 99)},
        "foot_speed_max": max(foot),
        "header_share": len(head) / (len(head) + len(foot)) * 100,
        "pressures": avg("pressures"),
        "shooters_15": sum(n >= 15 for n in shooters.values()),
        "shooters_25": sum(n >= 25 for n in shooters.values()),
        "top_shooter_shots": shooters.most_common(1)[0][1],
    }
    return checks, extra


def render(checks: list[Check], extra: dict, seed: int | None = None) -> str:
    rows = "\n".join(
        f"| {c.metric} | {c.fmt.format(c.value)} | {c.fmt.format(c.lo)}–{c.fmt.format(c.hi)} "
        f"| {c.reference} | {'✅' if c.ok else '❌'} |"
        for c in checks
    )
    fs = extra["foot_speed"]
    speeds = " · ".join(f"p{q} {v:.0f}" for q, v in fs.items())
    seed_note = f" (seed {seed})" if seed is not None else ""
    return f"""# Realism report

Generated by `uv run formline-gen report`{seed_note} over {extra['matches']} historical
matches. The live demo match is excluded because its key moments are scripted.

| Metric | Generated | Target range | Reference | OK |
|---|---|---|---|---|
{rows}

**Shot speed distribution (foot shots, km/h):** {speeds} · max {extra['foot_speed_max']:.0f}.
Headers are {extra['header_share']:.1f}% of shots.

**Baseline sample sizes:** {extra['shooters_15']} players have at least 15 shots in
the history and {extra['shooters_25']} have at least 25 (top: {extra['top_shooter_shots']}).
Low-volume players are kept on purpose: they are the case shrinkage exists for.

**Pressure events:** {extra['pressures']:.0f} per match (pressure is logged only on the
ball carrier here, so it is lower than full-pitch pressure counts).

## Sources

- Shots, conversion and goals trend: [Premier League]({SOURCES['pl_trends']})
- Completed passes per match: [Premier League]({SOURCES['pl_passes']})
- Goals per game 2024/25: [Extratime]({SOURCES['goals']})
- Shot speed above 100 km/h is a broadcast highlight: [Bundesliga]({SOURCES['shot_speed']})

Targets are season aggregates, used only to calibrate the generator. Rows marked
"assumption" have no cited source yet. No real match or player data is used.
"""
