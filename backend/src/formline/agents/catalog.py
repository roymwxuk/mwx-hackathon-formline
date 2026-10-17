"""Fixed overlay template catalog: which template shows which insight, and how.

The catalog is the JSON contract between the agents and the viewer. The LLM only
writes free text (`tag`, `headline`, `sub`); `bars` and `rows` are built here,
deterministically, from the insight's facts, so their numbers are correct by
construction. Length limits and required slots are what the verifier checks.
"""

from dataclasses import dataclass

from formline.schema.overlay import Bar, Row

# insight type -> template; insight metric -> overlay metric ("my metric" filter)
TEMPLATE_FOR_INSIGHT = {
    "shot_speed_vs_norm": "shot_speed_card",
    "season_best": "shot_speed_card",
    "season_worst": "shot_speed_card",
    "placement_vs_norm": "placement_card",
    "finish_vs_norm": "finish_quality_card",
}
OVERLAY_METRIC = {"shot_speed_kmh": "shot_speed", "placement": "finishing", "psxg": "finishing"}
INSIGHT_TYPES_COVERED = set(TEMPLATE_FOR_INSIGHT)


@dataclass(frozen=True)
class SlotLimits:
    tag: int
    headline: int
    sub: int


LIMITS = {"en": SlotLimits(tag=40, headline=60, sub=140),
          "ja": SlotLimits(tag=20, headline=30, sub=70)}


@dataclass(frozen=True)
class TemplateSpec:
    template_id: str
    text_slots: dict[str, tuple[str, ...]]  # mode -> required free-text slots
    structured: dict[str, str | None]  # mode -> "bars" / "rows" / None


TEMPLATES = {
    t: TemplateSpec(t, {"casual": ("tag", "headline", "sub"),
                        "analyst": ("tag", "headline", "sub")},
                    {"casual": "bars", "analyst": "rows"})
    for t in ("shot_speed_card", "placement_card", "finish_quality_card")
} | {
    "correction_banner": TemplateSpec(
        "correction_banner",
        {"casual": ("tag", "headline", "sub"), "analyst": ("tag", "headline", "sub")},
        {"casual": None, "analyst": None}),
}

COMPARISON_LABELS = {
    "en": {
        "zone_body_pressure": "same zone, body part and pressure",
        "zone_body": "same zone and body part",
        "area_body": "same area and body part",
        "body": "same body part, anywhere",
    },
    "ja": {
        "zone_body_pressure": "同じゾーン・部位・プレッシャー",
        "zone_body": "同じゾーン・部位",
        "area_body": "同じエリア・部位",
        "body": "同じ部位（全エリア）",
    },
}

LABELS = {
    "en": {
        "this_shot": "This shot", "his_norm": "His norm",
        "this_finish": "This finish", "his_typical": "His typical",
        "baseline": "Baseline (shrunk)", "sample": "Sample · weight",
        "comparison": "Comparison", "percentile": "Percentile (est.)",
        "xg": "xG · PSxG", "xg_only": "xG", "placement": "Placement score",
        "psxg": "Post-shot xG",
    },
    "ja": {
        "this_shot": "今回", "his_norm": "本人の平均",
        "this_finish": "今回", "his_typical": "本人の平均",
        "baseline": "基準値（縮小推定）", "sample": "サンプル数・重み",
        "comparison": "比較グループ", "percentile": "パーセンタイル（推定）",
        "xg": "xG・PSxG", "xg_only": "xG", "placement": "コーススコア", "psxg": "シュート後xG",
    },
}


def ordinal(n: int, lang: str) -> str:
    if lang == "ja":
        return f"{n}パーセンタイル"
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _speed(v: float) -> str:
    return f"{round(v)} km/h"


def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


def _score(v: float) -> str:
    return f"{round(v * 100)}/100"


def bars(template_id: str, facts: dict, lang: str) -> list[Bar]:
    """Casual card: this shot vs his own norm, two bars."""
    lab = LABELS[lang]
    value, norm = facts["value"], facts["norm"]
    if template_id == "shot_speed_card":
        names, fmt = (lab["this_shot"], lab["his_norm"]), _speed
    elif template_id == "placement_card":
        names, fmt = (lab["this_finish"], lab["his_typical"]), _score
    elif template_id == "finish_quality_card":
        names, fmt = (lab["this_finish"], lab["his_typical"]), _pct
    else:
        raise ValueError(f"{template_id} has no bars")
    return [Bar(label=names[0], value=value, display=fmt(value), highlight=True),
            Bar(label=names[1], value=norm, display=fmt(norm), highlight=False)]


def rows(template_id: str, facts: dict, lang: str) -> list[Row]:
    """Analyst card: the numbers behind the comparison, every one from facts."""
    lab = LABELS[lang]
    sep = "・" if lang == "ja" else " · "
    sample = f"n={facts['sample_n']}{sep}{facts['weight_on_own_shots']:.2f}"
    comparison = COMPARISON_LABELS[lang][facts["comparison_level"]]
    pct = ordinal(facts["est_percentile"], lang)
    psxg = facts.get("psxg")
    xg = f"{facts['xg']:.2f}{sep}{psxg:.2f}" if psxg is not None else f"{facts['xg']:.2f}"
    if template_id == "shot_speed_card":
        first = Row(label=lab["baseline"], value=_speed(facts["norm"]))
    elif template_id == "placement_card":
        first = Row(label=lab["placement"],
                    value=f"{_score(facts['value'])} ({lab['his_norm']} {_score(facts['norm'])})")
    elif template_id == "finish_quality_card":
        first = Row(label=lab["psxg"],
                    value=f"{_pct(facts['value'])} ({lab['his_norm']} {_pct(facts['norm'])})")
    else:
        raise ValueError(f"{template_id} has no rows")
    return [first,
            Row(label=lab["sample"], value=sample),
            Row(label=lab["comparison"], value=comparison),
            Row(label=lab["percentile"], value=pct),
            Row(label=lab["xg"] if psxg is not None else lab["xg_only"], value=xg)]


def structured_slots(template_id: str, mode: str, facts: dict, lang: str) -> dict:
    """The deterministic part of a card's slots for one mode and language."""
    kind = TEMPLATES[template_id].structured[mode]
    if kind == "bars":
        return {"bars": bars(template_id, facts, lang)}
    if kind == "rows":
        return {"rows": rows(template_id, facts, lang)}
    return {}
