"""Verify an Analyst answer against its facts pack (deterministic, no LLM).

Reuses the card verifier's wording checks (estimates, certainty, jargon, language) and
adds rules for answers that may name several players and both clubs:
- numbers   every number must appear in the facts (or the match score and minute);
- entities  only the players in the pack's roles, and only the two clubs of this match;
- structure headline and body present, within length limits, nothing else.
"""

import re
from dataclasses import dataclass

from formline.agents.verifier import (
    JAPANESE,
    KANA,
    NUMBER,
    SNAKE_CASE,
    Failure,
    LeagueNames,
    Verdict,
    VerifyContext,
    _check_certainty,
    normalize,
)
from formline.analyst.facts import FactsPack

LIMITS = {"en": {"headline": 70, "body": 260}, "ja": {"headline": 36, "body": 130}}
# Probability wording that needs an estimate marker. Unlike on cards, "chance" alone is not a
# trigger: in commentary "a good chance" usually means an opportunity, not a probability.
PROBABILITY = {"en": ("%", "percentile", "probability", "likelihood", "xg"),
               "ja": ("%", "パーセンタイル", "確率", "期待値")}
MARKERS = {"en": ("estimate", "est.", "model", "about", "around", "roughly", "~"),
           "ja": ("推定", "約", "モデル")}
# Club names have no official Japanese form, so the verifier can only check the spelling in
# FACTS. A Japanese rendering ("ノースゲート・ローバーズ", "北ゲート") could name any club unchecked,
# so the words of the league's club names in katakana are rejected.
JA_CLUB_WORDS = ("アスレチック", "アスレティック", "ローバーズ", "タウン", "ユナイテッド", "シティ",
                 "ケストレル", "ゲート", "ハーバーサイド", "エルダー", "ソーンム", "コラン")


@dataclass(frozen=True)
class AnswerContext:
    pack: FactsPack
    lang: str
    match_clubs: tuple[str, str]  # club ids


def _strings(value) -> list[str]:
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return [str(value)]


def allowed_numbers(pack: FactsPack) -> set[str]:
    nums = set()
    for s in _strings(pack.facts):
        nums |= set(NUMBER.findall(normalize(s)))
    # "3.0 m" in the facts may be written "3 m": the same number, not a new one
    return nums | {n[:-2] for n in nums if n.endswith(".0")}


def _forms(en: str, ja: str, lang: str) -> set[str]:
    return {en, en.split()[-1]} if lang == "en" else {ja, ja.split("・")[-1]}


def verify_answer(answer: dict, ctx: AnswerContext, league: LeagueNames) -> Verdict:
    failures: list[Failure] = []
    limits = LIMITS[ctx.lang]
    for key in answer:
        if key not in limits:
            failures.append(Failure("structure", f"unexpected key {key!r}: return only headline, body"))
    for key, limit in limits.items():
        value = answer.get(key)
        if not isinstance(value, str) or not value.strip():
            failures.append(Failure("structure", f"{key!r} is missing or empty"))
        elif len(value) > limit:
            failures.append(Failure("structure", f"{key!r} is {len(value)} characters; the limit is {limit}"))
    text = normalize(" ".join(str(answer.get(k, "")) for k in limits))

    allowed = allowed_numbers(ctx.pack)
    for m in NUMBER.finditer(text):
        if m.group(0) not in allowed:
            failures.append(Failure("numbers", f"number {m.group(0)} is not in FACTS; use only: "
                                               f"{', '.join(sorted(allowed, key=float)[:24])}"))

    own = set()
    for pid in ctx.pack.roles.values():
        if pid in league.players:
            own |= _forms(*league.players[pid], ctx.lang)
    for pid, (en, ja) in league.players.items():
        if pid in ctx.pack.roles.values():
            continue
        for form in _forms(en, ja, ctx.lang) - own:
            hit = re.search(rf"\b{re.escape(form)}\b", text) if ctx.lang == "en" else form in text
            if hit:
                failures.append(Failure("entities", f"names a player who is not in the facts ({form})"))
                break
    for cid, (name, short) in league.clubs.items():
        if cid in ctx.match_clubs:
            continue
        if re.search(rf"\b({re.escape(name)}|{re.escape(short)})\b", text):
            failures.append(Failure("entities", f"names a club not in this match ({name})"))

    vctx = VerifyContext("analyst_answer", ctx.lang, "casual")
    low = text.lower()
    if any(t in low for t in PROBABILITY[ctx.lang]) and not any(m in low for m in MARKERS[ctx.lang]):
        failures.append(Failure("estimates", "percentages and xG are model estimates; say so, e.g. "
                                             + ("（推定）" if ctx.lang == "ja" else "(model estimate)")))
    failures += _check_certainty(text, vctx)
    roles = [r for r in SNAKE_CASE.findall(text)] + [r for r in ctx.pack.roles if r in text]
    if roles:
        failures.append(Failure("jargon", f"internal labels or role placeholders shown ({', '.join(roles)}); "
                                          "use the player names from NAMES and plain words"))
    if ctx.lang == "ja" and any(w in text for w in JA_CLUB_WORDS):
        failures.append(Failure("entities", "write club names exactly as in FACTS (not in katakana "
                                            "or translated)"))
    if ctx.lang == "ja" and not JAPANESE.search(text):
        failures.append(Failure("language", "write in Japanese"))
    if ctx.lang == "en" and KANA.search(text):
        failures.append(Failure("language", "write in English only"))
    return Verdict(tuple(failures))
