"""The multi-agent workflow on Microsoft Agent Framework.

One run handles one "moment" (the insights from one shot) and returns up to four
verified overlays:

    Moment ─► Selector ─fan-out─► Narrator[en·casual]  ┐
                                  Narrator[en·analyst] ├─► Verifier ─switch─┬─ ok ─────────► Composer ─► Collector ─► output
                                  Narrator[ja·casual]  │                    ├─ retry ──────► the same Narrator (with feedback)
                                  Narrator[ja·analyst] ┘                    └─ give up ────► TemplateFallback ─► Composer

- Distinct roles: each executor has one job and a typed input/output message.
- Shared state: the workflow context holds the run's trace and the collected cards.
- Explicit handoffs: every edge is declared in `build_workflow()`; the retry loop is a
  cycle routed by a switch-case edge group, not hidden inside a function.
- Failure recovery: model errors (timeouts, bad JSON, exhausted budget) become verifier
  failures, so they retry and then fall back to the deterministic template; the
  selector falls back to rules. A run always completes.
"""

import json
import logging
from dataclasses import dataclass, field

from agent_framework import Case, Default, Executor, Workflow, WorkflowBuilder, handler

from formline.agents.cards import VARIANTS, Card
from formline.agents.catalog import TEMPLATE_FOR_INSIGHT
from formline.agents.composer import compose
from formline.agents.llm import LLMRunner
from formline.agents.narrator import MAX_ATTEMPTS, Narration, NarrationParseError, narrate_once
from formline.agents.selector import Selection, SelectorState, priority_of, select, shortlist
from formline.agents.template_narrator import Names, narrate
from formline.agents.verifier import LeagueNames, VerifyContext, verify
from formline.engine.insights import Insight

log = logging.getLogger("formline.workflow")


# ---------- messages (the typed handoffs between agents) ----------

@dataclass(frozen=True)
class Moment:
    candidates: list[Insight]


@dataclass(frozen=True)
class Draft:
    selection: Selection
    lang: str
    mode: str
    attempt: int  # model attempts made so far for this variant
    failures: tuple[str, ...]
    slots: dict | None
    error: str | None = None


@dataclass(frozen=True)
class Checked:
    selection: Selection
    lang: str
    mode: str
    attempt: int
    failures: tuple[str, ...]
    slots: dict | None
    ok: bool
    feedback: str | None
    source: str = "llm"  # "llm" or "template"


@dataclass(frozen=True)
class MomentResult:
    selection: Selection | None
    cards: list[Card]
    trace: list[dict]


@dataclass
class Deps:
    """What the agents share: the model runner, names and the selector's memory."""

    runner: LLMRunner
    league: LeagueNames
    names: dict[str, Names]
    selector_state: SelectorState = field(default_factory=SelectorState)


def _trace(ctx, executor: str, event: str, **detail) -> None:
    entry = {"executor": executor, "event": event, **detail}
    ctx.set_state("trace", [*ctx.get_state("trace", []), entry])
    log.info(json.dumps(entry, ensure_ascii=False, default=str))


def _variant_id(lang: str, mode: str) -> str:
    return f"narrator_{lang}_{mode}"


# ---------- executors (the agents) ----------

class SelectorExecutor(Executor):
    def __init__(self, deps: Deps):
        super().__init__(id="insight_selector")
        self.deps = deps

    @handler(input=Moment, output=Selection, workflow_output=MomentResult)
    async def choose(self, moment, ctx) -> None:
        ctx.set_state("trace", [])
        ctx.set_state("cards", [])
        en_names = {pid: n.en for pid, n in self.deps.names.items()}
        try:
            selection = await select(moment.candidates, self.deps.selector_state,
                                     self.deps.runner, en_names)
        except Exception as exc:  # noqa: BLE001 - any model failure: the rules still decide
            short = shortlist(moment.candidates, self.deps.selector_state)
            selection = Selection(short[0], priority_of(short[0]), f"fallback: {exc}",
                                  "rules") if short else None
        if selection is None:
            _trace(ctx, self.id, "nothing_selected", candidates=len(moment.candidates))
            await ctx.yield_output(MomentResult(None, [], ctx.get_state("trace")))
            return
        _trace(ctx, self.id, "selected", insight=selection.insight.insight_id,
               decided_by=selection.decided_by, reason=selection.reason)
        await ctx.send_message(selection)


