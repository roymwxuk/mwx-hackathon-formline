import re

import pytest

from formline.agents.catalog import LIMITS
from formline.agents.template_narrator import names_for, narrate, narrate_correction
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.insights import InsightCorrected, InsightCreated, InsightRetracted
from formline.engine.log import current_events
from formline.engine.pipeline import LivePipeline
from formline.generator.season import generate_season

VARIANTS = [(lang, mode) for lang in ("en", "ja") for mode in ("casual", "analyst")]


@pytest.fixture(scope="module")
def world():
    season = generate_season(2026)
    eng = BaselineEngine(season.league.players)
    eng.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                  for e in current_events(gm.feed))
    eng.fit_priors()
    live = next(gm.feed for gm in season.matches if gm.match.is_live_demo)
    changes = LivePipeline(eng).run(live)
    players = {p.player_id: p for p in season.league.players}
    return changes, players


def created(world):
    changes, players = world
    for c in changes:
        if isinstance(c, InsightCreated):
            p = players[c.insight.player_id]
            yield c.insight, names_for(p.display_name, p.display_name_ja)


def allowed_numbers(facts: dict) -> set[str]:
    """Every number the template may print, derived from facts (as the verifier will)."""
    out = set()
    for key in ("value", "norm", "delta", "sample_n", "est_percentile", "season_sample_n",
                "weight_on_own_shots", "xg", "psxg"):
        v = facts.get(key)
        if v is None:
            continue
        for x in (v, abs(v)):
            out |= {str(round(x)), f"{x:.1f}", f"{x:.2f}", str(x)}
            if key in ("value", "norm") and x <= 1:  # placement or PSxG shown as % or /100
                out.add(str(round(x * 100)))
    p = facts["est_percentile"]
    out |= {str(100 - p)}
    return out


def test_every_insight_gets_four_valid_variants(world):
    for ins, names in created(world):
        for lang, mode in VARIANTS:
            t = narrate(ins, lang, mode, names)
            lim = LIMITS[lang]
            assert t.tag and t.headline and t.sub
            assert len(t.tag) <= lim.tag, t.tag
            assert len(t.headline) <= lim.headline, t.headline
            assert len(t.sub) <= lim.sub, t.sub


def test_only_the_insights_player_is_named(world):
    _, players = world
    for ins, names in created(world):
        for lang, mode in VARIANTS:
            text = " ".join(vars(narrate(ins, lang, mode, names)).values())
            assert (names.ja if lang == "ja" else names.en) in text
            others = {p.display_name.split()[-1] for p in players.values()
                      if p.player_id != ins.player_id and p.display_name.split()[-1] != names.en}
            assert not [o for o in others if re.search(rf"\b{o}\b", text)]


def test_every_number_comes_from_facts(world):
    for ins, names in created(world):
        allowed = allowed_numbers(ins.facts) | {"100"}  # "/100" score scale
        for lang, mode in VARIANTS:
            text = " ".join(vars(narrate(ins, lang, mode, names)).values())
            for num in re.findall(r"\d+(?:\.\d+)?", text):
                assert num in allowed, (num, text)


def test_estimates_are_always_marked(world):
    markers = {"en": ("estimate", "Est."), "ja": ("推定",)}
    for ins, names in created(world):
        for lang, mode in VARIANTS:
            t = narrate(ins, lang, mode, names)
            text = f"{t.headline} {t.sub}"
            mentions_estimate_quantity = ("%" in text or "percentile" in text
                                          or "パーセンタイル" in text or "about" in text
                                          or "約" in text)
            if mentions_estimate_quantity:
                assert any(m in text for m in markers[lang]), text


def test_this_spot_only_at_zone_level(world):
    for ins, names in created(world):
        text = narrate(ins, "en", "casual", names).sub + narrate(ins, "en", "analyst", names).sub
        zone_level = ins.facts["comparison_level"] in ("zone_body_pressure", "zone_body")
        assert ("this spot" in text) == zone_level or ins.type.startswith("season_")
        ja = narrate(ins, "ja", "casual", names).sub
        assert ("この位置" in ja or "同じ位置" in ja) == zone_level or ins.type.startswith("season_")


def test_thin_samples_are_flagged(world):
    for ins, names in created(world):
        if ins.facts["sample_n"] < 5:
            assert "Small sample" in narrate(ins, "en", "analyst", names).sub
            assert "サンプル少" in narrate(ins, "ja", "analyst", names).sub


def test_flagship_slow_shot_wording(world):
    ins, names = next((i, n) for i, n in created(world)
                      if i.player_id == "ply_0107" and i.facts["value"] == 84.1
                      and i.type == "shot_speed_vs_norm")
    casual = narrate(ins, "en", "casual", names)
    assert casual.headline == "Reyner — not his usual strike"
    assert casual.sub.startswith("84 km/h, about 8 km/h below his typical shot")
    assert narrate(ins, "ja", "casual", names).headline == "レイナー、いつもの威力がない"


def test_correction_banner_for_the_var_overturn(world):
    changes, _ = world
    group = [c for c in changes if isinstance(c, (InsightCorrected, InsightRetracted))]
    assert narrate_correction(group, "en", "casual").headline == "Goal disallowed after review"
    assert "ゴール取り消し" in narrate_correction(group, "ja", "casual").headline
    analyst = narrate_correction(group, "en", "analyst").sub
    assert "1 overlay(s) withdrawn, 1 corrected" in analyst
