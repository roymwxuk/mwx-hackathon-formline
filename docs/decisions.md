# Design decisions

Short ADRs: context, options, decision, why. Newest last.

---

## ADR-001: Python backend, TypeScript frontend

**Status:** Proposed (2026-10-16)

**Context.** The owner is strongest in TypeScript. The multi-agent category names
Microsoft Agent Framework, which ships SDKs for Python and .NET, not TypeScript.

**Options.**
- (a) Python for the agent layer and stats engine, TypeScript for the viewer UI.
- (b) TypeScript throughout, with hand-rolled orchestration on Azure OpenAI via Foundry.

**Decision.** (a).

**Why.** Using Agent Framework directly is the most credible path for the
multi-agent category, and the stats work (shrinkage, property-based convergence
tests) has better Python tooling. The UI stays TypeScript, where the owner is
fastest. The cost is keeping one contract in sync across two languages; see ADR-002.

---

## ADR-002: Overlay contract first, UI built against a mock replay

**Status:** Accepted (2026-10-16)

**Context.** The viewer UI is 20% of the score and the pipeline should be visible
end to end early, but the backend does not yet emit overlays.

**Decision.** Encode `DATA_SCHEMA.md` §2–6.5 as TypeScript types
(`frontend/src/contract/`) and build the UI against a hand-written replay
(`frontend/src/mock/demo-match.ts`). Contract tests check the mock's invariants:
ordering, lineage, supersession, VAR retraction, and estimate wording. The
backend must produce streams that pass the same checks.

**Why.** It decouples UI work from engine progress and makes the contract the
spec. Follow-up: generate JSON Schema from the backend's Pydantic models and
validate against it, so the two languages cannot drift. The current
`backend/src/formline/models.py` predates `DATA_SCHEMA.md` and must be rewritten.

---

## ADR-003: Schema refinements made while encoding the contract

**Status:** Accepted (2026-10-16)

Changes against `DATA_SCHEMA.md` v0.2:

1. **Overlay op semantics.** `show` + `supersedes_overlay_id` = state moved on
   (e.g. a refreshed player strip). `correct` = the source data was corrected.
   `retract` = remove; it carries no template or slots. This separates normal
   updates from data corrections, which matters for audit and for the demo.
2. **Typed template slots.** Each `template_id` has its own slot shape
   (`shot_speed_card`, `baseline_percentile_card`, `chance_vs_norm_card`,
   `correction_banner`, `player_focus_strip`). Analyst mode adds optional
   `details` rows, so the two modes differ in density, not only in tone.
3. **Personalization happens server-side.** The backend emits one overlay stream
   per viewer profile. The frontend renders and never filters, so "which insights
   appear" is a pipeline decision that can be logged and tested.
4. **Player strip averages foot shots only.** Headers would distort shot-speed
   comparisons.
5. **Coordinates.** Each team's events are normalized to attack toward x = 100.
   Renderers flip the away team.
