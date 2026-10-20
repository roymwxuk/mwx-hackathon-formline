"""Answer a follow-up question a viewer clicked (`POST /matches/{id}/ask`).

The request names the comment's moment and the feed sequence it was written at (the
comment's `ask` field), the question and the language. A precomputed answer is served as
is; otherwise the events known at that sequence are replayed from the feed, the question is
checked against the catalog (it must apply to that moment), and the Analyst agent answers
it live from the facts pack, verified, under the runner's cache and call budget.

A question the viewer typed (`answer_free`) is answered "RAG over computed facts": the
Question Router (`analyst/router.py`) picks the fact sections (`analyst/sections.py`) that
answer it, and the Analyst answers the viewer's own question from only those facts.
"""

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from formline.agents.llm import BudgetExceeded, LLMRunner
from formline.analyst.agent import Answer, answer_verified, role_names
from formline.analyst.followups import (
    Moment,
    answer_key,
    applicable,
    followup_pack,
    moment_kind,
)
from formline.analyst.researcher import MAX_MODEL_CALLS, ResearchFailed, research
from formline.analyst.router import DECLINE, MAX_TEXT, player_clarification, route
from formline.analyst.sections import LABELS, facts_for
from formline.analyst.sections import label as section_label
from formline.analyst.store import MatchContext
from formline.analyst.templates import template_answer
from formline.analyst.tools import SECTION_FOR_TOOL
from formline.analyst.writer import answer_payload
from formline.schema.feed import FeedMessage


class AskError(ValueError):
    """The request does not name a moment of this match, or the question does not apply."""


@dataclass(frozen=True)
class AskRequest:
    moment: str  # e.g. "shot_outcome_evt_000412"
    seq: int  # feed sequence the comment was written at
    question: str
    player_id: str | None
    lang: str


def known_events(feed: list[FeedMessage], seq: int) -> dict[str, object]:
    """Events as known after the message with sequence `seq` (latest versions).

    Mirrors the Analyst writer, which ignores deletes (the demo feed has none)."""
    known: dict[str, object] = {}
    for msg in feed:
        if msg.sequence > seq:
            break
        if msg.event is not None:
            known[msg.event_id] = msg.event
    return known


def _moment(moment_id: str, seq: int, feed: list[FeedMessage], ctx: MatchContext,
            norm: Callable[[str], float | None] | None) -> tuple[Moment, dict[str, object]]:
    """The comment's moment as known at feed sequence `seq` (and the known events by id)."""
    parsed = moment_kind(moment_id)
    if parsed is None:
        raise AskError(f"unknown moment {moment_id!r}")
    kind, event_id = parsed
    known = known_events(feed, seq)
    event = known.get(event_id)
    if event is None:
        raise AskError(f"no event {event_id} in this match at sequence {seq}")
    events = sorted(known.values(), key=lambda e: (e.period, e.match_clock_ms))
    return Moment(kind, event, events, event.player_id, ctx.home, ctx.away, ctx.clubs,
                  ctx.players, norm), known


async def _answer(q: str, lang: str, m: Moment, known: Mapping[str, object], ctx: MatchContext,
                  runner: LLMRunner, precomputed: Mapping[str, dict]) -> dict:
    pid = m.player_id if q == "player_tonight" else None
    key = answer_key(m.id, q, pid, lang)
    if key in precomputed:
        return {**precomputed[key], "cached": True}
    if not applicable(q, m):
        raise AskError(f"{q!r} does not apply to this moment")
    pack = followup_pack(q, m)
    answer = await answer_verified(pack, lang, runner, ctx.league, (ctx.home, ctx.away))
    return {**answer_payload(q, lang, answer, pack, known), "cached": False}


