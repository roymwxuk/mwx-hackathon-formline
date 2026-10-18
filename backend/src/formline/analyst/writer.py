"""Analyst writer: proactive comments from a feed, in arrival order (live or precompute).

Fires on every shot (when it arrives), every corner (when its sequence ends: a shot by the
taking team, the defence winning the ball, or 15 s), and every card. A shot revised from a
goal to no goal (the VAR overturn) withdraws that goal's comments and adds a VAR comment;
lineage is the shot's event id, as for the cards.
"""

from collections.abc import Mapping
from datetime import datetime

from formline.agents.llm import LLMRunner
from formline.agents.verifier import LeagueNames
from formline.analyst.agent import answer_verified
from formline.analyst.facts import (
    CORNER_WINDOW_MS,
    ON_BALL,
    FactsPack,
    card_pack,
    corner_pack,
    minute,
    shot_pack,
    var_pack,
)
from formline.schema.feed import FeedMessage

LANGS = ("en", "ja")


class AnalystWriter:
    def __init__(self, runner: LLMRunner, league: LeagueNames, players: Mapping,
                 clubs: Mapping[str, str], home: str, away: str):
        self.runner, self.league, self.players = runner, league, players
        self.clubs, self.home, self.away = clubs, home, away
        self.events: dict[str, object] = {}
        self.corner = None  # (corner pass, on-ball events after it)
        self.card = None  # a card waiting for its foul (the feed may send the card first)
        self.shown: dict[str, list[dict]] = {}  # shot event id -> its comments
        self.clock: tuple[int, int] = (1, 0)
        self.summary = {"comments": 0, "llm": 0, "template": 0, "retracted": 0}

    def _sorted(self) -> list:
        return sorted(self.events.values(), key=lambda e: (e.period, e.match_clock_ms))

    async def on_message(self, msg: FeedMessage) -> list[dict]:
        if msg.event is None:
            return []
        e = msg.event
        before = self.events.get(e.event_id)
        self.events[e.event_id] = e
        self.clock = max(self.clock, (e.period, e.match_clock_ms))
        out: list[dict] = []
        if msg.op == "update" and before is not None:
            if e.type == "shot" and before.outcome == "goal" and e.outcome != "goal":
                out += self._withdraw(e.event_id)
                out += await self._comment(var_pack(before, e, self._sorted(), self.clubs,
                                                    self.home, self.away), e.player_id)
            return out
        if self.card is not None:
            out += await self._card_comment(e if e.type == "foul_committed" else None)
        if self.corner is not None:
            out += await self._advance_corner(e)
        if e.type == "shot":
            pack = shot_pack(e, self._sorted(), self.players, self.clubs, self.home, self.away)
            comments = await self._comment(pack, e.player_id)
            self.shown[e.event_id] = comments
            out += comments
        elif e.type == "card":
            self.card = e
            if self._foul_for(e) is not None:  # its foul already arrived
                out += await self._card_comment(None)
        elif e.type == "pass" and getattr(e, "pass_type", None) == "corner":
            self.corner = (e, [])
        return out

    def _foul_for(self, card):
        return next((f for f in self.events.values() if f.type == "foul_committed"
                     and f.player_id == card.player_id
                     and f.match_clock_ms == card.match_clock_ms), None)

    async def _card_comment(self, _arrived) -> list[dict]:
        """Comment on the waiting card once its foul is known (or the next message came)."""
        card, self.card = self.card, None
        pack = card_pack(card, self._foul_for(card), self._sorted(), self.clubs)
        return await self._comment(pack, card.player_id)

    async def flush(self) -> list[dict]:
        out = await self._card_comment(None) if self.card is not None else []
        if self.corner is None:
            return out
        corner, after = self.corner
        self.corner = None
        return out + await self._comment(corner_pack(corner, after, self._sorted(), self.clubs),
                                         corner.player_id)

    async def _advance_corner(self, e) -> list[dict]:
        corner, after = self.corner
        late = (e.period, e.match_clock_ms) > (corner.period, corner.match_clock_ms + CORNER_WINDOW_MS)
        if e.type in ON_BALL and e.event_id != corner.event_id and not late:
            after.append(e)
        resolved = late or (e.type == "shot" and e.team_id == corner.team_id) or (
            e.type in ON_BALL and e.team_id != corner.team_id)
        if not resolved:
            return []
        self.corner = None
        pack = corner_pack(corner, after, self._sorted(), self.clubs)
        pack.facts["minute"] = minute(corner)
        return await self._comment(pack, corner.player_id, at_ms=after[-1].match_clock_ms
                                   if after else corner.match_clock_ms)

    async def _comment(self, pack: FactsPack, player_id: str | None,
                       at_ms: int | None = None) -> list[dict]:
        out = []
        for lang in LANGS:
            a = await answer_verified(pack, lang, self.runner, self.league, (self.home, self.away))
            self.summary["comments"] += 1
            self.summary[a.source] += 1
            out.append({
                "comment_id": f"cmt_{pack.question}_{pack.moment_id}_{lang}",
                "op": "show", "supersedes_comment_id": None, "question": pack.question,
                "period": pack.event.period,
                "match_clock_ms": at_ms if at_ms is not None else pack.match_clock_ms,
                "lang": lang, "headline": a.headline, "body": a.body, "player_id": player_id,
                "evidence": [self._evidence(eid) for eid in pack.source_event_ids],
                "verified": True, "source": a.source,
            })
        return out

    def _evidence(self, event_id: str) -> dict:
        e = self.events.get(event_id)
        return {"event_id": event_id, "minute": minute(e) if e else "", "type": e.type if e else ""}

    def _withdraw(self, shot_id: str) -> list[dict]:
        out = []
        for c in self.shown.pop(shot_id, []):
            out.append({**c, "comment_id": f"{c['comment_id']}_retract", "op": "retract",
                        "supersedes_comment_id": c["comment_id"], "match_clock_ms": self.clock[1],
                        "headline": "", "body": ""})
            self.summary["retracted"] += 1
        return out


async def write_comments(feed: list[FeedMessage], writer: AnalystWriter) -> list[tuple[datetime, dict]]:
    """All comments for a feed, timed at the message that produced them."""
    rows: list[tuple[datetime, dict]] = []
    for msg in feed:
        for c in await writer.on_message(msg):
            rows.append((msg.emitted_at, c))
    last = feed[-1].emitted_at if feed else None
    for c in await writer.flush():
        rows.append((last, c))
    return rows
