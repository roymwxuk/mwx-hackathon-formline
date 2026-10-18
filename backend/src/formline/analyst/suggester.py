"""The Question Suggester: picks which follow-up questions to offer after a key moment.

The model only *chooses*: OPTIONS are the catalog questions that apply to this moment
(`analyst/followups.py`), and its JSON reply `{"pick": [...]}` is checked in code (known ids
only, no repeats, 2–3 of them). One retry with the problem stated, then the moment's default
order, so a moment always gets valid questions. One call per moment, for both languages: the
button wording comes from the catalog, not from the model.
"""

import json
from dataclasses import dataclass

from formline.agents.llm import LLMRunner
from formline.agents.selector import strip_fences
from formline.analyst.facts import FactsPack
from formline.analyst.followups import DESCRIPTIONS
from formline.prompts import load

MAX_ATTEMPTS = 2
MIN_PICKS, MAX_PICKS = 2, 3

PROMPT = load("suggester")  # prompts/suggester.md
INSTRUCTIONS = PROMPT.text


@dataclass(frozen=True)
class Suggestion:
    picks: list[str]
    source: str  # "llm" or "rule"
    attempts: int


def check_picks(reply: object, options: list[str]) -> str | None:
    """None if the reply is a valid pick, else the problem (fed back on the retry)."""
    if not isinstance(reply, dict) or not isinstance(reply.get("pick"), list):
        return 'reply with {"pick": [...]} only'
    picks = reply["pick"]
    unknown = [p for p in picks if p not in options]
    if unknown:
        return f"unknown option(s) {unknown}; use only {options}"
    if len(set(picks)) != len(picks):
        return "each option at most once"
    want_min = min(MIN_PICKS, len(options))
    if not want_min <= len(picks) <= MAX_PICKS:
        return f"pick between {want_min} and {MAX_PICKS} options"
    return None


async def suggest(pack: FactsPack, options: list[str], runner: LLMRunner) -> Suggestion:
    """Pick follow-up questions for the moment of `pack` from `options` (best first)."""
    if len(options) <= 1:
        return Suggestion(list(options), "rule", 0)
    payload = {"MOMENT": pack.question, "MOMENT_FACTS": pack.facts,
               "OPTIONS": {q: DESCRIPTIONS[q] for q in options}}
    feedback = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if feedback:
            payload["FIX_THIS_PROBLEM"] = feedback
        try:
            text = await runner.complete("suggester", INSTRUCTIONS,
                                         json.dumps(payload, ensure_ascii=False),
                                         use_cache=feedback is None)
            reply = json.loads(strip_fences(text))
        except Exception as exc:  # noqa: BLE001 - bad JSON, timeouts, budget: retry, then rule
            feedback = f"{exc}; reply with the JSON object only"
            continue
        feedback = check_picks(reply, options)
        if feedback is None:
            return Suggestion(list(reply["pick"]), "llm", attempt)
    return Suggestion(options[:MAX_PICKS], "rule", MAX_ATTEMPTS)
