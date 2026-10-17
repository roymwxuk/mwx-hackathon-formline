"""Contract artefacts: the overlay JSON Schema and example overlays from real insights.

Both are committed, so the frontend can test against exactly what the backend emits.
The example text is minimal; real wording comes from the narrator (task 2+).
"""

import json
from pathlib import Path

from formline.agents.catalog import OVERLAY_METRIC, TEMPLATE_FOR_INSIGHT, structured_slots
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.insights import Insight, InsightCorrected, InsightCreated, InsightRetracted
from formline.engine.log import current_events
from formline.engine.pipeline import LivePipeline
from formline.generator.season import generate_season
from formline.schema.overlay import Overlay, OverlaySlots, overlay_json

SHOW_DELAY_MS = 2_000  # a card appears shortly after the shot
TTL_MS = 12_000


def overlay_id(insight_id: str, lang: str, mode: str, version: int = 1) -> str:
    base = f"ovl_{insight_id.removeprefix('ins_')}_{lang}_{mode}"
    return base if version == 1 else f"{base}_v{version}"


def _example_text(ins: Insight, lang: str, names: dict[str, tuple[str, str]]) -> dict:
    en, ja = names[ins.player_id]
    f = ins.facts
    if lang == "ja":
        return {"tag": "本人比", "headline": f"{ja} {f['value']}",
                "sub": f"本人の平均 {f['norm']}（推定）"}
    return {"tag": "VS HIS OWN NORM", "headline": f"{en}: {f['value']}",
            "sub": f"His norm is about {f['norm']} (model estimate)."}


def _show(ins: Insight, lang: str, mode: str, names, op: str = "show",
          supersedes: str | None = None) -> Overlay:
    template = TEMPLATE_FOR_INSIGHT[ins.type]
    slots = OverlaySlots(**_example_text(ins, lang, names),
                         **structured_slots(template, mode, ins.facts, lang))
    return Overlay(
        overlay_id=overlay_id(ins.insight_id, lang, mode, ins.version),
        op=op, supersedes_overlay_id=supersedes,
        match_clock_ms=ins.match_clock_ms + SHOW_DELAY_MS, ttl_ms=TTL_MS,
        template_id=template, priority=1 if ins.salience >= 0.8 else 2 if ins.salience >= 0.5
        else 3, audience_mode=mode, lang=lang, slots=slots, insight_id=ins.insight_id,
        player_id=ins.player_id, metric=OVERLAY_METRIC[ins.metric],
        source_event_ids=list(ins.source_event_ids), verified=False,
    )


def build_examples(seed: int = 2026) -> list[Overlay]:
    """A show, a retract, a correct and a correction banner from the live match."""
    season = generate_season(seed)
    names = {p.player_id: (p.display_name, p.display_name_ja) for p in season.league.players}
    engine = BaselineEngine(season.league.players)
    engine.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                     for e in current_events(gm.feed))
    engine.fit_priors()
    live = next(gm.feed for gm in season.matches if gm.match.is_live_demo)
    changes = LivePipeline(engine).run(live)

    slow = next(c.insight for c in changes if isinstance(c, InsightCreated)
                and c.insight.player_id == "ply_0107" and c.insight.facts["value"] == 84.1
                and c.insight.type == "shot_speed_vs_norm")
    retracted = next(c for c in changes if isinstance(c, InsightRetracted))
    corrected = next(c for c in changes if isinstance(c, InsightCorrected))
    original = next(c.insight for c in changes if isinstance(c, InsightCreated)
                    and c.insight.insight_id == retracted.insight.insight_id)

    out = [_show(slow, "en", "casual", names), _show(slow, "ja", "analyst", names),
           _show(original, "en", "analyst", names)]
    out.append(Overlay(
        overlay_id=overlay_id(original.insight_id, "en", "analyst") + "_retract", op="retract",
        supersedes_overlay_id=overlay_id(original.insight_id, "en", "analyst"),
        match_clock_ms=out[-1].match_clock_ms + 100_000, ttl_ms=0,
        template_id=out[-1].template_id, priority=1, audience_mode="analyst", lang="en",
        slots=OverlaySlots(tag="", headline=""), insight_id=original.insight_id,
        player_id=original.player_id, metric=out[-1].metric,
        source_event_ids=list(original.source_event_ids), verified=True))
    out.append(_show(corrected.after, "en", "casual", names, op="correct",
                     supersedes=overlay_id(corrected.before.insight_id, "en", "casual")))
    out.append(Overlay(
        overlay_id=f"ovl_banner_{corrected.after.source_event_ids[0]}_en_casual", op="show",
        supersedes_overlay_id=None, match_clock_ms=out[-1].match_clock_ms, ttl_ms=240_000,
        template_id="correction_banner", priority=1, audience_mode="casual", lang="en",
        slots=OverlaySlots(tag="CORRECTION · VAR", headline="Goal disallowed",
                           sub="The earlier stat has been withdrawn."),
        insight_id=corrected.after.insight_id, player_id=None, metric=None,
        source_event_ids=list(corrected.after.source_event_ids), verified=True))
    return out


def write_contracts(schema_path: Path, examples_path: Path, seed: int = 2026) -> None:
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(Overlay.model_json_schema(), indent=2) + "\n",
                           encoding="utf-8")
    examples = [overlay_json(o) for o in build_examples(seed)]
    examples_path.write_text(json.dumps(examples, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
