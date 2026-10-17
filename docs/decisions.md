# Design decisions

Short ADRs: context, options, decision, why. Newest last. Where a decision was later
changed, the original text stays and a dated **Outcome** or **Superseded** note says what
happened, so the reasoning at the time remains visible.

| ADR | Decision | Status |
|---|---|---|
| [001](#adr-001-python-backend-typescript-frontend) | Python backend (Agent Framework), TypeScript viewer | Accepted |
| [002](#adr-002-overlay-contract-first-ui-built-against-a-mock-replay) | Overlay contract first; UI built against a mock replay | Accepted |
| [003](#adr-003-schema-refinements-made-while-encoding-the-contract) | Schema refinements: op semantics, coordinates, foot-shot averages | Accepted; items 2–3 superseded by 004 |
| [004](#adr-004-adopt-the-claudeai-ui-prototype-as-the-viewer-inside-nextjs) | Port the UI prototype into Next.js; client-side personalization | Accepted |
| [005](#adr-005-synthetic-data-generator) | Synthetic generator: fictional league, hidden profiles, calibrated realism | Accepted |
| [006](#adr-006-personal-baselines-with-shrinkage) | Like-for-like baselines with empirical Bayes shrinkage, exact incremental state | Accepted |
| [007](#adr-007-chaos-injector-design) | Chaos injector: duplicates, reordering, late messages, corrections | Accepted |
| [008](#adr-008-multi-agent-architecture-for-narration) | Multi-agent workflow on Agent Framework with a deterministic verifier | Accepted |
| [009](#adr-009-deploy-on-azure-container-apps-with-scale-to-zero-and-keyless-foundry-access) | Container Apps, scale to zero, GHCR, managed identity for Foundry | Accepted |

---

## ADR-001: Python backend, TypeScript frontend

**Status:** Accepted (proposed 2026-10-16, confirmed 2026-10-17)

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

**Outcome (2026-10-17).** The agents run on Agent Framework 1.19 for Python
(`agent-framework-core` + `agent-framework-foundry`; ADR-008), and the stats engine's
property-based tests use `hypothesis`.

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

**Outcome (2026-10-17).** Done: the backend's Pydantic models live in
`backend/src/formline/schema/` (the old `models.py` is gone), `formline-gen` exports
`docs/contracts/overlay.schema.json`, and `backend/tests/test_overlay_contract.py` checks
the overlays against it. The backend now emits the overlays the viewer renders.

---

## ADR-003: Schema refinements made while encoding the contract

**Status:** Accepted (2026-10-16). Items 2 and 3 superseded by ADR-004 (generic slots,
client-side personalization).

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
   and late corrections come from the chaos injector (ADR-007), not from the generator.
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

**Accuracy (task 8).** Against the generator's hidden truth (population means from 300
extra simulated matches), shrunk baselines cut the RMSE of raw averages by 30% overall
(4.11 → 2.87 km/h) and by 45% for players with 1–4 shots. The fitted k is somewhat low
(forwards 2.2 vs 3.9 implied by the truth), so the smallest samples are slightly
under-shrunk; see `docs/shrinkage-accuracy.md`.

**Finding worth reporting.** PSxG gets the maximum k (50): players differ very
little in finishing relative to shot-to-shot noise. That matches the public
analytics view that finishing skill is hard to detect, and it is why finishing
insights must be worded cautiously.

---

## ADR-007: Chaos injector design

**Status:** Accepted (2026-10-17)

**Context.** The project plan requires the pipeline to survive what real feeds deliver:
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
4. **Never drop messages.** Missing-data inference is out of scope in the project plan, and a
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

**Result (task 7).** `python -m formline.convergence --runs 300`: baselines equal the
rebuild from the log in 300/300 chaotic replays, equal the clean run in 107/107 runs
without injected corrections or deletes, and insights equal the clean run in 57/57 runs
that also had no beyond-window late messages. Property-based tests (`hypothesis`, 140
random configurations per test run) check the same three properties.

---

## ADR-008: Multi-agent architecture for narration

**Status:** Accepted (2026-10-17)

**Context.** Engine insights (deterministic, ADR-006) must become timed overlay cards in
EN/JA × casual/analyst. LLM text is the most fluent option and the target category is Best
Multi-Agent Orchestration, but an LLM can misstate numbers, name the wrong player or claim
certainty. Every number on screen must be traceable to the engine.

**Options.**
- (a) One LLM call per card that does everything (choose, write, format).
- (b) Templates only, no LLM.
- (c) Several agents with narrow jobs on Microsoft Agent Framework, with deterministic
  guardrails between them.

**Decision.** (c), as a `WorkflowBuilder` graph (`backend/src/formline/agents/workflow.py`):

```
Moment ─► Selector ─fan-out─► 4 × Narrator (EN/JA × casual/analyst) ─► Verifier ─switch─┬─ ok ─────► Composer ─► Collector
                                                                                         ├─ retry ──► same Narrator, with feedback
                                                                                         └─ give up ► TemplateFallback ─► Composer
```

**Why each role is what it is.**
1. **Insight Selector: hybrid.** Rules build a shortlist (salience, one card per shot,
   per-player cooldown, rate limit); the LLM picks one id and gives a reason through a
   JSON contract; invalid output falls back to the top candidate. The decision is a real
   agent choice, but it can never surface something the rules didn't allow.
2. **Narrator: LLM, one call per variant.** It sees only the facts, the player's name, the
   comparison level and the length limits, and returns `{tag, headline, sub}`. Writing JA
   directly from facts (not translating EN) keeps both languages checkable.
3. **Verifier: deterministic.** Numbers by kind, entities, estimate wording, certainty
   claims, language, structure. Being deterministic makes it measurable (99.6% catch rate,
   0 false positives) and its failure details double as retry feedback.
4. **Overlay Composer: deterministic.** `bars` and `rows` are built from facts by the
   catalog, so card numbers are correct by construction; the LLM never produces them.
5. **TemplateFallback.** After 3 failed attempts the deterministic template narration is
   used; it always verifies. A card is never blocked and never wrong.

**Failure recovery.** Bad JSON, timeouts, network errors and an exhausted call budget become
verifier failures (retry, then template); a selector failure falls back to rules. Tested
with fake models that are wrong on the first attempt, return garbage, or always time out.

**Corrections reuse the graph.** When an insight is corrected (the VAR overturn), the new
insight is sent through the same workflow as a forced selection and re-issued as
`op: correct`; retracted insights get `op: retract`; a banner cites the shot and the VAR
events (`agents/live.py`).

**Cost and reproducibility.** A response cache keyed by prompt version, model, agent,
instructions and input; a per-run call budget; temperature 0.2. The live match's overlays
are precomputed once (`formline-gen overlays`, decision D3) and replayed with the feed;
`?live=true` runs the workflow during the replay to show it working. A rerun makes no
model calls.

**One code path, with or without Azure.** `FoundryChatClient` when a Foundry project is
configured, otherwise a fake client built on Agent Framework's `BaseChatClient`, so tests,
CI and offline demos exercise exactly the same `Agent.run` path.

**Known tuning item.** At 40:12 the Selector picks a placement insight (salience 0.55)
over the flagship speed insight (0.49): correct by salience, but the demo story is speed.
**Update (2026-10-17):** kept, since the speed gap is modest. Instead, "my metric" now
reveals the other metric's insight (secondary insights, below).

**Secondary insights (2026-10-17).** One card per shot for everyone meant "my metric" could
only hide cards. Each shown card now brings the best insight of the other overlay metric for
the same shot, narrated through the same workflow (a forced selection, like corrections) and
marked `secondary`; the viewer shows it only when "my metric" matches. Default viewers see
exactly what they saw before, secondaries skip cooldowns and rate limits, and lineage
corrects or retracts them like any card. Cost: 20 extra texts for the demo match.

---

## ADR-009: Deploy on Azure Container Apps with scale to zero and keyless Foundry access

**Status:** Accepted (2026-10-17)

**Context.** The brief asks for "an AI insights engine running on Azure", and the demo video
must show it on its target platform. The deployment has to be cheap for a solo entrant
(budget ¥3,000/month), secret-free in a public repo, repeatable from scripts, and able to
hold one long-lived SSE stream per viewer for a 90-minute match replayed at 20×.

**Options.**
- Hosting: (a) Azure Container Apps (consumption); (b) App Service; (c) AKS; (d) Static Web
  Apps for the viewer plus a separate API host.
- Images: (a) GitHub Container Registry; (b) Azure Container Registry.
- Model auth: (a) API keys in app settings or Key Vault; (b) managed identity with Entra ID roles.
- Event log store: (a) the JSONL log baked into the image; (b) Azure Database for PostgreSQL
  Flexible Server.

**Decision.**
- **Container Apps for both apps**, in one environment (`formline-env`), min 0 / max 1
  replicas: backend 0.5 vCPU / 1 GiB, viewer 0.25 vCPU / 0.5 GiB. Idle apps cost nothing;
  `stop.sh` disables ingress so not even bots can wake them; `start.sh` restores the same URLs.
- **GHCR, public packages**, published by CI on `main` as `linux/amd64` images tagged with the
  commit SHA (the dev Mac builds arm64, which Container Apps can't run). No registry
  credentials anywhere, and ACR's daily charge is avoided.
- **Managed identity, no keys.** `DefaultAzureCredential` uses `az login` locally and the
  backend's system-assigned identity in Azure. The identity gets **"Foundry User"** on the
  Foundry resource (`deploy.sh` assigns it).
- **JSONL, not Postgres.** The season (~28 MB, deterministic) is generated at image build
  time; precomputed Foundry overlays ship in `backend/demo/overlays/`. The event log
  interface still allows Postgres later.
- **Japan East** for everything: in the cheapest Container Apps price tier and closest to
  the owner; Global Standard model deployments cost the same in every region.
- **Model:** `gpt-4.1-mini` (Global Standard, 50k TPM rate limit). The agents' jobs are
  short JSON-contract calls checked by a deterministic verifier, so a small model is enough;
  a full narration run of the live match costs about ¥1.
- **Scripts over IaC for now:** `provision.sh`, `deploy.sh <sha>`, `stop.sh`, `start.sh`,
  `teardown.sh` are idempotent `az` scripts; Bicep + `azd` stays an optional task.

**Why.** Container Apps gives containers, HTTPS ingress, revisions, logs to Log Analytics and
true scale to zero with no cluster to run; AKS and App Service keep paying while idle. One
platform for both apps keeps one deploy flow. Keyless auth means the public repo and the
app settings contain nothing worth stealing.

**Findings worth recording.**
- **Foundry project endpoints need "Foundry User".** `FoundryChatClient` calls the project
  endpoint (`https://<resource>.services.ai.azure.com/api/projects/<project>`). With
  "Cognitive Services OpenAI User", "Azure AI Developer" or "Foundry Project Runtime User" it
  returned 403 with an empty body, while the classic OpenAI endpoint worked. Diagnosed with a
  direct `curl` using an Entra token; only "Foundry User" works. The other roles were removed.
- **Long SSE streams through ingress.** One viewer stream stopped after about four minutes
  ("Reconnecting…"); not yet confirmed as an ingress limit. Streams are now resumable: every
  message carries an SSE id, and on reconnect the browser sends `Last-Event-ID` and the
  backend continues after it, so a dropped connection costs nothing. The viewer's speed,
  pause and restart controls use the same mechanism (`start=mm:ss`).
- **Tests must never reach Azure.** `backend/.env` held the real endpoint, so the test suite
  briefly called Foundry (all calls were rejected, 0 tokens billed). `tests/conftest.py` now
  blanks the endpoint and a guard test asserts the fake client is used.

**Costs.** Measured so far: about ¥21 in model tokens for all narration runs; Container Apps
within the monthly free grant. A ¥3,000 budget alerts at 50% and 100%.

**Trade-offs.** A cold start after scale to zero takes a few seconds (warm the app before a
demo); max 1 replica means no high availability; JSONL baked into the image means data
changes need a new image. All acceptable for a demo, and each has a clear upgrade path
(min 1 replica, more replicas behind the same ingress, Postgres behind the event log interface).
