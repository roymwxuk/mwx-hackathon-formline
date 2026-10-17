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

from formline.agents.catalog import LIMITS, TEMPLATE_FOR_INSIGHT, ordinal
from formline.agents.llm import LLMRunner
from formline.agents.selector import strip_fences
from formline.agents.template_narrator import Names, _pool_en, _pool_ja, narrate
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

# One good card per variant (for a different shot), to anchor style and length.
EXAMPLES = {
    ("en", "casual"): {"tag": "SHOT SPEED · VS HIS OWN NORM",
                       "headline": "Reyner — not his usual strike",
                       "sub": "84 km/h, about 8 km/h below his typical shot from outside the "
                              "box (estimate)."},
    ("en", "analyst"): {"tag": "SHOT SPEED · PERSONAL BASELINE",
                        "headline": "Reyner 84.1 km/h · Δ −8.2 vs baseline",
                        "sub": "Est. 21st percentile vs his shots from outside the box (n=5, "
                               "weight 0.69). Model estimates."},
    ("ja", "casual"): {"tag": "シュートスピード・本人比", "headline": "レイナー、いつもの威力がない",
                       "sub": "84 km/h。エリア外からのシュートの平均より約8 km/h遅い（推定）"},
    ("ja", "analyst"): {"tag": "シュートスピード・本人基準",
                        "headline": "レイナー 84.1 km/h・基準比 −8.2",
                        "sub": "エリア外からのシュートと比べ推定21パーセンタイル。n=5・重み0.69。"
                               "数値はモデルによる推定値です。"},
}

RULES = """You write one on-screen card for a live football broadcast.
Rules:
- Use ONLY the values and phrases in CARD_FACTS, written as given (e.g. "84 km/h", "44/100",
  "17%"). Never invent numbers, and never show scores or chances as decimals like 0.43.
- The headline must name the player exactly as given in PLAYER. Name no other player or club.
- Plain football language. Never use technical labels or field names.
- Percentiles, percentages and chances are model estimates: say so ("estimate", "est.", "about";
  in Japanese "推定" or "約").
- No certainty claims (no "will score", "definitely", 必ず, 確実).
- Describe the comparison with COMPARED_WITH, as given.
- Keep within LIMITS (characters). Write in the requested language.
Reply with JSON only: {"tag": "...", "headline": "...", "sub": "..."}"""


def instructions(lang: str, mode: str) -> str:
    example = json.dumps(EXAMPLES[(lang, mode)], ensure_ascii=False)
    return (f"{RULES}\nVoice: {VOICE[(lang, mode)]}\n"
            f"Example of a good card for a different shot (write a fresh card for the given "
            f"facts in this style; do not copy its numbers or wording): {example}")


WHAT = {
    "en": {"shot_speed_vs_norm": "shot speed compared with his own norm",
           "season_best": "his fastest shot of the season",
           "season_worst": "his slowest shot of the season",
           "placement_vs_norm": "how close to the corner he placed it (score out of 100), "
                                "compared with his own norm",
           "finish_vs_norm": "the chance this finish had of scoring, compared with his typical "
                             "finish"},
    "ja": {"shot_speed_vs_norm": "本人の平均と比べたシュートスピード",
           "season_best": "今季最速のシュート", "season_worst": "今季最も遅いシュート",
           "placement_vs_norm": "本人の平均と比べたコースの良さ（100点満点）",
           "finish_vs_norm": "本人の普段のフィニッシュと比べた得点確率"},
}
BODY = {"en": {"strong_foot": "strong foot", "weak_foot": "weaker foot", "head": "header"},
        "ja": {"strong_foot": "利き足", "weak_foot": "逆足", "head": "ヘディング"}}
PRESSURE = {"en": {"pressured": "under pressure", "open": "no defender close"},
            "ja": {"pressured": "プレッシャー下", "open": "フリー"}}
