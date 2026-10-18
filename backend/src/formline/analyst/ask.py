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

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from formline.agents.llm import LLMRunner
from formline.analyst.agent import answer_verified
from formline.analyst.followups import (
    Moment,
    answer_key,
    applicable,
    followup_pack,
    moment_kind,
)
from formline.analyst.router import DECLINE, MAX_TEXT, route
from formline.analyst.sections import facts_for
from formline.analyst.sections import label as section_label
from formline.analyst.store import MatchContext
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


async def answer_free(moment_id: str, seq: int, text: str, lang: str, feed: list[FeedMessage],
                      ctx: MatchContext, runner: LLMRunner,
                      norm: Callable[[str], float | None] | None = None,
                      short_names: Mapping[str, str] | None = None) -> dict:
    """A typed question, "RAG over computed facts": the Router retrieves 1–3 fact sections,
    the Analyst answers the viewer's own question from them (verified), or it is declined.

    Returns {"retrieved": {sections, club_id, player_id, label} | None,
    "answer": {..., coverage} | None, "declined": message | None}."""
    if not text.strip():
        raise AskError("empty question")
    m, known = _moment(moment_id, seq, feed, ctx, norm)
    r = await route(text, lang, m, ctx.league.players, dict(short_names or {}), runner)
    if not r.sections:
        return {"retrieved": None, "answer": None, "declined": DECLINE[lang]}
    pack = facts_for(r.sections, m, r.club_id, r.player_id)
    player = None
    if r.player_id:
        en, ja = ctx.league.players[r.player_id]
        player = en.split()[-1] if lang == "en" else ja.split("・")[-1]
    retrieved = {"sections": r.sections, "club_id": r.club_id, "player_id": r.player_id,
                 "label": section_label(r.sections, lang, ctx.clubs.get(r.club_id), player)}
    a = await answer_verified(pack, lang, runner, ctx.league, (ctx.home, ctx.away),
                              viewer_question=text[:MAX_TEXT])
    if a.coverage == "none":
        return {"retrieved": retrieved, "answer": None, "declined": DECLINE[lang]}
    answer = {**answer_payload("free", lang, a, pack, known), "coverage": a.coverage,
              "cached": False}
    return {"retrieved": retrieved, "answer": answer, "declined": None}
