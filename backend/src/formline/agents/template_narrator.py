"""Deterministic template narrator: correct wording for every insight, no LLM.

It is the floor of the system: the fallback after the verifier rejects an LLM
narration N times, and the whole narration layer when no LLM is configured.

Rules built in:
- every number comes from `Insight.facts`, rounded for display;
- percentiles and probabilities are always marked as estimates;
- "from this spot" only when the comparison really was zone-level, otherwise the
  wider comparison is named honestly;
- thin samples are flagged.
"""

from dataclasses import dataclass

from formline.agents.catalog import ordinal
from formline.engine.insights import Insight, InsightChange, InsightCorrected, InsightRetracted

INSIDE_BOX = {"six_yard", "box_central", "box_wide"}


@dataclass(frozen=True)
class TextSlots:
    tag: str
    headline: str
    sub: str


@dataclass(frozen=True)
class Names:
    en: str  # surname, e.g. "Reyner"
    ja: str  # e.g. "レイナー" or "伊藤健二"


def names_for(display_name: str, display_name_ja: str) -> Names:
    en = display_name.split()[-1]
    ja = display_name_ja.split("・")[-1] if "・" in display_name_ja else display_name_ja
    return Names(en, ja)


# ---------- phrases ----------

BODY_EN = {"strong_foot": "strong-foot", "weak_foot": "weaker-foot", "head": "headed"}
BODY_JA = {"strong_foot": "利き足", "weak_foot": "逆足", "head": "ヘディング"}


def _pool_en(f: dict, noun: str = "shots") -> str:
    """The comparison pool, honestly named: "his shots from this spot", …"""
    level = f["comparison_level"]
    if level == "zone_body_pressure":
        return f"his {noun} from this spot under similar pressure"
    if level == "zone_body":
        return f"his {noun} from this spot"
    if level == "area_body":
        area = "inside" if f["zone"] in INSIDE_BOX else "outside"
        return f"his {noun} from {area} the box"
    return f"all his {BODY_EN.get(f['body_group'], '')} {noun}"


def _typical_en(f: dict, noun: str = "shot") -> str:
    """"his typical shot from this spot" / "his typical strong-foot shot"."""
    level = f["comparison_level"]
    if level == "body":
        return f"his typical {BODY_EN.get(f['body_group'], '')} {noun}"
    return "his typical " + _pool_en(f, noun).removeprefix("his ")


def _pool_ja(f: dict) -> str:
    level = f["comparison_level"]
    if level == "zone_body_pressure":
        return "同じ位置・同じプレッシャーでのシュート"
    if level == "zone_body":
        return "この位置からのシュート"
    if level == "area_body":
        return "エリア内からのシュート" if f["zone"] in INSIDE_BOX else "エリア外からのシュート"
    return f"{BODY_JA.get(f['body_group'], '')}シュート全体"


def _thin_en(f: dict) -> str:
    return " Small sample." if f["thin_sample"] or f["sample_n"] < 5 else ""


def _thin_ja(f: dict) -> str:
    return "（サンプル少）" if f["thin_sample"] or f["sample_n"] < 5 else ""


def _kmh(v: float) -> str:
    return f"{round(v)} km/h"


def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


def _signed(v: float) -> str:
    return f"+{v:.1f}" if v > 0 else f"−{abs(v):.1f}" if v < 0 else "0.0"


# ---------- casual ----------

