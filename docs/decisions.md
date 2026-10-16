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

---

## ADR-004: Adopt the claude.ai UI prototype as the viewer, inside Next.js

**Status:** Accepted (2026-10-16). Supersedes ADR-003 items 2 and 3, and replaces the
step-2 viewer (`docs/ui-step-2-pitch-and-clock.md`).

**Context.** A separate design session produced a complete Vite + React viewer
(`formline-ui`): live viewer, two-viewer page, settings panel, focus strip,
overlay log, VAR withdrawal, phone layout and 8 logic tests. It covers UI steps
3–5, which were still unbuilt here. Its types are simpler than
`frontend/src/contract/`.

**Options.**
- (a) Keep Vite and replace `frontend/` with the prototype as is.
- (b) Port the prototype into the existing Next.js app, adopting its types.
- (c) Port only its components and re-fit them to the richer ADR-003 contract.

**Decision.** (b).

**Why.** It gets the finished UI in about an hour, where (c) would mean
rewriting most of it. Keeping Next.js leaves the existing scaffold, lint and
CI setup intact, and a later server route (e.g. an SSE proxy) has an obvious home.
The UI only needs the fields it renders, so the full feed envelope and typed
template slots now belong to the backend's Pydantic models.

**What changed.**
1. **Stream contract** is `StreamMessage` (`frontend/src/lib/types.ts`):
   `{kind:'event'}` or `{kind:'overlay'}` per SSE `data:` line. Events carry
   `version`; the client keeps the highest version per `event_id`.
2. **Generic slots.** Overlays use one slot shape: `tag`, `headline`, `sub`,
   with `bars` for casual and `rows` for analyst. Density still differs by
   mode, but the template catalog is enforced by the backend, not by TS types.
3. **Personalization is client-side for now.** The stream carries every
   EN/JA × casual/analyst variant, and `personalize()` filters per viewer. The
   rules are pure and unit-tested. Moving the filter to the backend later
   doesn't change the contract.
4. **Overlay gains `player_id` and `metric`**, so favorites and "my metric"
   can filter without parsing slots (`DATA_SCHEMA.md` §6.5 updated).
5. **Tailwind removed.** The prototype uses one plain stylesheet with design
   tokens (`frontend/src/app/globals.css`). Fonts load through `next/font`.
6. Kept from step 2: `?t=mm:ss` opens the mock replay at that moment.

---

## ADR-005: Synthetic data generator

**Status:** Accepted (2026-10-17)

**Context.** The engine needs a season of history (so every regular shooter has a
baseline) and one live match with guaranteed demo moments. The data must be
synthetic but look like a real provider feed.

**Options.**
- (a) Independent random events per type with tuned frequencies.
- (b) A possession-chain simulator driven by hidden per-player profiles.
- (c) Replay a hand-written match only.

**Decision.** (b), plus scripted beats for the live match.

**Why.** Chains give realistic sequences for free: possession numbers,
`key_pass_event_id`, shots clustered after final-third receptions, restarts that
follow from outcomes. Hidden profiles (GEN-ONLY) give each player a stable "true"
style, so we can later measure how well shrinkage recovers it, which (a) and (c)
cannot do.

**Details.**
1. **League.** 6 fictional clubs × 18 players (4-3-3 plus 7 subs). The UI's
   named players keep their ids (`ply_0107` Reyner and the rest). 30 past matches
   (double round robin) and 1 live match (HAR vs NOR).
2. **Profile definition.** `shot_power_mean_kmh` is a strong-foot, unpressured
   shot from 16 m. Real shots are closer, sometimes pressured or weak-foot, so raw
   averages sit 6–9 km/h below it. This is intended: it is exactly why baselines
   must compare like with like.
3. **Live match is scripted where it matters.** Six beats (the UI storyline) are
   pinned at fixed clock times, and the clock never skips past a beat. Unscripted
   shots in the live match never score, so the score is fixed: 1–0 after VAR
   cancels Reyner's 63:42 goal (`var_review_start`/`end`, then the shot re-sent
   as version 2 with `outcome: off_target`). History matches are unscripted.
4. **Derived, not asserted.** `under_pressure` on a shot is computed from the
   freeze frame (a defender within 2.3 m), so the flag and the frame never disagree.
5. **Clean feed.** Each event becomes a `create` envelope emitted 250–900 ms
   after the action, so messages are already slightly out of event order. Duplicates
   and late corrections come from the chaos injector later, not from the generator.
6. **Generated data is not committed.** One seed (2026) reproduces it exactly
   (about 28 MB). `backend/data/sample/` (league, matches, a live-feed excerpt
   with the VAR sequence) is committed so readers can see the format.
7. **Calibration.** Checked against public 2024/25 league aggregates in
   `docs/realism-report.md`; a test fails if any metric leaves its range.
8. **Revised in task 2 (shot features).** Computing distances exposed that 35% of
   shots came from the six-yard box (median 11 m). Open-play passes now stop short
   of the six-yard box, crosses land shallower, and shot probability rises more
   gently near goal: now 9% six-yard, median 14 m, 69% inside the box. Two
   location checks were added to the realism report.

---

## ADR-006: Personal baselines with shrinkage

**Status:** Accepted (2026-10-17)

