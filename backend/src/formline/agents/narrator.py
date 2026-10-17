"""Narrator: writes a card's free text for one language and audience mode.

The model sees only the insight's facts (already rounded for display), the player's
name, the comparison actually used and the length limits, and must answer with JSON
`{"tag", "headline", "sub"}`. `bars` and `rows` are not its job: the composer builds
them from facts.

`narrate_verified()` is the recovery loop: verify, retry with the verifier's feedback,
and after MAX_ATTEMPTS fall back to the deterministic template narrator, which always
passes. Every result records how it was produced.
"""

import json
from dataclasses import dataclass

from formline.agents.catalog import LIMITS, TEMPLATE_FOR_INSIGHT
from formline.agents.llm import LLMRunner
from formline.agents.selector import strip_fences
from formline.agents.template_narrator import Names, narrate
from formline.agents.verifier import LeagueNames, Verdict, VerifyContext, verify
from formline.engine.insights import Insight

MAX_ATTEMPTS = 3  # first try + 2 retries with feedback

VOICE = {
    ("en", "casual"): "Casual fan, English. Short, vivid, plain words; one idea per card.",
    ("en", "analyst"): "Analyst, English. Dense and precise: lead with the number and the gap "
                       "to his baseline; mention the comparison and sample.",
    ("ja", "casual"): "カジュアルなファン向け、日本語。短く、わかりやすく、印象的に。",
    ("ja", "analyst"): "アナリスト向け、日本語。数値と本人基準との差を先に。比較対象とサンプル数にも触れる。",
}

RULES = """You write one on-screen card for a live football broadcast.
Rules:
- Use ONLY numbers that appear in FACTS (you may round them as shown). Never invent numbers.
- Name only the given player. Do not mention clubs or other players.
- Percentiles, percentages and chances are model estimates: say so ("estimate", "est.", "about";
  in Japanese "推定" or "約").
- No certainty claims (no "will score", "definitely", 必ず, 確実).
- Describe the comparison honestly using COMPARISON (say "from this spot" only if it says so).
- Keep within LIMITS (characters). Write in the requested language.
Reply with JSON only: {"tag": "...", "headline": "...", "sub": "..."}"""


def instructions(lang: str, mode: str) -> str:
    return f"{RULES}\nVoice: {VOICE[(lang, mode)]}"


def request_payload(ins: Insight, lang: str, mode: str, names: Names,
                    feedback: str | None = None) -> dict:
    f = ins.facts
    limits = LIMITS[lang]
    payload = {
        "language": lang,
        "audience_mode": mode,
        "player": names.ja if lang == "ja" else names.en,
        "insight_type": ins.type,
        "direction": ins.direction,
        "confidence": ins.confidence,
        "COMPARISON": f.get("comparison_level"),
        "FACTS": {k: v for k, v in f.items()
                  if k not in ("comparison", "comparison_level", "metric")},
        "LIMITS": {"tag": limits.tag, "headline": limits.headline, "sub": limits.sub},
    }
    if feedback:
        payload["FIX_THESE_PROBLEMS"] = feedback
    return payload


class NarrationParseError(ValueError):
    pass


def parse_slots(text: str) -> dict:
    try:
        data = json.loads(strip_fences(text))
    except (json.JSONDecodeError, TypeError) as exc:
        raise NarrationParseError("reply was not valid JSON") from exc
    if not isinstance(data, dict):
        raise NarrationParseError("reply was not a JSON object")
    return data


@dataclass(frozen=True)
class Narration:
    slots: dict  # tag, headline, sub
    source: str  # "llm" or "template"
    attempts: int  # model attempts made (0 when no model call was needed)
    failures: tuple[str, ...]  # verifier feedback from rejected attempts


async def narrate_once(ins: Insight, lang: str, mode: str, names: Names, runner: LLMRunner,
                       feedback: str | None = None) -> dict:
    payload = request_payload(ins, lang, mode, names, feedback)
    text = await runner.complete("narrator", instructions(lang, mode),
                                 json.dumps(payload, ensure_ascii=False),
                                 use_cache=feedback is None)
    return parse_slots(text)


async def narrate_verified(ins: Insight, lang: str, mode: str, names: Names, runner: LLMRunner,
                           league: LeagueNames) -> Narration:
    ctx = VerifyContext(TEMPLATE_FOR_INSIGHT[ins.type], lang, mode, ins.facts, ins.player_id)
    feedback: str | None = None
    failures: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            slots = await narrate_once(ins, lang, mode, names, runner, feedback)
            verdict = verify(slots, ctx, league)
        except NarrationParseError as exc:
            verdict = None
            feedback = f"- [format] {exc}; reply with the JSON object only"
        if verdict is not None:
            if verdict.ok:
                return Narration({k: slots[k] for k in ("tag", "headline", "sub")}, "llm",
                                 attempt, tuple(failures))
            feedback = verdict.feedback()
        failures.append(feedback)
    template = vars(narrate(ins, lang, mode, names))
    assert verify(template, ctx, league).ok, "template narration must always verify"
    return Narration(template, "template", MAX_ATTEMPTS, tuple(failures))


def verdict_for(slots: dict, ins: Insight, lang: str, mode: str, league: LeagueNames) -> Verdict:
    ctx = VerifyContext(TEMPLATE_FOR_INSIGHT[ins.type], lang, mode, ins.facts, ins.player_id)
    return verify(slots, ctx, league)
