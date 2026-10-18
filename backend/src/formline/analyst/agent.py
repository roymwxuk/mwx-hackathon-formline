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

MAX_ATTEMPTS = 3

QUESTIONS = {
    "en": {"shot_outcome": "Why did this shot end as it did?", "corner": "What came of this corner?",
           "card": "Why was this player booked?", "var": "Why was the goal ruled out?"},
    "ja": {"shot_outcome": "このシュートはなぜこの結果になったのか？", "corner": "このコーナーキックはどうなったか？",
           "card": "なぜこの選手にカードが出たのか？", "var": "なぜゴールは取り消されたのか？"},
}

INSTRUCTIONS = """You are the match analyst for a live football broadcast (synthetic match data).
Answer QUESTION about one moment using only FACTS. Name players only with the names in NAMES
(FACTS refer to them by role, e.g. SHOOTER). Explain the one or two facts that matter most
(e.g. distance, pressure, the goalkeeper, chance quality, placement); do not list every fact.
Chances and percentages are model estimates: say so. Never state certainty. If FACTS say
something is not in the data, do not guess it. Write in LANGUAGE ({lang}) for a general
audience, warm but precise, within LIMITS.
Reply with JSON only: {{"headline": "...", "body": "..."}}"""


@dataclass(frozen=True)
class Answer:
    headline: str
    body: str
    source: str  # "llm" or "template"
    attempts: int


def role_names(pack: FactsPack, lang: str, league: LeagueNames) -> dict[str, str]:
    out = {}
    for role, pid in pack.roles.items():
        en, ja = league.players.get(pid, (pid, pid))
        out[role] = en.split()[-1] if lang == "en" else ja.split("・")[-1]
    return out


def payload(pack: FactsPack, lang: str, names: dict[str, str], feedback: str | None) -> dict:
    p = {"LANGUAGE": lang, "QUESTION": QUESTIONS[lang][pack.question],
         "QUESTION_ID": pack.question, "NAMES": names,
         "FACTS": pack.facts, "LIMITS": LIMITS[lang]}
    if feedback:
        p["FIX_THESE_PROBLEMS"] = feedback
    return p


async def answer_verified(pack: FactsPack, lang: str, runner: LLMRunner, league: LeagueNames,
                          match_clubs: tuple[str, str]) -> Answer:
    names = role_names(pack, lang, league)
    ctx = AnswerContext(pack, lang, match_clubs)
    feedback: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text = await runner.complete("analyst", INSTRUCTIONS.format(lang=lang),
                                         json.dumps(payload(pack, lang, names, feedback),
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
            return Answer(answer["headline"], answer["body"], "llm", attempt)
        feedback = verdict.feedback()
    t = template_answer(pack, lang, names)
    assert verify_answer(t, ctx, league).ok, f"template answer must verify: {verify_answer(t, ctx, league).feedback()}"
    return Answer(t["headline"], t["body"], "template", MAX_ATTEMPTS)