def _casual_en(ins: Insight, n: Names) -> TextSlots:
    f, below = ins.facts, ins.direction == "below"
    gap = round(abs(f["delta"]))
    if ins.type in ("season_best", "season_worst"):
        best = ins.type == "season_best"
        what = "goal" if f["outcome"] == "goal" and best else "shot"
        return TextSlots(
            "SHOT SPEED · SEASON RECORD",
            f"{n.en}'s {'fastest' if best else 'softest'} {what} of the season",
            f"{_kmh(f['value'])}, {'beating' if best else 'below'} all {f['season_sample_n']} "
            f"of his earlier {BODY_EN.get(f['body_group'], '')} shots this season.")
    if ins.type == "shot_speed_vs_norm":
        return TextSlots(
            "SHOT SPEED · VS HIS OWN NORM",
            f"{n.en} — not his usual strike" if below else f"{n.en} hits it harder than usual",
            f"{_kmh(f['value'])}, about {gap} km/h {'below' if below else 'above'} "
            f"{_typical_en(f)} (estimate).{_thin_en(f)}")
    if ins.type == "placement_vs_norm":
        share = f["est_percentile"] if below else 100 - f["est_percentile"]
        return TextSlots(
            "FINISHING · VS HIS OWN NORM",
            f"{n.en}'s finish was easy for the keeper" if below else f"{n.en} picks his corner",
            f"Placement in the {'bottom' if below else 'top'} {share}% of "
            f"{_pool_en(f, 'finishes')} (estimate).{_thin_en(f)}")
    if ins.type == "finish_vs_norm":
        return TextSlots(
            "FINISHING · VS HIS OWN NORM",
            f"A tame finish from {n.en}" if below else f"{n.en} finishes better than usual",
            f"This finish had about a {_pct(f['value'])} chance; "
            f"{_typical_en(f, 'finish')} is about {_pct(f['norm'])} (model estimate)."
            f"{_thin_en(f)}")
    raise ValueError(ins.type)


def _casual_ja(ins: Insight, n: Names) -> TextSlots:
    f, below = ins.facts, ins.direction == "below"
    gap = round(abs(f["delta"]))
    if ins.type in ("season_best", "season_worst"):
        best = ins.type == "season_best"
        what = "ゴール" if f["outcome"] == "goal" and best else "シュート"
        return TextSlots(
            "シュートスピード・今季記録",
            f"{n.ja}、今季{'最速の' if best else '最も弱い'}{what}",
            f"{_kmh(f['value'])}。今季の{BODY_JA.get(f['body_group'], '')}シュート"
            f"{f['season_sample_n']}本を{'すべて上回った' if best else 'すべて下回った'}")
    if ins.type == "shot_speed_vs_norm":
        return TextSlots(
            "シュートスピード・本人比",
            f"{n.ja}、いつもの威力がない" if below else f"{n.ja}、普段より強烈な一撃",
            f"{_kmh(f['value'])}。{_pool_ja(f)}の平均より約{gap} km/h"
            f"{'遅い' if below else '速い'}（推定）{_thin_ja(f)}")
    if ins.type == "placement_vs_norm":
        share = f["est_percentile"] if below else 100 - f["est_percentile"]
        return TextSlots(
            "フィニッシュ・本人比",
            f"{n.ja}、コースが甘い" if below else f"{n.ja}、コースを突いた",
            f"{_pool_ja(f)}の中で{'下位' if below else '上位'}{share}%のコース"
            f"（推定）{_thin_ja(f)}")
    if ins.type == "finish_vs_norm":
        return TextSlots(
            "フィニッシュ・本人比",
            f"{n.ja}、決めきれない一本" if below else f"{n.ja}、普段以上のフィニッシュ",
            f"得点確率は約{_pct(f['value'])}、{_pool_ja(f)}の平均は約{_pct(f['norm'])}"
            f"（推定）{_thin_ja(f)}")
    raise ValueError(ins.type)


# ---------- analyst ----------

ESTIMATES_EN = "Model estimates."
ESTIMATES_JA = "数値はモデルによる推定値です。"


def _analyst_en(ins: Insight, n: Names) -> TextSlots:
    f = ins.facts
    pct = ordinal(f["est_percentile"], "en")
    basis = (f"vs {_pool_en(f)} (n={f['sample_n']}, weight {f['weight_on_own_shots']:.2f})."
             f"{_thin_en(f)} {ESTIMATES_EN}")
    if ins.type in ("season_best", "season_worst"):
        best = ins.type == "season_best"
        return TextSlots(
            "SHOT SPEED · SEASON RECORD",
            f"{n.en} {f['value']} km/h · season {'best' if best else 'low'}",
            f"{'Beats' if best else 'Below'} all {f['season_sample_n']} earlier "
            f"{BODY_EN.get(f['body_group'], '')} shots. Est. {pct} pct. vs {_pool_en(f)}. "
            f"{ESTIMATES_EN}")
    if ins.type == "shot_speed_vs_norm":
        return TextSlots(
            "SHOT SPEED · PERSONAL BASELINE",
            f"{n.en} {f['value']} km/h · Δ {_signed(f['delta'])} vs baseline",
            f"Est. {pct} percentile {basis}")
    if ins.type == "placement_vs_norm":
        return TextSlots(
            "FINISHING · PERSONAL BASELINE",
            f"{n.en} placement {round(f['value'] * 100)}/100 · est. {pct} pct.",
            f"Baseline {round(f['norm'] * 100)}/100 {basis}")
    if ins.type == "finish_vs_norm":
        return TextSlots(
            "FINISHING · PERSONAL BASELINE",
            f"{n.en} PSxG {f['value']:.2f} vs baseline {f['norm']:.2f}",
            f"Est. {pct} pct., xG {f['xg']:.2f}, {basis}")
    raise ValueError(ins.type)


