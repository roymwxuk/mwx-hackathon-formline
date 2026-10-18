"""Answer a follow-up question a viewer clicked (`POST /matches/{id}/ask`).

The request names the comment's moment and the feed sequence it was written at (the
comment's `ask` field), the question and the language. A precomputed answer is served as
is; otherwise the events known at that sequence are replayed from the feed, the question is
checked against the catalog (it must apply to that moment), and the Analyst agent answers
it live from the facts pack, verified, under the runner's cache and call budget.
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


async def answer_question(req: AskRequest, feed: list[FeedMessage], ctx: MatchContext,
                          runner: LLMRunner, precomputed: Mapping[str, dict],
                          norm: Callable[[str], float | None] | None = None) -> dict:
    parsed = moment_kind(req.moment)
    if parsed is None:
        raise AskError(f"unknown moment {req.moment!r}")
    pid = req.player_id if req.question == "player_tonight" else None
    key = answer_key(req.moment, req.question, pid, req.lang)
    if key in precomputed:
        return {**precomputed[key], "cached": True}

    kind, event_id = parsed
    known = known_events(feed, req.seq)
    event = known.get(event_id)
    if event is None:
        raise AskError(f"no event {event_id} in this match at sequence {req.seq}")
    if req.question == "player_tonight" and pid != event.player_id:
        raise AskError("player_tonight asks about the player of the moment")
    events = sorted(known.values(), key=lambda e: (e.period, e.match_clock_ms))
    m = Moment(kind, event, events, event.player_id, ctx.home, ctx.away, ctx.clubs,
               ctx.players, norm)
    if not applicable(req.question, m):
        raise AskError(f"{req.question!r} does not apply to this moment")
    pack = followup_pack(req.question, m)
    answer = await answer_verified(pack, req.lang, runner, ctx.league, (ctx.home, ctx.away))
    return {**answer_payload(req.question, req.lang, answer, pack, known), "cached": False}