OUTCOME = {"en": {"goal": "goal", "saved": "saved", "off_target": "missed the target",
                  "post": "hit the post", "blocked": "blocked"},
           "ja": {"goal": "ゴール", "saved": "セーブされた", "off_target": "枠外",
                  "post": "ポストに当たった", "blocked": "ブロックされた"}}


def _fmt(metric: str, v: float) -> str:
    if metric == "shot_speed_kmh":
        return f"{round(v)} km/h"
    if metric == "placement":
        return f"{round(v * 100)}/100"
    return f"{round(v * 100)}%"


def viewer_facts(ins: Insight, lang: str, mode: str) -> dict:
    """The insight's facts phrased for viewers: no codes, no raw fractions."""
    f = ins.facts
    metric = f["metric"]
    below = ins.direction == "below"
    gap = abs(f["delta"])
    if metric == "shot_speed_kmh":
        gap_text = f"{round(gap)} km/h"
    else:
        gap_text = f"{round(gap * 100)} points" if metric == "placement" else f"{round(gap * 100)}%"
    if lang == "ja":
        gap_text = f"約{gap_text}{'低い' if below else '高い'}" if metric != "shot_speed_kmh" \
            else f"約{gap_text}{'遅い' if below else '速い'}"
        compared = f"{_pool_ja(f)}の平均"
        percentile = f"推定{ordinal(f['est_percentile'], 'ja')}"
        sample = f"同条件{f['sample_n']}本"
    else:
        gap_text = f"about {gap_text} {'below' if below else 'above'} his norm"
        compared = _pool_en(f)
        percentile = f"{ordinal(f['est_percentile'], 'en')} percentile (estimate)"
        sample = f"{f['sample_n']} similar shots"
    facts = {
        "WHAT": WHAT[lang][ins.type],
        "THIS_SHOT": _fmt(metric, f["value"]),
        "HIS_NORM": _fmt(metric, f["norm"]),
        "GAP": gap_text,
        "PERCENTILE": percentile,
        "COMPARED_WITH": compared,
        "SAMPLE": sample,
        "SHOT": {"body": BODY[lang].get(f["body_group"], ""),
                 "pressure": PRESSURE[lang][f["pressure"]],
                 "distance": f"{round(f['distance_m'])} m",
                 "result": OUTCOME[lang].get(f["outcome"], f["outcome"])},
    }
    if f.get("season_record") and f.get("season_sample_n"):
        n = f["season_sample_n"]
        facts["SEASON_RECORD"] = (f"{'beats' if f['season_record'] == 'best' else 'below'} all "
                                  f"{n} of his earlier shots of this kind this season"
                                  if lang == "en" else
                                  f"今季の同種のシュート{n}本を"
                                  f"{'すべて上回る' if f['season_record'] == 'best' else 'すべて下回る'}")
    if f["thin_sample"] or f["sample_n"] < 5:
        facts["SMALL_SAMPLE"] = "small sample" if lang == "en" else "サンプル少"
    if mode == "analyst":
        facts["SPEED_EXACT"] = f"{f['value']} km/h" if metric == "shot_speed_kmh" else None
        facts["DELTA_EXACT"] = f"{f['delta']:+.1f}" if metric == "shot_speed_kmh" else None
        facts["WEIGHT_ON_HIS_OWN_SHOTS"] = f"{f['weight_on_own_shots']:.2f}"
        facts["XG"] = f"{f['xg']:.2f}"
        if f.get("psxg") is not None:
            facts["PSXG"] = f"{f['psxg']:.2f}"
        facts = {k: v for k, v in facts.items() if v is not None}
    return facts


def request_payload(ins: Insight, lang: str, mode: str, names: Names,
                    feedback: str | None = None) -> dict:
    limits = LIMITS[lang]
    payload = {
        "language": lang,
        "audience_mode": mode,
        "PLAYER": names.ja if lang == "ja" else names.en,
        "direction": ins.direction,
        "CARD_FACTS": viewer_facts(ins, lang, mode),
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