class NarratorExecutor(Executor):
    def __init__(self, deps: Deps, lang: str, mode: str):
        super().__init__(id=_variant_id(lang, mode))
        self.deps, self.lang, self.mode = deps, lang, mode

    async def _draft(self, selection: Selection, attempt: int, failures: tuple[str, ...],
                     feedback: str | None, ctx) -> None:
        ins = selection.insight
        try:
            slots = await narrate_once(ins, self.lang, self.mode, self.deps.names[ins.player_id],
                                       self.deps.runner, feedback)
            error = None
        except NarrationParseError as exc:
            slots, error = None, f"[format] {exc}; reply with the JSON object only"
        except Exception as exc:  # noqa: BLE001 - timeout/network/budget = failed attempt
            slots, error = None, f"[model] {type(exc).__name__}: {exc}"
        _trace(ctx, self.id, "drafted", attempt=attempt + 1, error=error)
        await ctx.send_message(Draft(selection, self.lang, self.mode, attempt + 1, failures,
                                     slots, error))

    @handler(input=Selection, output=Draft)
    async def first(self, selection, ctx) -> None:
        await self._draft(selection, 0, (), None, ctx)

    @handler(input=Checked, output=Draft)
    async def retry(self, checked, ctx) -> None:
        await self._draft(checked.selection, checked.attempt,
                          (*checked.failures, checked.feedback), checked.feedback, ctx)


class VerifierExecutor(Executor):
    def __init__(self, deps: Deps):
        super().__init__(id="verifier")
        self.deps = deps

    @handler(input=Draft, output=Checked)
    async def check(self, draft, ctx) -> None:
        ins = draft.selection.insight
        if draft.slots is None:
            ok, feedback = False, f"- {draft.error}"
        else:
            vctx = VerifyContext(TEMPLATE_FOR_INSIGHT[ins.type], draft.lang, draft.mode,
                                 ins.facts, ins.player_id)
            verdict = verify(draft.slots, vctx, self.deps.league)
            ok, feedback = verdict.ok, (None if verdict.ok else verdict.feedback())
        _trace(ctx, self.id, "passed" if ok else "rejected", variant=f"{draft.lang}_{draft.mode}",
               attempt=draft.attempt, feedback=feedback)
        await ctx.send_message(Checked(draft.selection, draft.lang, draft.mode, draft.attempt,
                                       draft.failures, draft.slots, ok, feedback))


class TemplateFallbackExecutor(Executor):
    def __init__(self, deps: Deps):
        super().__init__(id="template_fallback")
        self.deps = deps

    @handler(input=Checked, output=Checked)
    async def fallback(self, checked, ctx) -> None:
        ins = checked.selection.insight
        slots = vars(narrate(ins, checked.lang, checked.mode, self.deps.names[ins.player_id]))
        _trace(ctx, self.id, "template_used", variant=f"{checked.lang}_{checked.mode}",
               attempts=checked.attempt)
        await ctx.send_message(Checked(checked.selection, checked.lang, checked.mode,
                                       checked.attempt, (*checked.failures, checked.feedback),
                                       slots, True, None, source="template"))


class ComposerExecutor(Executor):
    def __init__(self):
        super().__init__(id="overlay_composer")

    @handler(input=Checked, output=Card)
    async def build(self, checked, ctx) -> None:
        overlay = compose(checked.selection, checked.lang, checked.mode, checked.slots)
        narration = Narration({k: checked.slots[k] for k in ("tag", "headline", "sub")},
                              checked.source, checked.attempt, checked.failures)
        _trace(ctx, self.id, "composed", overlay=overlay.overlay_id, source=checked.source)
        await ctx.send_message(Card(overlay, narration))


