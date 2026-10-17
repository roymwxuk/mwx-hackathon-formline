"""Insight Selector: decides which insight to surface, and when.

Hybrid by design (ADR-008, decision D2):
1. Rules build a shortlist: salience threshold, at most one card per shot, a
   per-player cooldown and a rate limit, so a broadcast never floods.
2. The LLM picks one insight from the shortlist and says why, through a JSON
   contract. Invalid JSON or an id outside the shortlist falls back to the
   top-ranked candidate, so the selector can never surface something the rules
   didn't allow.
"""

import json
from dataclasses import dataclass, field

from formline.agents.llm import LLMRunner
from formline.engine.insights import Insight

MIN_SALIENCE = 0.35
COOLDOWN_MS = 3 * 60_000  # same player again only after 3 match minutes...
COOLDOWN_OVERRIDE = 0.9  # ...unless the insight is this salient (e.g. a season record)
RATE_WINDOW_MS = 10 * 60_000
RATE_MAX = 3  # cards per 10 match minutes

INSTRUCTIONS = """You are the Insight Selector for a live football broadcast.
Each candidate is a deterministic finding about one shot compared with the shooter's own
history. Pick the ONE candidate that best tells viewers why this moment matters: prefer
season records, big gaps from the player's norm, high confidence and goals. Never invent
candidates.
Reply with JSON only: {"show": "<candidate id>", "reason": "<at most 20 words>"}"""


@dataclass(frozen=True)
class Selection:
    insight: Insight
    priority: int  # 1 = most important
    reason: str
    decided_by: str  # "llm" or "rules"


@dataclass
class SelectorState:
    """What has been shown so far, for cooldowns and rate limits."""

    last_shown: dict[str, tuple[int, int]] = field(default_factory=dict)  # player -> time
    shown_times: list[tuple[int, int]] = field(default_factory=list)  # (period, clock)


def priority_of(insight: Insight) -> int:
    return 1 if insight.salience >= 0.8 else 2 if insight.salience >= 0.5 else 3


def _time(ins: Insight) -> tuple[int, int]:
    return ins.period, ins.match_clock_ms


def _within(a: tuple[int, int], b: tuple[int, int], ms: int) -> bool:
    return a[0] == b[0] and 0 <= b[1] - a[1] < ms


def shortlist(candidates: list[Insight], state: SelectorState) -> list[Insight]:
    """Rule-based shortlist for one shot's insights, best first."""
    if not candidates:
        return []
    now = _time(candidates[0])
    recent = [t for t in state.shown_times if _within(t, now, RATE_WINDOW_MS)]
    eligible = []
    for ins in candidates:
        if ins.salience < MIN_SALIENCE:
            continue
        last = state.last_shown.get(ins.player_id)
        if last and _within(last, now, COOLDOWN_MS) and ins.salience < COOLDOWN_OVERRIDE:
            continue
        if len(recent) >= RATE_MAX and ins.salience < COOLDOWN_OVERRIDE:
            continue
        eligible.append(ins)
    return sorted(eligible, key=lambda i: (-i.salience, i.insight_id))


def _candidate_json(ins: Insight, name: str) -> dict:
    f = ins.facts
    return {"id": ins.insight_id, "type": ins.type, "player": name, "direction": ins.direction,
            "salience": ins.salience, "confidence": ins.confidence,
            "value": f["value"], "norm": f["norm"], "est_percentile": f["est_percentile"],
            "outcome": f["outcome"], "season_record": f.get("season_record")}


def parse_choice(text: str, allowed: set[str]) -> tuple[str, str] | None:
    """(id, reason) from the model's JSON, or None if it is unusable."""
    try:
        data = json.loads(strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("show") not in allowed:
        return None
    return data["show"], str(data.get("reason", ""))[:200]


def strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()


async def select(candidates: list[Insight], state: SelectorState, runner: LLMRunner,
                 names: dict[str, str]) -> Selection | None:
    """Choose at most one insight from one shot's candidates and record it as shown."""
    short = shortlist(candidates, state)
    if not short:
        return None
    top = short[0]
    choice = None
    if len(short) > 1:
        payload = {"candidates": [_candidate_json(i, names[i.player_id]) for i in short]}
        text = await runner.complete("insight_selector", INSTRUCTIONS,
                                     json.dumps(payload, ensure_ascii=False))
        choice = parse_choice(text, {i.insight_id for i in short})
    if choice:
        chosen = next(i for i in short if i.insight_id == choice[0])
        selection = Selection(chosen, priority_of(chosen), choice[1], "llm")
    else:
        why = "only eligible candidate" if len(short) == 1 else "fallback: highest salience"
        selection = Selection(top, priority_of(top), why, "rules")
    now = _time(selection.insight)
    state.last_shown[selection.insight.player_id] = now
    state.shown_times.append(now)
    return selection