**Context.** The flagship insight compares each shot with the shooter's own
history. A striker has ~35 shots a season, so like-for-like buckets (zone × body
part × pressure) hold only a handful of shots each, and corrections (VAR) must
roll a shot back out of every bucket.

**Decisions.**
1. **Fallback ladder.** zone × body × pressure → zone × body → area × body →
   body. Use the most specific level with ≥ 5 shots and report which level was
   used, so the narrator never claims "from this spot" when it compared all
   strong-foot shots. 5, not 8: with 8, even the busiest strikers rarely got a
   zone-level comparison.
2. **Exact fixed-point buckets.** Values are stored as integers (speed × 10,
   placement × 1000, PSxG × 10000) in sorted lists with integer sums. Add and
   remove are exact and order-independent, so corrections need no recompute and
   a chaotic stream can be checked for *exact* equality with a clean one.
   Alternative considered: Welford running variance with removal; rejected
   because floating-point drift makes the result depend on arrival order.
3. **Empirical Bayes shrinkage.** Normal–normal model per metric × position group
   × body part: shrunk = (n·x̄ + k·prior) / (n + k), k = σ²/τ², with σ² (shot to
   shot) and τ² (player to player) estimated by method of moments from the
   history. The prior is the group's mean **at the same ladder level, excluding
   the player**. Fallback when a group has too few players: the same body part
   across all groups (never across body parts: headers must not inherit a
   foot-shot spread or mean). k is capped at 50.
4. **Priors are fitted once and frozen** after the historical bootstrap, so live
   updates and corrections stay exact and deterministic.
5. **Percentiles are model estimates** from N(shrunk, σ² + σ²/(n+k)), clipped to
   1–99, shown next to the raw rank. Example: Okafor's pressured header ranks last
   of 5 raw shots, but is estimated at the 59th percentile after shrinkage.

**Finding worth reporting.** PSxG gets the maximum k (50): players differ very
little in finishing relative to shot-to-shot noise. That matches the public
analytics view that finishing skill is hard to detect, and it is why finishing
insights must be worded cautiously.

---

## ADR-007: Chaos injector design

**Status:** Accepted (2026-10-17)

**Context.** `CLAUDE.md` requires the pipeline to survive what real feeds deliver:
duplicates, late and out-of-order messages, and corrections. We need a way to produce
such feeds on demand, both for property-based convergence tests and to show the
pipeline coping live in the demo.

**Options.**
- (a) Bake the damage into the generator's output files.
- (b) A separate transform that damages delivery of a clean feed at replay time.
- (c) Randomly mutate messages (drop fields, corrupt values).

**Decision.** (b): `formline/chaos.py`, `inject(feed, ChaosConfig) -> (messages, report)`,
plugged into `replay(..., transform=...)` and exposed as `?chaos=true&chaos_seed=N`.

**Why.** The clean feed stays the reference, so every chaotic run can be compared with
it. The same match can be replayed clean or chaotic, which is exactly what a
convergence test and a side-by-side demo need. (c) tests input validation, not feed
robustness, and creates states no provider would send.

**Design choices.**
1. **Damage delivery, not content.** Each message gets an arrival time (its
   `emitted_at`); the injector perturbs arrival times and delivers in arrival order.
   The provider's `emitted_at` and `sequence` stay on each message, as they would in
   reality. The only new content is injected corrections, which real feeds also send.
2. **Five damage types with configurable rates** (defaults in brackets): duplicate
   (3%), in-window reorder of 0.2–3 s (5%), beyond-window delay of 6–30 s (1%), shot
   correction (15% of eligible shots) with revert (50% of corrections), and delete
   (0%, opt-in). Reorder and late are separate on purpose: one exercises the
   reorder buffer, the other the late-arrival and correction path.
3. **Realistic corrections.** A correction is a new version of a shot with the outcome
   swapped (goal → saved, saved → off target, …) or, 30% of the time, a different
   shooter from the same team (attribution fix). A revert is a further version that
   restores the original payload exactly, modelling "temporary" then "final" event
   files.
4. **Never drop messages.** Missing-data inference is out of scope in `CLAUDE.md`, and a
   dropped message makes "convergence" undefined (the truth is no longer in the log).
5. **Leave real updates alone.** Shots that already have an update (the VAR overturn)
   are never given injected corrections, so injected and real versions cannot collide
   and the demo storyline always survives chaos.
6. **Deterministic per seed.** `random.Random(f"chaos:{seed}")`, and a tiebreak counter
   for equal arrival times, so any failing convergence case can be replayed exactly
   from its seed.
7. **Report what was injected.** `ChaosReport` counts each damage type and lists the
   corrected event ids, so tests can check rates and the README can quote numbers.

**What "converged" means (used by the convergence tests).** The truth is the final
version of every event in the append-only log (`current_events`). A chaotic run has
converged when its incrementally built state equals a rebuild from that truth. Without
injected corrections, the truth equals the clean feed, so the state must also equal
the clean run's.

**Observed on the live match (seed 1).** 1,324 messages in, 1,386 out: 51 duplicates,
60 reordered, 12 delayed, 6 corrections, 5 reverts. The ingestor dropped all 51
duplicates and produced 12 revisions. 9 of the 12 delayed messages crossed the
watermark; 3 landed inside it because the watermark follows the latest event time and
quiet spells leave room. "Late" is therefore a property of arrival relative to the
stream, not of the delay alone.