async def answer_question(req: AskRequest, feed: list[FeedMessage], ctx: MatchContext,
                          runner: LLMRunner, precomputed: Mapping[str, dict],
                          norm: Callable[[str], float | None] | None = None) -> dict:
    if moment_kind(req.moment) is None:
        raise AskError(f"unknown moment {req.moment!r}")
    pid = req.player_id if req.question == "player_tonight" else None
    key = answer_key(req.moment, req.question, pid, req.lang)
    if key in precomputed:  # the demo's suggested questions: no replay, no model call
        return {**precomputed[key], "cached": True}
    m, known = _moment(req.moment, req.seq, feed, ctx, norm)
    if req.question == "player_tonight" and pid != m.player_id:
        raise AskError("player_tonight asks about the player of the moment")
    return await _answer(req.question, req.lang, m, known, ctx, runner, precomputed)


def moment_as_of(event_id: str, version: int, feed: list[FeedMessage], ctx: MatchContext,
                 norm: Callable[[str], float | None] | None) -> tuple[Moment, dict[str, object]]:
    """The match as known when the viewer received this event version: the feed replayed up
    to that message (the viewer names an event it has, never a clock)."""
    msg = next((m for m in feed if m.event_id == event_id and m.version == version), None)
    if msg is None or msg.event is None:
        raise AskError(f"no event {event_id} v{version} in this match")
    known = known_events(feed, msg.sequence)
    events = sorted(known.values(), key=lambda e: (e.period, e.match_clock_ms))
    event = known[event_id]
    return Moment("free", event, events, getattr(event, "player_id", None), ctx.home, ctx.away,
                  ctx.clubs, ctx.players, norm), known


log = logging.getLogger("formline.ask")

# Typed questions: one deadline for the whole request, and model calls kept back for the
# fallback Router (1 + a retry) and the Analyst (3 attempts) so they can always run.
DEADLINE_S = 25.0
RESEARCH_TIMEOUT_S = 12.0
FALLBACK_RESERVE = 2 + 3


def _steps(session, lang: str) -> list[dict]:
    """The Researcher's calls for the viewer: tool, ok, a short label."""
    out = []
    for st in session.steps:
        label = st["tool"]
        if st["ok"] and st["tool"] in SECTION_FOR_TOOL:
            sec = SECTION_FOR_TOOL[st["tool"]]
            pid, club = st["args"].get("player_id"), st["args"].get("club_id")
            player = None
            if pid:
                en, ja = session.ctx.league.players[pid]
                player = en.split()[-1] if lang == "en" else ja.split("・")[-1]
            label = LABELS[lang][sec].format(club=session.ctx.clubs.get(club, ""),
                                             player=player or "", n=st["args"].get("n", 3))
        out.append({"tool": st["tool"], "ok": st["ok"], "label": label})
    return out


def _template(pack, lang: str, ctx: MatchContext) -> Answer:
    """When the deadline leaves no time for the Analyst: what the facts say (always verifies)."""
    t = template_answer(pack, lang, role_names(pack, lang, ctx.league))
    return Answer(t["headline"], t["body"], "template", 0, "partial")