def _analyst_ja(ins: Insight, n: Names) -> TextSlots:
    f = ins.facts
    pct = ordinal(f["est_percentile"], "ja")
    basis = f"n={f['sample_n']}・重み{f['weight_on_own_shots']:.2f}。{_thin_ja(f)}{ESTIMATES_JA}"
    if ins.type in ("season_best", "season_worst"):
        best = ins.type == "season_best"
        return TextSlots(
            "シュートスピード・今季記録",
            f"{n.ja} {f['value']} km/h・今季{'最速' if best else '最低'}",
            f"今季の{BODY_JA.get(f['body_group'], '')}シュート{f['season_sample_n']}本を"
            f"{'上回る' if best else '下回る'}。推定{pct}。{basis}")
    if ins.type == "shot_speed_vs_norm":
        return TextSlots(
            "シュートスピード・本人基準",
            f"{n.ja} {f['value']} km/h・基準比 {_signed(f['delta'])}",
            f"{_pool_ja(f)}と比べ推定{pct}。{basis}")
    if ins.type == "placement_vs_norm":
        return TextSlots(
            "フィニッシュ・本人基準",
            f"{n.ja} コース{round(f['value'] * 100)}/100・推定{pct}",
            f"基準値{round(f['norm'] * 100)}/100。{basis}")
    if ins.type == "finish_vs_norm":
        return TextSlots(
            "フィニッシュ・本人基準",
            f"{n.ja} PSxG {f['value']:.2f}・基準{f['norm']:.2f}",
            f"推定{pct}。xG {f['xg']:.2f}。{basis}")
    raise ValueError(ins.type)


NARRATORS = {
    ("en", "casual"): _casual_en, ("ja", "casual"): _casual_ja,
    ("en", "analyst"): _analyst_en, ("ja", "analyst"): _analyst_ja,
}


def narrate(ins: Insight, lang: str, mode: str, names: Names) -> TextSlots:
    return NARRATORS[(lang, mode)](ins, names)


# ---------- correction banner ----------

def narrate_correction(changes: list[InsightChange], lang: str, mode: str) -> TextSlots:
    """One banner for all insight changes caused by a single corrected event."""
    goal_overturned = any(
        isinstance(c, InsightCorrected) and c.before.facts.get("outcome") == "goal"
        and c.after.facts.get("outcome") != "goal" for c in changes
    ) or any(isinstance(c, InsightRetracted) and c.insight.facts.get("outcome") == "goal"
             for c in changes)
    withdrawn = sum(isinstance(c, InsightRetracted) for c in changes)
    updated = sum(isinstance(c, InsightCorrected) for c in changes)
    if lang == "ja":
        headline = "ゴール取り消し（判定変更）" if goal_overturned else "データ訂正"
        if mode == "casual":
            return TextSlots("訂正", headline, "先ほどの表示を更新しました。")
        return TextSlots("訂正", headline,
                         f"表示を取り消し{withdrawn}件・更新{updated}件。"
                         "イベントログから基準値を再計算しました。")
    headline = "Goal disallowed after review" if goal_overturned else "Data correction"
    if mode == "casual":
        return TextSlots("CORRECTION", headline, "The earlier stat has been updated.")
    return TextSlots("CORRECTION", headline,
                     f"{withdrawn} overlay(s) withdrawn, {updated} corrected; baselines rebuilt "
                     "from the event log.")
