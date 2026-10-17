"""Overlay Composer: fills a catalog template as a timed overlay. Deterministic.

Text slots come from the narrator (already verified); `bars` / `rows` come from the
catalog's builders over the insight's facts; ids, timing, priority, metric and
lineage come from the selection and the insight.
"""

from formline.agents.catalog import OVERLAY_METRIC, TEMPLATE_FOR_INSIGHT, structured_slots
from formline.agents.selector import Selection
from formline.engine.insights import Insight
from formline.schema.overlay import Overlay, OverlaySlots

SHOW_DELAY_MS = 2_000  # a card appears shortly after the shot
TTL_MS = 12_000
TTL_RECORD_MS = 15_000  # season records stay a little longer


def overlay_id(insight_id: str, lang: str, mode: str, version: int = 1) -> str:
    base = f"ovl_{insight_id.removeprefix('ins_')}_{lang}_{mode}"
    return base if version == 1 else f"{base}_v{version}"


def compose(selection: Selection, lang: str, mode: str, text: dict, *, verified: bool = True,
            op: str = "show", supersedes: str | None = None,
            at_ms: int | None = None) -> Overlay:
    ins: Insight = selection.insight
    template = TEMPLATE_FOR_INSIGHT[ins.type]
    slots = OverlaySlots(tag=text["tag"], headline=text["headline"], sub=text["sub"],
                         **structured_slots(template, mode, ins.facts, lang))
    record = ins.type.startswith("season_")
    return Overlay(
        overlay_id=overlay_id(ins.insight_id, lang, mode, ins.version),
        op=op,
        supersedes_overlay_id=supersedes,
        match_clock_ms=at_ms if at_ms is not None else ins.match_clock_ms + SHOW_DELAY_MS,
        ttl_ms=TTL_RECORD_MS if record else TTL_MS,
        template_id=template,
        priority=selection.priority,
        audience_mode=mode,
        lang=lang,
        slots=slots,
        insight_id=ins.insight_id,
        player_id=ins.player_id,
        metric=OVERLAY_METRIC[ins.metric],
        source_event_ids=list(ins.source_event_ids),
        verified=verified,
        secondary=selection.secondary,
    )