async def answer_free(event_id: str, version: int, text: str, lang: str,
                      feed: list[FeedMessage], ctx: MatchContext, runner: LLMRunner,
                      norm: Callable[[str], float | None] | None = None,
                      short_names: Mapping[str, str] | None = None,
                      use_research: bool = True) -> dict:
    """A typed question. The Researcher (a tool-using agent) gathers the facts it needs, in
    as many lookups as it takes within hard limits; if it fails, the one-shot Router picks
    sections instead (partial research is discarded). The Analyst answers the viewer's own
    question from those facts and the Verifier checks it (docs/plan-agentic-research.md).

    Returns {"retrieved": {sections, club_id, player_id, label} | None,
    "answer": {..., coverage} | None, "declined": message | None,
    "research": [{tool, ok, label}], "outcome": str}."""
    if not text.strip():
        raise AskError("empty question")
    m, known = moment_as_of(event_id, version, feed, ctx, norm)
    clarification = player_clarification(text[:MAX_TEXT], lang, m, short_names)
    if clarification:
        # Existing clients already display this message without treating it as an error.
        return {"retrieved": None, "answer": None, "declined": clarification, "research": [],
                "outcome": "clarify"}
    loop = asyncio.get_running_loop()
    start = loop.time()

    def left() -> float:
        return DEADLINE_S - (loop.time() - start)

    def done(outcome: str, steps: list, retrieved=None, answer=None, declined=None,
             analyst: Answer | None = None) -> dict:
        record = {"event": "ask_free", "outcome": outcome, "steps": len(steps),
                  "seconds": round(loop.time() - start, 2)}
        if analyst is not None:  # why answers were rejected, for diagnosis (never shown)
            record |= {"source": analyst.source, "attempts": analyst.attempts,
                       "rejections": list(analyst.rejections)}
        log.info(json.dumps(record, ensure_ascii=False))
        return {"retrieved": retrieved, "answer": answer, "declined": declined,
                "research": steps, "outcome": outcome}

    if runner.remaining < FALLBACK_RESERVE:
        return done("budget_exhausted", [], declined=DECLINE[lang])
    steps: list[dict] = []
    pack = retrieved = None
    outcome = "fallback_budget"
    allowance = min(MAX_MODEL_CALLS, runner.remaining - FALLBACK_RESERVE)
    if use_research and allowance >= 2:
        try:
            res = await asyncio.wait_for(
                research(text[:MAX_TEXT], lang, m, ctx, runner, dict(short_names or {}), norm,
                         allowance), RESEARCH_TIMEOUT_S)
            steps = _steps(res.session, lang)
            if res.cannot_answer:
                return done("cannot_answer", steps, declined=DECLINE[lang])
            pack = res.session.pack()
            lookups = list(res.session.lookups.values())
            retrieved = {"sections": [lk.section for lk in lookups],
                         "club_id": next((lk.args["club_id"] for lk in lookups
                                          if lk.args.get("club_id")), None),
                         "player_id": next((lk.args["player_id"] for lk in lookups
                                            if lk.args.get("player_id")), None),
                         "label": res.session.label(lang)}
            outcome = "answered"
        except TimeoutError:
            outcome = "fallback_timeout"
        except BudgetExceeded:
            outcome = "fallback_budget"
        except ResearchFailed as exc:
            outcome = exc.outcome
        except Exception:  # a framework or tool error: fall back, never fail
            log.exception("researcher failed")
            outcome = "fallback_error"
    if pack is None:  # the one-shot Router, from the reserved budget
        try:
            r = await asyncio.wait_for(
                route(text, lang, m, ctx.league.players, dict(short_names or {}), runner),
                max(1.0, left()))
        except TimeoutError:
            return done("timeout", steps, declined=DECLINE[lang])
        if not r.sections:
            return done(outcome if outcome != "answered" else "cannot_answer", steps,
                        declined=DECLINE[lang])
        pack = facts_for(r.sections, m, r.club_id, r.player_id, ctx.info, ctx.records,
                         ctx.player_seasons, norm, history=ctx.history, n=r.n)
        player = None
        if r.player_id:
            en, ja = ctx.league.players[r.player_id]
            player = en.split()[-1] if lang == "en" else ja.split("・")[-1]
        retrieved = {"sections": r.sections, "club_id": r.club_id, "player_id": r.player_id,
                     "label": section_label(r.sections, lang, ctx.clubs.get(r.club_id), player,
                                            r.n)}
    try:
        a = await asyncio.wait_for(
            answer_verified(pack, lang, runner, ctx.league, (ctx.home, ctx.away),
                            viewer_question=text[:MAX_TEXT]), max(2.0, left()))
    except TimeoutError:
        a = _template(pack, lang, ctx)
    if a.coverage == "none":
        return done("cannot_answer", steps, retrieved, declined=DECLINE[lang], analyst=a)
    answer = {**answer_payload("free", lang, a, pack, known), "coverage": a.coverage,
              "cached": False}
    return done(outcome, steps, retrieved, answer, analyst=a)
