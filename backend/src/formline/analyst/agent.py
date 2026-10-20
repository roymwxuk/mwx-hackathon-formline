"""The Analyst agent: explains a key moment from its facts pack, verified, with evidence.

Same pattern as the Narrator (agents/narrator.py): one JSON contract, the verifier's
feedback on a retry, a template answer after MAX_ATTEMPTS, so an answer is never blocked
and never wrong.
"""

import json
from dataclasses import dataclass

from formline.agents.llm import LLMRunner
from formline.agents.selector import strip_fences
from formline.agents.verifier import LeagueNames
from formline.analyst.facts import FactsPack
from formline.analyst.templates import template_answer
from formline.analyst.verify import LIMITS, AnswerContext, verify_answer
from formline.prompts import load

MAX_ATTEMPTS = 3

QUESTIONS = {
    "en": {"shot_outcome": "Why did this shot end as it did?", "corner": "What came of this corner?",
           "card": "Why was this player booked?", "var": "Why was the goal ruled out?",
           # follow-up questions a viewer asks (analyst/followups.py)
           "situation": "What is happening in the match so far?",
           "score": "Why is the score what it is?",
           "player_tonight": "How is PLAYER doing tonight, compared with his own season norm?",
           "team_stats": "How do the two teams compare so far?"},
    "ja": {"shot_outcome": "このシュートはなぜこの結果になったのか？", "corner": "このコーナーキックはどうなったか？",
           "card": "なぜこの選手にカードが出たのか？", "var": "なぜゴールは取り消されたのか？",
           "situation": "ここまでの試合の流れは？",
           "score": "なぜこのスコアなのか？",
           "player_tonight": "今夜のPLAYERの出来は？本人の今季平均と比べてどうか？",
           "team_stats": "ここまでの両チームの比較は？"},
}

PROMPT = load("analyst")  # prompts/analyst.md; "{lang}" is filled in per call
FREE_PROMPT = load("analyst_free")  # prompts/analyst_free.md: typed questions


@dataclass(frozen=True)
class Answer:
    headline: str
    body: str
    source: str  # "llm" or "template"
    attempts: int
    coverage: str = "full"  # typed questions: full | partial | none
    rejections: tuple[str, ...] = ()  # why each failed attempt failed (logged, not shown)


def role_names(pack: FactsPack, lang: str, league: LeagueNames) -> dict[str, str]:
    out = {}
    for role, pid in pack.roles.items():
        en, ja = league.players.get(pid, (pid, pid))
        out[role] = en.split()[-1] if lang == "en" else ja.split("・")[-1]
    return out


def payload(pack: FactsPack, lang: str, names: dict[str, str], feedback: str | None,
            viewer_question: str | None = None) -> dict:
    if viewer_question is not None:  # a typed question, answered from retrieved sections
        p = {"LANGUAGE": lang, "VIEWER_QUESTION": viewer_question, "NAMES": names,
             "FACTS": pack.facts, "MAX_CHARACTERS": LIMITS[lang]}
    else:
        p = {"LANGUAGE": lang, "QUESTION": QUESTIONS[lang][pack.question],
             "QUESTION_ID": pack.question, "NAMES": names,
             "FACTS": pack.facts, "MAX_CHARACTERS": LIMITS[lang]}
    if feedback:
        p["FIX_THESE_PROBLEMS"] = feedback
    return p


async def answer_verified(pack: FactsPack, lang: str, runner: LLMRunner, league: LeagueNames,
                          match_clubs: tuple[str, str],
                          viewer_question: str | None = None,
                          scorers_tonight: frozenset[str] | None = None) -> Answer:
    """`viewer_question` set: a typed question, answered freely from `pack` (the retrieved
    sections) with a coverage verdict; otherwise the catalog question of the pack."""
    names = role_names(pack, lang, league)
    free = viewer_question is not None
    ctx = AnswerContext(pack, lang, match_clubs, free=free, scorers_tonight=scorers_tonight)
    prompt = (FREE_PROMPT if free else PROMPT).text.replace("{lang}", lang)
    feedback: str | None = None
    rejections: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if feedback:
            rejections.append(feedback)
        try:
            text = await runner.complete("analyst", prompt,
                                         json.dumps(payload(pack, lang, names, feedback,
                                                            viewer_question),
                                                    ensure_ascii=False),
                                         use_cache=feedback is None)
            answer = json.loads(strip_fences(text))
            if not isinstance(answer, dict):
                raise TypeError("not a JSON object")
        except Exception as exc:  # noqa: BLE001 - bad JSON, timeouts, budget: retry, then template
            feedback = f"- [format] {exc}; reply with the JSON object only"
            continue
        verdict = verify_answer(answer, ctx, league)
        if verdict.ok:
            return Answer(answer["headline"], answer["body"], "llm", attempt,
                          answer.get("coverage", "full"), tuple(rejections))
        feedback = verdict.feedback()
    rejections.append(feedback)
    t = template_answer(pack, lang, names)
    assert verify_answer(t, ctx, league).ok, f"template answer must verify: {verify_answer(t, ctx, league).feedback()}"
    # a typed question's template only lists what the data shows: a partial answer at best
    return Answer(t["headline"], t["body"], "template", MAX_ATTEMPTS,
                  "partial" if free else "full", tuple(rejections))
