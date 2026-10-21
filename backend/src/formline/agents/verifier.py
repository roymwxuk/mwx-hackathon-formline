"""Verifier: reject any card text that states something the engine didn't compute.

Deterministic (no LLM), so its catch rate can be measured (task 4). It checks free
text only (`tag`, `headline`, `sub`); `bars` and `rows` are built from facts by the
catalog and are correct by construction.

Checks:
1. numbers    every number must be derivable from the insight's facts (display rounding)
2. entities   only the insight's player may be named; no other player or club
3. estimates  percentages, percentiles and chances must carry an estimate marker
4. certainty  no certainty claims ("will score", "definitely", 必ず, 確実)
5. language   JA text is Japanese; EN text has no kana
6. structure  required slots present, within length limits, no unexpected keys; the headline
              names the insight's player
7. jargon     no internal labels (snake_case codes, "body group", 強足 …), and no raw 0–1
              fractions where viewers expect a score or a percentage

Failure details are written to be fed back to the narrator as retry instructions.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from formline.agents.catalog import LIMITS, TEMPLATES

TEXT_SLOTS = ("tag", "headline", "sub")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
KANA = re.compile(r"[぀-ヿ]")
JAPANESE = re.compile(r"[぀-ヿ一-鿿]")

ESTIMATE_TRIGGERS = {
    "en": ("%", "percentile", "pct", "chance", "probability", "likelihood"),
    "ja": ("%", "パーセンタイル", "確率", "可能性"),
}
ESTIMATE_MARKERS = {
    "en": ("estimate", "est.", "model", "about", "around", "roughly", "~"),
    "ja": ("推定", "約", "モデル"),
}
JARGON = {
    "en": ("body group", "zone body", "area body", "box central", "outside central",
           "open pressure", "pressure bucket", "comparison level", "est percentile"),
    "ja": ("強足", "強い足", "頭部", "体の向き", "ボディグループ", "ゾーンボディ"),
}
SNAKE_CASE = re.compile(r"\b[a-z]+_[a-z_]+\b")
FRACTION = re.compile(r"(?<![\d.])0\.\d+")

CERTAINTY = {
    "en": ("will score", "definitely", "certainly", "guaranteed", "100% chance", "no doubt",
           "always scores", "sure to"),
    "ja": ("必ず", "確実", "間違いなく", "絶対"),
}
# A denial of certainty must sit right before the claim: "no one can say he will score",
# "there is no guarantee Okafor will score", "it isn't guaranteed". A bare negation elsewhere
# ("Ito has not been tested and Okafor will definitely score", "nobody can deny he will
# score") is not a denial.
DENIAL = re.compile(
    r"(?:\b(?:no ?one|nobody)\s+(?:(?:can|could|will|would)\s+)?"
    r"(?:says?|knows?|tells?|predicts?|promises?|guarantees?)"
    r"|\b(?:can't|cannot|can not|couldn't|could not|don't|do not|doesn't|does not|won't|will not)"
    r"\s+(?:say|know|tell|predict|promise|guarantee)"
    r"|\bno\s+(?:guarantee|certainty|telling|way of knowing)"
    r"|\bnot\s+(?:certain|sure|clear)|\b(?:unclear|uncertain))"
    r"(?:\s+(?:if|whether|that))?(?:\s+[\w'’-]+){0,3}\s+$"
    # "no guaranteed scorer", "cannot be guaranteed", "no player can be guaranteed"
    r"|(?:\bnot|\bno|\bnever|n't|\bcannot|\bno\s+[\w'’-]+\s+(?:can|could|will|would|is|are))"
    r"\s+(?:be\s+)?$")
CLAUSE_BREAK = re.compile(r"[.;:!?,]|\b(?:and|but|so|yet|while|because|though|although)\b")


@dataclass(frozen=True)
class Failure:
    check: str
    detail: str


@dataclass(frozen=True)
class Verdict:
    failures: tuple[Failure, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures

    def feedback(self) -> str:
        """Retry instructions for the narrator."""
        return "\n".join(f"- [{f.check}] {f.detail}" for f in self.failures)


@dataclass(frozen=True)
class LeagueNames:
    """Every player and club name the verifier must police."""

    players: dict[str, tuple[str, str]]  # player_id -> (EN display name, JA display name)
    clubs: dict[str, tuple[str, str]]  # club_id -> (name, short name)
    player_club: dict[str, str]  # player_id -> club_id


@dataclass(frozen=True)
class VerifyContext:
    template_id: str
    lang: str
    mode: str
    facts: dict = field(default_factory=dict)
    player_id: str | None = None
    extra_numbers: frozenset[str] = frozenset()  # e.g. banner counts


# ---------- helpers ----------

def normalize(text: str) -> str:
    """Full-width digits and signs to ASCII; Unicode minus to '-'."""
    return unicodedata.normalize("NFKC", text).replace("−", "-")


def _forms(v: float) -> set[str]:
    out = set()
    for x in (v, abs(v)):
        out |= {str(round(x)), f"{x:.1f}", f"{x:.2f}", str(x)}
    return out


def _num(facts: dict, key: str) -> float | None:
    v = facts.get(key)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _union(facts: dict, keys: tuple[str, ...], scale: float = 1.0) -> set[str]:
    out: set[str] = set()
    for key in keys:
        v = _num(facts, key)
        if v is not None:
            out |= _forms(v * scale)
    return out


def number_kinds(facts: dict) -> dict[str, set[str]]:
    """Allowed display forms per kind of number, so "18 km/h" can't borrow the 18 m distance.

    kinds: speed (before km/h), percent (before %), sample (after n=), score (before /100),
    percentile (before st/nd/rd/th or パーセンタイル), and any (bare numbers: every fact).
    """
    speed_metric = facts.get("metric") == "shot_speed_kmh"
    speed = _union(facts, ("shot_speed_kmh",))
    if speed_metric:
        speed |= _union(facts, ("value", "norm", "delta", "group_prior"))
    fraction = ("value", "norm", "group_prior", "delta") if not speed_metric else ()
    percent = _union(facts, (*fraction, "xg", "psxg"), 100)
    pct = _num(facts, "est_percentile")
    if pct is not None:
        percent |= {str(round(pct)), str(round(100 - pct))}
    sample = _union(facts, ("sample_n",))  # "n=" always means the comparison sample
    score = _union(facts, fraction, 100) if facts.get("metric") == "placement" else set()
    percentile = {str(round(pct))} if pct is not None else set()
    general = (speed | percent | sample | score | percentile
               | _union(facts, ("value", "norm", "delta", "season_sample_n",
                                "weight_on_own_shots", "xg", "psxg", "distance_m",
                                "group_prior")))
    return {"speed": speed, "percent": percent, "sample": sample, "score": score,
            "percentile": percentile, "any": general}


def allowed_numbers(facts: dict) -> set[str]:
    """Every number a card may show for these facts, in any display form."""
    return number_kinds(facts)["any"]


UNIT_PATTERNS = (
    ("speed", re.compile(r"(\d+(?:\.\d+)?)\s*km/h")),
    ("percent", re.compile(r"(\d+(?:\.\d+)?)\s*%")),
    ("sample", re.compile(r"n\s*=\s*(\d+)")),
    ("score", re.compile(r"(\d+)\s*/\s*100\b")),
    ("percentile", re.compile(r"(\d+)\s*(?:st|nd|rd|th)\b")),
    ("percentile", re.compile(r"(\d+)\s*パーセンタイル")),
)
SCALE_SUFFIX = re.compile(r"/\s*100\b")  # the "/100" of a placement score is not a claim


def _surname(name: str) -> str:
    return name.split()[-1]


def _ja_short(name: str) -> str:
    return name.split("・")[-1] if "・" in name else name


# ---------- checks ----------

def _check_structure(slots: dict, ctx: VerifyContext) -> list[Failure]:
    out = []
    spec = TEMPLATES.get(ctx.template_id)
    if spec is None:
        return [Failure("structure", f"unknown template {ctx.template_id!r}")]
    limits = LIMITS[ctx.lang]
    for key in slots:
        if key not in TEXT_SLOTS:
            out.append(Failure("structure", f"unexpected slot {key!r}: return only "
                                            f"{', '.join(TEXT_SLOTS)}"))
    for key in spec.text_slots[ctx.mode]:
        value = slots.get(key)
        if not isinstance(value, str) or not value.strip():
            out.append(Failure("structure", f"slot {key!r} is missing or empty"))
            continue
        limit = getattr(limits, key)
        if len(value) > limit:
            out.append(Failure("structure", f"{key!r} is {len(value)} characters; the limit is "
                                            f"{limit}"))
    return out


def _check_numbers(text: str, ctx: VerifyContext) -> list[Failure]:
    kinds = number_kinds(ctx.facts)
    extra = set(ctx.extra_numbers)
    out = []
    claimed: list[tuple[int, int]] = []
    for kind, pattern in UNIT_PATTERNS:
        for m in pattern.finditer(text):
            claimed.append(m.span(1))
            if m.group(1) not in kinds[kind] | extra:
                allowed = ", ".join(sorted(kinds[kind], key=float)[:12]) or "none"
                out.append(Failure("numbers", f"{m.group(0).strip()} does not match FACTS; "
                                              f"allowed {kind} values: {allowed}"))
    claimed += [(m.start(), m.end()) for m in SCALE_SUFFIX.finditer(text)]
    for m in NUMBER.finditer(text):
        if any(a <= m.start() < b for a, b in claimed):
            continue
        if m.group(0) not in kinds["any"] | extra:
            allowed = ", ".join(sorted(kinds["any"], key=float)[:20])
            out.append(Failure("numbers", f"number {m.group(0)} is not in FACTS; use only these "
                                          f"values (rounded as shown): {allowed}"))
    return out


def _check_entities(text: str, ctx: VerifyContext, league: LeagueNames) -> list[Failure]:
    out = []
    own = league.players.get(ctx.player_id) if ctx.player_id else None
    own_forms = set()
    if own:
        own_forms = {own[0], _surname(own[0]), own[1], _ja_short(own[1])}
    for pid, (en, ja) in league.players.items():
        if pid == ctx.player_id:
            continue
        for form in ({_surname(en), en} if ctx.lang == "en" else {_ja_short(ja), ja}):
            if form in own_forms:
                continue  # shared surname with the insight's player
            hit = re.search(rf"\b{re.escape(form)}\b", text) if ctx.lang == "en" else form in text
            if hit:
                out.append(Failure("entities", f"names another player ({form}); mention only "
                                               f"{own[0] if own and ctx.lang == 'en' else own[1] if own else 'no player'}"))
                break
    own_club = league.player_club.get(ctx.player_id or "")
    for cid, (name, short) in league.clubs.items():
        if cid == own_club:
            continue
        if re.search(rf"\b({re.escape(name)}|{re.escape(short)})\b", text):
            out.append(Failure("entities", f"names another club ({name}); do not mention clubs"))
    return out


def _check_estimates(text: str, ctx: VerifyContext) -> list[Failure]:
    low = text.lower()
    if any(t in low for t in ESTIMATE_TRIGGERS[ctx.lang]) and not any(
            m in low for m in ESTIMATE_MARKERS[ctx.lang]):
        marker = "（推定）" if ctx.lang == "ja" else "(estimate)"
        return [Failure("estimates", f"percentages, percentiles and chances are model estimates; "
                                     f"say so, e.g. add {marker}")]
    return []


def _negated(low: str, at: int) -> bool:
    """English only: a denial of certainty just before the claim, in the same clause, denies
    it ("no one can say he will score"). Japanese stays strict: in 絶対に止められない the ない
    is not a denial."""
    clause = CLAUSE_BREAK.split(low[:at])[-1]
    return bool(DENIAL.search(clause))


def _check_certainty(text: str, ctx: VerifyContext) -> list[Failure]:
    low = text.lower()
    hits = [w for w in CERTAINTY[ctx.lang] if w in low
            and not (ctx.lang == "en" and all(_negated(low, m.start())
                                               for m in re.finditer(re.escape(w), low)))]
    if hits:
        return [Failure("certainty", f"remove certainty claims ({', '.join(hits)}); everything is "
                                     "an estimate")]
    return []


def _check_jargon(text: str, ctx: VerifyContext) -> list[Failure]:
    out = []
    low = text.lower()
    terms = [t for t in JARGON[ctx.lang] if t in low] + SNAKE_CASE.findall(text)
    if terms:
        out.append(Failure("jargon", f"internal labels shown to viewers ({', '.join(terms)}); "
                                     "use plain football words from CARD_FACTS"))
    metric = ctx.facts.get("metric")
    # Only the metric's own values shown as 0–1 fractions are wrong; other decimals (the
    # sample weight, xG on analyst cards) are fine.
    as_fraction = set()
    for key in ("value", "norm", "delta", "group_prior"):
        v = ctx.facts.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            as_fraction |= {s for s in _forms(v) if s.startswith("0.")}
    raw = [r for r in FRACTION.findall(text) if r in as_fraction]
    if raw and (metric == "placement" or (metric == "psxg" and ctx.mode == "casual")):
        unit = "a score out of 100 (e.g. 44/100)" if metric == "placement" else "a percentage"
        out.append(Failure("jargon", f"raw fraction(s) {', '.join(raw)}; show it as {unit}"))
    return out


def _check_headline_names_player(slots: dict, ctx: VerifyContext,
                                 league: LeagueNames) -> list[Failure]:
    own = league.players.get(ctx.player_id) if ctx.player_id else None
    headline = slots.get("headline")
    if not own or not isinstance(headline, str) or not headline:
        return []
    forms = {own[0], _surname(own[0])} if ctx.lang == "en" else {own[1], _ja_short(own[1])}
    if not any(form in headline for form in forms):
        name = _surname(own[0]) if ctx.lang == "en" else _ja_short(own[1])
        return [Failure("structure", f"the headline must name the player ({name})")]
    return []


def _check_language(slots: dict, ctx: VerifyContext) -> list[Failure]:
    text = " ".join(v for k, v in slots.items() if k in ("headline", "sub") and isinstance(v, str))
    if ctx.lang == "ja" and not JAPANESE.search(text):
        return [Failure("language", "write the headline and sub in Japanese")]
    if ctx.lang == "en" and KANA.search(text):
        return [Failure("language", "write in English only")]
    return []


def verify(slots: dict, ctx: VerifyContext, league: LeagueNames) -> Verdict:
    """Check one card's free text for one (template, lang, mode)."""
    failures = _check_structure(slots, ctx)
    text = normalize(" ".join(str(slots.get(k, "")) for k in TEXT_SLOTS))
    failures += _check_numbers(text, ctx)
    failures += _check_entities(text, ctx, league)
    failures += _check_estimates(text, ctx)
    failures += _check_certainty(text, ctx)
    failures += _check_language(slots, ctx)
    failures += _check_jargon(text, ctx)
    failures += _check_headline_names_player(slots, ctx, league)
    return Verdict(tuple(failures))


def league_names(players, clubs) -> LeagueNames:
    return LeagueNames(
        players={p.player_id: (p.display_name, p.display_name_ja) for p in players},
        clubs={c.club_id: (c.name, c.short_name) for c in clubs},
        player_club={p.player_id: p.club_id for p in players},
    )
