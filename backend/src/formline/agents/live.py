"""Live orchestration: feed messages in, timed overlays out, corrections included.

Per message: the engine pipeline (ingest → baselines → insights) runs first; new
insights from one shot form a moment and go through the agent workflow; insight
corrections and retractions go through the corrections path:

- a shown card whose insight was **corrected** is re-narrated through the same
  workflow (Narrator → Verifier → Composer) and re-issued as `op: correct`,
  superseding every variant of the old card;
- a shown card whose insight was **retracted** gets `op: retract` for every variant;
- one **correction banner** (all four variants) per corrected event, when a shown
  card was affected or a goal was overturned. Its lineage cites the shot and the VAR
  events that reviewed it.

Corrections are timed when they arrive (e.g. the VAR decision), not at the shot.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from formline.agents.cards import VARIANTS
from formline.agents.selector import Selection, priority_of
from formline.agents.template_narrator import narrate_correction
from formline.agents.verifier import VerifyContext, verify
from formline.agents.workflow import Deps, build_workflow, run_moment
from formline.engine.engine import BaselineEngine
from formline.engine.insights import (
    InsightChange,
    InsightCorrected,
    InsightCreated,
    InsightRetracted,
)
from formline.engine.pipeline import LivePipeline
from formline.schema.feed import FeedMessage
from formline.schema.overlay import Overlay, OverlaySlots

CORRECTION_DELAY_MS = 1_000
BANNER_TTL_MS = 4 * 60_000


@dataclass
class LiveSummary:
    moments: int = 0
    cards: int = 0
    corrected_cards: int = 0
    retracted_cards: int = 0
    banners: int = 0
    llm_texts: int = 0
    template_texts: int = 0


@dataclass
class LiveOrchestrator:
    engine: BaselineEngine  # bootstrapped with the history, priors frozen
    deps: Deps
    overlays: list[Overlay] = field(default_factory=list)  # everything emitted, in order
    summary: LiveSummary = field(default_factory=LiveSummary)

    def __post_init__(self) -> None:
        self.pipeline = LivePipeline(self.engine)
        self.workflow = build_workflow(self.deps)
        self.shown: dict[str, list[Overlay]] = {}  # insight_id -> current overlays
        self.reviews: dict[str, list[str]] = defaultdict(list)  # shot -> VAR event ids
        self.clock: tuple[int, int] = (1, 0)  # latest (period, match clock) seen
        self.banner_versions: dict[str, int] = {}  # shot -> banners issued so far
        self.withdrawn: dict[str, list[Overlay]] = {}  # insight_id -> retracted overlays

    # ---------- driving ----------

    async def process(self, msg: FeedMessage) -> list[Overlay]:
        start = len(self.overlays)
        if msg.event is not None and msg.op == "create":
            e = msg.event
            self.clock = max(self.clock, (e.period, e.match_clock_ms))
            if e.type.startswith("var_review"):
                for target in e.related_event_ids:
                    self.reviews[target].append(e.event_id)
        await self._handle(self.pipeline.process(msg))
        return self.overlays[start:]

    async def flush(self) -> list[Overlay]:
        start = len(self.overlays)
        await self._handle(self.pipeline.flush())
        return self.overlays[start:]

    async def run(self, feed: list[FeedMessage]) -> list[Overlay]:
        for msg in feed:
            await self.process(msg)
        await self.flush()
        return self.overlays

    async def _handle(self, changes: list[InsightChange]) -> None:
        moments: dict[str, list] = {}
        corrections: dict[str, list[InsightChange]] = defaultdict(list)
        for c in changes:
            if isinstance(c, InsightCreated) and c.insight.version == 1:
                moments.setdefault(c.insight.source_event_ids[0], []).append(c.insight)
            else:
                shot = (c.after if isinstance(c, InsightCorrected) else c.insight)
                corrections[shot.source_event_ids[0]].append(c)
        for candidates in moments.values():
            await self._show(candidates)
        for shot, group in corrections.items():
            await self._correct(shot, group)

    # ---------- show ----------

    async def _show(self, candidates) -> None:
        out = await run_moment(self.workflow, candidates, self.deps.selector_state)
        self.summary.moments += 1
        self._count_sources(out.cards)
        if out.cards:
            overlays = [c.overlay for c in out.cards]
            self.shown[out.selection.insight.insight_id] = overlays
            self.overlays += overlays
            self.summary.cards += len(overlays)

    def _count_sources(self, cards) -> None:
        for card in cards:
            self.summary.llm_texts += card.narration.source == "llm"
            self.summary.template_texts += card.narration.source == "template"

    # ---------- corrections ----------

    def _at(self) -> int:
        return self.clock[1] + CORRECTION_DELAY_MS

    async def _correct(self, shot: str, group: list[InsightChange]) -> None:
        affected = False
        for c in group:
            if isinstance(c, InsightCorrected) and c.before.insight_id in self.shown:
                await self._reissue(c)
                affected = True
            elif isinstance(c, InsightRetracted) and c.insight.insight_id in self.shown:
                self._retract(c.insight.insight_id)
                affected = True
            elif isinstance(c, InsightCreated) and c.insight.insight_id in self.withdrawn:
                await self._reshow(c.insight)  # notable again after a revert
                affected = True
        goal_overturned = any(
            (isinstance(c, InsightCorrected) and c.before.facts.get("outcome") == "goal"
             and c.after.facts.get("outcome") != "goal")
            or (isinstance(c, InsightRetracted) and c.insight.facts.get("outcome") == "goal")
            for c in group)
        if affected or goal_overturned:
            self._banner(shot, group)

    async def _reissue(self, c: InsightCorrected) -> None:
        old = self.shown.pop(c.before.insight_id)
        selection = Selection(c.after, min(o.priority for o in old) if old else
                              priority_of(c.after), f"correction: {c.reason}", "correction")
        out = await run_moment(self.workflow, [c.after], self.deps.selector_state,
                               forced=selection)
        self._count_sources(out.cards)
        by_variant = {(o.lang, o.audience_mode): o for o in old}
        corrected = []
        for card in out.cards:
            o = card.overlay
            previous = by_variant[(o.lang, o.audience_mode)]
            corrected.append(Overlay.model_validate(
                o.model_dump() | {"op": "correct", "supersedes_overlay_id": previous.overlay_id,
                                  "match_clock_ms": self._at()}))
        self.shown[c.after.insight_id] = corrected
        self.overlays += corrected
        self.summary.corrected_cards += len(corrected)

    async def _reshow(self, insight) -> None:
        old = self.withdrawn.pop(insight.insight_id)
        selection = Selection(insight, min(o.priority for o in old), "notable again after a "
                              "correction", "correction")
        out = await run_moment(self.workflow, [insight], self.deps.selector_state,
                               forced=selection)
        shown = [Overlay.model_validate(c.overlay.model_dump() | {"match_clock_ms": self._at()})
                 for c in out.cards]
        self.shown[insight.insight_id] = shown
        self.overlays += shown
        self.summary.cards += len(shown)

    def _retract(self, insight_id: str) -> None:
        self.withdrawn[insight_id] = self.shown[insight_id]
        for o in self.shown.pop(insight_id):
            self.overlays.append(Overlay.model_validate(
                o.model_dump() | {"overlay_id": f"{o.overlay_id}_retract", "op": "retract",
                                  "supersedes_overlay_id": o.overlay_id, "ttl_ms": 0,
                                  "match_clock_ms": self._at(), "verified": True,
                                  "slots": {"tag": "", "headline": ""}}))
            self.summary.retracted_cards += 1

    def _banner(self, shot: str, group: list[InsightChange]) -> None:
        withdrawn = sum(isinstance(c, InsightRetracted) for c in group)
        updated = sum(isinstance(c, InsightCorrected) for c in group)
        insight = group[0].after if isinstance(group[0], InsightCorrected) else group[0].insight
        sources = [shot, *self.reviews.get(shot, [])]
        # A later correction of the same shot (e.g. a revert) replaces its earlier banner.
        version = self.banner_versions.get(shot, 0) + 1
        self.banner_versions[shot] = version

        def banner_id(lang: str, mode: str, v: int) -> str:
            base = f"ovl_banner_{shot}_{lang}_{mode}"
            return base if v == 1 else f"{base}_v{v}"

        for lang, mode in VARIANTS:
            text = vars(narrate_correction(group, lang, mode))
            ctx = VerifyContext("correction_banner", lang, mode,
                                extra_numbers=frozenset({str(withdrawn), str(updated)}))
            verified = verify(text, ctx, self.deps.league).ok
            self.overlays.append(Overlay(
                overlay_id=banner_id(lang, mode, version),
                op="show" if version == 1 else "correct",
                supersedes_overlay_id=None if version == 1 else banner_id(lang, mode,
                                                                          version - 1),
                match_clock_ms=self._at(), ttl_ms=BANNER_TTL_MS,
                template_id="correction_banner", priority=1, audience_mode=mode, lang=lang,
                slots=OverlaySlots(**text), insight_id=insight.insight_id, player_id=None,
                metric=None, source_event_ids=sources, verified=verified))
            self.summary.banners += 1
