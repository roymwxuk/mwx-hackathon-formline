"""The Question Router: retrieves the facts that answer a question the viewer typed.

"RAG over computed facts": the model picks 1–3 fact sections (`analyst/sections.py`) and,
where a section needs one, the club or the player; code computes those sections from the
events. Code checks the reply (known section ids, a club of this match, a player who has
shot), retries once with the problem, then declines. The Analyst then answers the viewer's
own question from only those facts, and the verifier checks every number and name.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from formline.agents.llm import LLMRunner
from formline.agents.selector import strip_fences
from formline.analyst.followups import Moment
from formline.analyst.sections import MAX_SECTIONS, SECTIONS
from formline.prompts import load

MAX_TEXT = 200
MAX_ATTEMPTS = 2

PROMPT = load("router")  # prompts/router.md
INSTRUCTIONS = PROMPT.text


@dataclass(frozen=True)
class Route:
    sections: list[str]  # empty: cannot answer
    club_id: str | None
    player_id: str | None
    source: str  # "llm" or "rule" (declined after failed attempts)
    attempts: int


def shooters(m: Moment) -> list[str]:
    """Players who have taken a shot so far, in order of first shot."""
    seen: list[str] = []
    for s in m.shots:
        if s.player_id not in seen:
            seen.append(s.player_id)
    return seen


def check_route(reply: object, m: Moment) -> str | None:
    """None if the reply is a valid route, else the problem (fed back on the retry)."""
    if not isinstance(reply, dict):
        return 'reply with {"sections": [...], "club_id": ..., "player_id": ...} only'
    if reply.get("cannot_answer") is True:
        return None
    secs = reply.get("sections")
    if not isinstance(secs, list) or not 1 <= len(secs) <= MAX_SECTIONS:
        return f"sections must be a list of 1 to {MAX_SECTIONS} ids, or reply cannot_answer"
    unknown = [s for s in secs if s not in SECTIONS]
    if unknown or len(set(secs)) != len(secs):
        return f"use each id at most once, only from {list(SECTIONS)}"
    if "team_tonight" in secs and reply.get("club_id") not in (m.home, m.away):
        return f"team_tonight needs club_id {m.home} or {m.away}"
    if "player_tonight" in secs and reply.get("player_id") not in shooters(m):
        return ("player_tonight needs a player_id from PLAYERS with has_shot true, got "
                f"{reply.get('player_id')!r}")
    if "player_info" in secs and reply.get("player_id") not in squad(m):
        return f"player_info needs a player_id from PLAYERS, got {reply.get('player_id')!r}"
    if "player_info" in secs and "player_tonight" in secs:
        return "use player_info or player_tonight, not both"
    return None


def squad(m: Moment) -> list[str]:
    """Every player of the two clubs in this match."""
    return [pid for pid, p in m.players.items() if p.club_id in (m.home, m.away)]


def player_clarification(text: str, lang: str, m: Moment,
                         short_names: Mapping[str, str] | None = None) -> str | None:
    """Ask before routing a shared first name/surname; no model may guess the identity.

    Explicit full names and a uniquely named club disambiguate. Only match squads count.
    English names use word boundaries so e.g. Ito never matches a piece of another word.
    """
    def mentioned(name: str, source: str) -> bool:
        return bool(re.search(rf"(?<!\w){re.escape(name.casefold())}(?!\w)", source))

    source = text.casefold()
    ids = squad(m)
    # Remove full names first: their individual components must not trigger ambiguity.
    for pid in ids:
        p = m.players[pid]
        for name in (p.display_name, p.display_name_ja):
            if mentioned(name, source) or (re.search(r"[\u3040-\u30ff]", name)
                                            and name.casefold() in source):
                source = source.replace(name.casefold(), " ")
    clubs = [cid for cid in (m.home, m.away)
             if any(mentioned(alias, text.casefold())
                    for alias in (m.clubs[cid], m.clubs[cid].split()[0],
                                  (short_names or {}).get(cid, "")) if alias)]
    if len(clubs) == 1:
        ids = [pid for pid in ids if m.players[pid].club_id == clubs[0]]
    groups: dict[str, list[str]] = {}
    for pid in ids:
        p = m.players[pid]
        for token in set(p.display_name.split() + p.display_name_ja.split("・")):
            hit = token in source if re.search(r"[\u3040-\u30ff]", token) else mentioned(token, source)
            if hit:
                groups.setdefault(token.casefold(), []).append(pid)
    for candidates in groups.values():
        if len(candidates) < 2:
            continue
        choices = "; ".join(
            f"{m.players[pid].display_name_ja if lang == 'ja' else m.players[pid].display_name} "
            f"({m.clubs[m.players[pid].club_id]}, #{m.players[pid].shirt_number})"
            for pid in candidates)
        if lang == "ja":
            return f"どの選手ですか？ {choices}。フルネームまたはクラブ名を添えて質問してください。"
        return f"Which player do you mean: {choices}? Please ask again using the full name or club."
    return None


async def route(text: str, lang: str, m: Moment, names: dict[str, tuple[str, str]],
                short_names: dict[str, str], runner: LLMRunner) -> Route:
    """The sections (and their subject) that answer `text` at moment `m`, or none."""
    shot = set(shooters(m))
    players = [{"id": pid, "name": names[pid][0], "name_ja": names[pid][1],
                "club": m.clubs[m.players[pid].club_id], "has_shot": pid in shot}
               for pid in squad(m)]
    clubs = [{"id": c, "name": m.clubs[c], "short_name": short_names.get(c, "")}
             for c in (m.home, m.away)]
    payload = {"VIEWER_TEXT": text[:MAX_TEXT], "LANGUAGE": lang, "SECTIONS": SECTIONS,
               "CLUBS": clubs, "PLAYERS": players}
    feedback = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if feedback:
            payload["FIX_THIS_PROBLEM"] = feedback
        try:
            out = await runner.complete("router", INSTRUCTIONS,
                                        json.dumps(payload, ensure_ascii=False),
                                        use_cache=feedback is None)
            reply = json.loads(strip_fences(out))
        except Exception as exc:  # noqa: BLE001 - bad JSON, timeouts, budget: retry, then decline
            feedback = f"{exc}; reply with the JSON object only"
            continue
        feedback = check_route(reply, m)
        if feedback is None:
            if reply.get("cannot_answer") is True:
                return Route([], None, None, "llm", attempt)
            secs = reply["sections"]
            needs_player = "player_tonight" in secs or "player_info" in secs
            return Route(secs, reply.get("club_id") if "team_tonight" in secs else None,
                         reply.get("player_id") if needs_player else None, "llm", attempt)
    return Route([], None, None, "rule", MAX_ATTEMPTS)


DECLINE = {
    "en": "I can only answer from this match's data: the fixture, venue, weather, crowd and "
          "referee, goals, shots and "
          "chances, a team or a player (profile, season, tonight), fouls and cards, corners, the "
          "last 10 minutes, and both clubs' season so far.",
    "ja": "答えられるのはこの試合のデータだけです：試合情報（会場・天気・観客・審判）、ゴール、シュートと決定機、チームや"
          "選手（プロフィール・今季・今夜）、ファウルとカード、コーナー、直近10分、両チームの今季成績。",
}
