"""The Researcher: a tool-using agent that gathers the facts a typed question needs.

It may look something up, read the result and look up more (e.g. find the top scorer, then
his last 3 games), within hard limits enforced in our code: at most 5 tool calls
(`tools.ResearchSession`, admitted before each call) and a model-call allowance charged on
every round-trip (`LLMRunner.research`). It writes nothing the viewer sees: its final reply
is `{"done": true}` or `{"cannot_answer": true}`; the gathered lookups go to the Analyst and
the Verifier (docs/plan-agentic-research.md).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass

from formline.agents.llm import LLMRunner
from formline.agents.selector import strip_fences
from formline.analyst.followups import Moment
from formline.analyst.store import MatchContext
from formline.analyst.tools import ResearchSession
from formline.prompts import load

PROMPT = load("researcher")  # prompts/researcher.md
MAX_MODEL_CALLS = 6  # round-trips for one research run, the final reply included


class ResearchFailed(RuntimeError):
    """Malformed final reply, or done without any evidence: the caller falls back."""

    def __init__(self, outcome: str, detail: str = ""):
        super().__init__(detail or outcome)
        self.outcome = outcome


@dataclass(frozen=True)
class Research:
    session: ResearchSession
    cannot_answer: bool


def payload(text: str, lang: str, m: Moment, ctx: MatchContext,
            short_names: dict[str, str]) -> dict:
    shot = {s.player_id for s in m.shots}
    players = [{"id": pid, "name": ctx.league.players[pid][0], "name_ja": ctx.league.players[pid][1],
                "club": m.clubs[p.club_id], "has_shot": pid in shot}
               for pid, p in m.players.items() if p.club_id in (m.home, m.away)]
    clubs = [{"id": c, "name": m.clubs[c], "short_name": short_names.get(c, "")}
             for c in (m.home, m.away)]
    now = max(m.events, key=lambda e: (e.period, e.match_clock_ms))
    return {"VIEWER_TEXT": text, "LANGUAGE": lang, "CLUBS": clubs, "PLAYERS": players,
            "MINUTE_NOW": now.match_clock_ms // 60_000 + 1}


async def research(text: str, lang: str, m: Moment, ctx: MatchContext, runner: LLMRunner,
                   short_names: dict[str, str] | None = None,
                   norm: Callable[[str], float | None] | None = None,
                   max_model_calls: int = MAX_MODEL_CALLS) -> Research:
    """Run the Researcher; raises BudgetExceeded (allowance or budget) or ResearchFailed."""
    session = ResearchSession(m, ctx, norm)
    reply = await runner.research(
        "researcher", PROMPT.text,
        json.dumps(payload(text, lang, m, ctx, dict(short_names or {})), ensure_ascii=False),
        session.tools(), max_model_calls)
    try:  # the first JSON object: the model sometimes repeats it ('{"done": true} {"done": true}')
        final, _ = json.JSONDecoder().raw_decode(strip_fences(reply or "").strip())
    except (json.JSONDecodeError, TypeError):
        raise ResearchFailed("fallback_malformed", f"final reply is not JSON: {reply!r:.80}") from None
    if not isinstance(final, dict):
        raise ResearchFailed("fallback_malformed", "final reply is not a JSON object")
    if final.get("cannot_answer") is True:
        return Research(session, cannot_answer=True)
    if final.get("done") is not True:
        raise ResearchFailed("fallback_malformed", f"unexpected final reply {final!r:.80}")
    if not session.lookups:
        raise ResearchFailed("fallback_no_evidence", "done without any successful lookup")
    return Research(session, cannot_answer=False)
