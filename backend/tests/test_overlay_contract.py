import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from formline.agents.catalog import (
    INSIGHT_TYPES_COVERED,
    LIMITS,
    TEMPLATE_FOR_INSIGHT,
    TEMPLATES,
    bars,
    ordinal,
    rows,
    structured_slots,
)
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.insights import INSIGHT_TYPES, SEASON_TYPES, InsightCreated
from formline.engine.log import current_events
from formline.engine.pipeline import LivePipeline
from formline.generator.season import generate_season
from formline.schema.overlay import Overlay, OverlaySlots, overlay_message

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "docs" / "contracts" / "overlay.schema.json"
EXAMPLES = REPO / "backend" / "data" / "sample" / "overlays.example.json"


@pytest.fixture(scope="module")
def live_insights():
    season = generate_season(2026)
    eng = BaselineEngine(season.league.players)
    eng.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                  for e in current_events(gm.feed))
    eng.fit_priors()
    live = next(gm.feed for gm in season.matches if gm.match.is_live_demo)
    return [c.insight for c in LivePipeline(eng).run(live) if isinstance(c, InsightCreated)]


# ---------- committed contract artefacts ----------

def test_committed_schema_matches_the_models():
    assert json.loads(SCHEMA.read_text()) == Overlay.model_json_schema()


def test_committed_examples_validate_and_cover_every_op():
    examples = [Overlay.model_validate(o) for o in json.loads(EXAMPLES.read_text())]
    assert {o.op for o in examples} == {"show", "retract", "correct"}
    assert any(o.template_id == "correction_banner" for o in examples)
    assert {o.lang for o in examples} == {"en", "ja"}


# ---------- model rules ----------

def _overlay(**changes) -> dict:
    base = json.loads(EXAMPLES.read_text())[0]
    return base | changes


def test_retract_and_correct_must_name_what_they_supersede():
    with pytest.raises(ValidationError):
        Overlay.model_validate(_overlay(op="retract", supersedes_overlay_id=None))
    with pytest.raises(ValidationError):
        Overlay.model_validate(_overlay(op="show", supersedes_overlay_id="ovl_x"))


def test_every_overlay_cites_a_source_event():
    with pytest.raises(ValidationError):
        Overlay.model_validate(_overlay(source_event_ids=[]))


def test_stream_message_shape():
    msg = overlay_message(Overlay.model_validate(_overlay()))
    assert msg["kind"] == "overlay" and "stat" not in msg["overlay"]["slots"]


# ---------- catalog ----------

def test_every_insight_type_has_a_template():
    produced = set(INSIGHT_TYPES.values()) | set(SEASON_TYPES.values())
    assert produced == set(TEMPLATE_FOR_INSIGHT) == INSIGHT_TYPES_COVERED
    assert set(TEMPLATE_FOR_INSIGHT.values()) | {"correction_banner"} == set(TEMPLATES)


def test_bars_and_rows_come_straight_from_facts(live_insights):
    for ins in live_insights:
        template = TEMPLATE_FOR_INSIGHT[ins.type]
        for lang in ("en", "ja"):
            b = bars(template, ins.facts, lang)
            assert [x.value for x in b] == [ins.facts["value"], ins.facts["norm"]]
            assert b[0].highlight and not b[1].highlight
            r = rows(template, ins.facts, lang)
            assert len(r) == 5
            assert ordinal(ins.facts["est_percentile"], lang) in [x.value for x in r]
            for mode in ("casual", "analyst"):
                slots = OverlaySlots(tag="t", headline="h", sub="s",
                                     **structured_slots(template, mode, ins.facts, lang))
                assert (slots.bars is not None) == (mode == "casual")
                assert (slots.rows is not None) == (mode == "analyst")


def test_speed_display_rounds_like_the_mock():
    b = bars("shot_speed_card", {"value": 84.1, "norm": 92.3}, "en")
    assert [x.display for x in b] == ["84 km/h", "92 km/h"]


@pytest.mark.parametrize("n,en", [(1, "1st"), (2, "2nd"), (3, "3rd"), (11, "11th"),
                                  (12, "12th"), (21, "21st"), (99, "99th")])
def test_ordinals(n, en):
    assert ordinal(n, "en") == en
    assert ordinal(n, "ja") == f"{n}パーセンタイル"


def test_japanese_limits_are_tighter():
    assert LIMITS["ja"].headline < LIMITS["en"].headline


def test_xg_row_label_matches_what_is_shown():
    facts = {"value": 118.3, "norm": 87.1, "sample_n": 6, "weight_on_own_shots": 0.73,
             "comparison_level": "zone_body", "est_percentile": 99, "xg": 0.05}
    assert rows("shot_speed_card", facts, "en")[-1].label == "xG"
    assert rows("shot_speed_card", facts | {"psxg": 0.4}, "en")[-1].label == "xG · PSxG"