class CollectorExecutor(Executor):
    def __init__(self):
        super().__init__(id="collector")

    @handler(input=Card, workflow_output=MomentResult)
    async def collect(self, card, ctx) -> None:
        cards = [*ctx.get_state("cards", []), card]
        ctx.set_state("cards", cards)
        if len(cards) == len(VARIANTS):
            order = {v: i for i, v in enumerate(VARIANTS)}
            cards.sort(key=lambda c: order[(c.overlay.lang, c.overlay.audience_mode)])
            selection = next(iter(cards)).overlay.insight_id
            _trace(ctx, self.id, "moment_done", insight=selection)
            await ctx.yield_output(MomentResult(None, cards, ctx.get_state("trace")))


# ---------- the graph ----------

def build_workflow(deps: Deps) -> Workflow:
    selector = SelectorExecutor(deps)
    narrators = {(lang, mode): NarratorExecutor(deps, lang, mode) for lang, mode in VARIANTS}
    verifier = VerifierExecutor(deps)
    fallback = TemplateFallbackExecutor(deps)
    composer = ComposerExecutor()
    collector = CollectorExecutor()

    def retry_to(lang: str, mode: str):
        return lambda c: not c.ok and c.attempt < MAX_ATTEMPTS and (c.lang, c.mode) == (lang, mode)

    builder = WorkflowBuilder(start_executor=selector, name="formline_cards",
                              description="Insight → verified EN/JA casual/analyst overlays")
    builder.add_fan_out_edges(selector, list(narrators.values()))
    for narrator in narrators.values():
        builder.add_edge(narrator, verifier)
    builder.add_switch_case_edge_group(verifier, [
        Case(lambda c: c.ok, composer),
        *(Case(retry_to(lang, mode), narrator) for (lang, mode), narrator in narrators.items()),
        Default(fallback),
    ])
    builder.add_edge(fallback, composer)
    builder.add_edge(composer, collector)
    return builder.build()


async def run_moment(workflow: Workflow, candidates: list[Insight],
                     selector_state: SelectorState) -> MomentResult:
    result = await workflow.run(Moment(candidates))
    outputs = result.get_outputs()
    out = outputs[-1] if outputs else MomentResult(None, [], [])
    if out.cards:  # attach the selection decided in this run
        chosen = next(e for e in out.trace if e["event"] == "selected")
        insight = next(i for i in candidates if i.insight_id == chosen["insight"])
        out = MomentResult(Selection(insight, out.cards[0].overlay.priority, chosen["reason"],
                                     chosen["decided_by"]), out.cards, out.trace)
    return out


# ---------- a whole match ----------

@dataclass
class RunSummary:
    moments: int = 0
    selected: int = 0
    selector_llm: int = 0
    selector_rules: int = 0
    cards: int = 0
    llm_texts: int = 0
    template_texts: int = 0
    retried_texts: int = 0
    model_calls: int = 0
    cache_hits: int = 0


async def run_match(insights: list[Insight], deps: Deps) -> tuple[list[MomentResult], RunSummary]:
    """Run the workflow over a match's insights, one moment (shot) at a time, in order."""
    workflow = build_workflow(deps)
    moments: dict[str, list[Insight]] = {}
    for ins in sorted(insights, key=lambda i: (i.period, i.match_clock_ms, i.insight_id)):
        moments.setdefault(ins.source_event_ids[0], []).append(ins)
    results, summary = [], RunSummary()
    for candidates in moments.values():
        out = await run_moment(workflow, candidates, deps.selector_state)
        results.append(out)
        summary.moments += 1
        if out.selection:
            summary.selected += 1
            summary.selector_llm += out.selection.decided_by == "llm"
            summary.selector_rules += out.selection.decided_by == "rules"
        for card in out.cards:
            summary.cards += 1
            summary.llm_texts += card.narration.source == "llm"
            summary.template_texts += card.narration.source == "template"
            summary.retried_texts += card.narration.attempts > 1
    summary.model_calls = deps.runner.budget.calls
    summary.cache_hits = deps.runner.cache_hits
    return results, summary
