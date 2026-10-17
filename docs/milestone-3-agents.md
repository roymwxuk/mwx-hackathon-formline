# Milestone 3: agents and overlays

**Status:** In progress. Tasks 1–4, 6 and 7 done; task 5 done except the Azure steps (2026-10-17)
**Branch:** `feat/agents`, to be built on `feat/engine`
**Planned:** Oct 16–19 in `CLAUDE.md`, so about a day late. Deadline: submit Oct 26 (JST).
**Estimate:** about 11–14 h for MUST and SHOULD items. COULD items only if time allows.

## Goal

Turn the engine's insights (milestone 2) into **verified, timed, personalized overlay
cards** that the viewer renders, using a **multi-agent workflow** on Microsoft Agent
Framework. The target category is Best Multi-Agent Orchestration: distinct roles, shared
state, explicit handoffs, failure recovery.

```
engine insights ──► Insight Selector ──► Narrator ──► Verifier ──pass──► Overlay Composer ──► SSE stream ──► viewer
 (+ corrections)      (what & when)      (EN/JA ×      (numbers,   │                (catalog template,
                                          casual/        entities,  └─fail─► retry Narrator with feedback
                                          analyst)       wording)          └─after N fails─► template fallback
```

The LLM only **words** what the deterministic engine found. Every number in a card must
come from `Insight.facts`, and the verifier enforces it. This reuses the owner's prior
pattern (LLM output through a JSON contract, layered guardrails).

**Grounded in the installed SDK:** `agent-framework` 1.19.0 provides `Agent(client,
instructions, ...)`, `WorkflowBuilder` (`add_edge`, `add_switch_case_edge_group`,
`add_fan_out_edges`, `add_fan_in_edges`, checkpoints), `Executor`, `FoundryChatClient`,
`OpenAIChatClient`, orchestration builders (`SequentialBuilder`, `ConcurrentBuilder`,
`HandoffBuilder`, `MagenticBuilder`) and `FoundryEvals`.

---

## Decisions to make first

Each needs an answer before the related task starts. Recommendations are marked ★.

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | **Model and provider** | (a) Azure OpenAI or Foundry model via `FoundryChatClient`; (b) OpenAI directly | ★ (a): a small, cheap deployment (e.g. a "mini" model) in Microsoft Foundry. Azure tech counts for judging, and it's cheap at demo volume. A **fake client** for tests and offline runs. |
| D2 | **Is the Selector an LLM?** | (a) rules only; (b) LLM picks from a rule-built shortlist; (c) LLM only | ★ (b): rules build a shortlist (salience, cooldowns, priority) and the LLM picks and justifies within a JSON contract, falling back to the top-ranked item. That makes it a real agent decision while staying explainable and safe. |
| D3 | **Live narration or precomputed?** | (a) call the LLM live during replay; (b) precompute the live match's overlays once, cache them, replay them timed; (c) both | ★ (c): precompute by default (reproducible demo video, near-zero cost, no latency), with a `--live` flag that runs the real workflow during replay for showing it working. |
| D4 | **Where is personalization applied?** | (a) server per viewer profile; (b) client filters all variants (current, ADR-004) | ★ (b) for now: the backend produces all 4 variants (EN/JA × casual/analyst) per selected insight; the existing client rules filter. Revisit only if time allows. |
| D5 | **Favorites priority (frontend gap 5)** | (a) Selector ranks per profile; (b) the viewer's card slot shows the highest-priority card within its display time, favorites first | ★ (b) plus favorites as an input to (a)'s priority. Cheap, and visible in the two-viewer demo. |
| D6 | **Japanese text** | (a) the LLM writes JA directly from facts; (b) write EN, then translate | ★ (a): one call per (lang, mode) variant from the same facts; the verifier checks JA numbers and names too. |
| D7 | **Foundry evaluations scope** | (a) skip; (b) one offline run of `FoundryEvals` on a sample of narrations; (c) in CI | ★ (b) if time allows (COULD): a hero-technology checkbox with a concrete number. |

---

## Tasks

Priority: **MUST** (needed for the demo and category), **SHOULD** (strongly improves the score),
**COULD** (only if time allows).

| # | Task | Priority | Estimate | Depends on |
|---|---|---|---|---|
| 1 | ✅ Overlay contract and template catalog (backend) | MUST | 1 h | — |
| 2 | ✅ Template narrator (deterministic EN/JA fallback) | MUST | 1.5 h | 1 |
| 3 | ✅ Verifier (deterministic checks) | MUST | 1.5 h | 2 |
| 4 | ✅ Verifier catch-rate harness | SHOULD | 1 h | 3 |
| 5 | 🟡 LLM client setup and fake client (Azure steps pending) | MUST | 1 h | D1 |
| 6 | ✅ Agents: Selector, Narrator, Composer | MUST | 2 h | 1–5 |
| 7 | ✅ Workflow orchestration (Agent Framework) | MUST | 1.5 h | 6 |
| 8 | Corrections path (retract/correct overlays, banner) | MUST | 1 h | 7 |
| 9 | Live integration: overlay cache and SSE | MUST | 1 h | 7, 8 |
| 10 | Frontend wiring (gaps 1 and 5) | MUST | 1 h | 9 |
| 11 | Foundry evaluations | COULD | 1 h | 6 |
| 12 | Half-time or full-time recap card (gap 7) | COULD | 1 h | 7 |
| 13 | Docs: ADR-008, README, milestone log | MUST | 0.5 h | all |

---

### Task 1: overlay contract and template catalog (MUST) ✅ Done

**Goal:** the backend speaks exactly the overlay format the viewer already renders.

- **1.1 Pydantic models** (`formline/schema/overlay.py`)
  - `Overlay` mirroring `frontend/src/lib/types.ts`: `overlay_id`, `op` (show/correct/retract),
    `supersedes_overlay_id`, `match_clock_ms`, `ttl_ms`, `template_id`, `priority`,
    `audience_mode`, `lang`, `slots`, `insight_id`, `player_id`, `metric`,
    `source_event_ids`, `verified`.
  - `OverlaySlots`: `tag`, `headline`, `sub?`, `bars?` (casual), `rows?` (analyst).
  - `StreamMessage` gains `{kind: 'overlay', overlay}`.
- **1.2 Fixed template catalog** (`formline/agents/catalog.py`)
  - `shot_speed_card` (speed vs norm, season best/worst), `placement_card`,
    `finish_quality_card`, `correction_banner`.
  - Per template and mode: which slots are required, max lengths (headline ≤ 60 chars EN,
    ≤ 30 JA), and which facts feed `bars` and `rows`.
  - Map insight type → template (`shot_speed_vs_norm`/`season_*` → `shot_speed_card`, etc.)
    and insight metric → overlay metric (`shot_speed_kmh` → `shot_speed`, `placement`/`psxg`
    → `finishing`).
- **1.3 Contract test**
  - Export JSON Schema from the Pydantic models. Commit a few example overlays as
    `backend/data/sample/overlays.example.json`.
  - Backend test: the examples validate. Frontend test: the same file loads as `Overlay[]`
    and renders through `applyOverlays` and `personalize`.
- **Done when:** a hand-built overlay from a real insight validates and renders in the viewer.

**Result:**
- `formline/schema/overlay.py`: `Overlay`, `OverlaySlots`, `Bar`, `Row`, with op rules
  (correct and retract must name what they supersede; show must not), at least one source
  event, and `overlay_message()` for the stream. Top-level nulls stay in the JSON because
  the TS type expects the keys; empty optional slots are omitted.
- `formline/agents/catalog.py`: insight type → template, insight metric → overlay metric,
  per-language length limits (headline 60 EN / 30 JA), and deterministic `bars` (casual)
  and `rows` (analyst) built from facts in EN and JA, so card numbers are correct by
  construction. Insight facts gained `comparison_level`, so the comparison can be translated.
- Contract artefacts, written by `uv run formline-gen contracts`:
  `docs/contracts/overlay.schema.json` (JSON Schema) and
  `backend/data/sample/overlays.example.json` (6 overlays from real live-match insights:
  show, retract, correct, correction banner; EN and JA).
- Tests: 16 backend (schema drift guard, examples, op rules, catalog), 4 frontend (the
  viewer loads the backend examples and its retract and personalization logic works on them).

### Task 2: template narrator, the deterministic fallback (MUST) ✅ Done

**Goal:** every insight can always be worded correctly without an LLM. This is the fallback
after verifier failures, and the offline mode.

- **2.1 EN templates** per (template, mode):
  - casual: short headline + one `sub` sentence + `bars` (this shot vs his norm);
  - analyst: headline with the number and delta + `rows` (norm, sample and weight, comparison,
    percentile, xG/PSxG) + "All figures are model estimates."
- **2.2 JA templates**: the same facts, natural Japanese; numbers in ASCII digits; player names
  from `display_name_ja`; "（推定）" on estimates.
- **2.3 Wording rules built in:** percentiles and probabilities always phrased as estimates;
  the comparison label from `facts.comparison` ("from this spot" only at the zone levels);
  thin samples flagged ("small sample").
- **2.4 Correction banner templates** (EN/JA, casual/analyst) from `InsightCorrected` and
  `InsightRetracted` reasons ("Goal disallowed …", "The earlier stat has been withdrawn").
- **Steps:** write the templates → unit tests per template × mode × lang on the live match's
  22 insights → check lengths and required slots.
- **Done when:** all live-match insights produce 4 valid variants each, and the verifier (task 3)
  passes all of them.

**Result** (`formline/agents/template_narrator.py`, tests in `tests/test_template_narrator.py`):
- `narrate(insight, lang, mode, names)` returns `TextSlots(tag, headline, sub)` for all 5
  insight types × EN/JA × casual/analyst. `narrate_correction(changes, lang, mode)` words the
  banner for all insight changes caused by one corrected event ("Goal disallowed after
  review" / "ゴール取り消し（判定変更）").
- **Honest comparisons:** the pool is named by the level actually used: "his typical shot from
  this spot", "… from outside the box", "his typical strong-foot shot" (JA: "この位置からの
  シュート", "エリア外からのシュート", "利き足シュート全体").
- **Estimates always marked** ("(estimate)", "Est.", "Model estimates." / "（推定）", "推定");
  thin samples flagged ("Small sample." / "（サンプル少）"). JA uses the katakana surname, or
  the full kanji name (伊藤健二).
- **Example (flagship 40:12 shot):** "Reyner — not his usual strike | 84 km/h, about 8 km/h
  below his typical shot from outside the box (estimate)." · "レイナー、いつもの威力がない |
  84 km/h。エリア外からのシュートの平均より約8 km/h遅い（推定）"
- **8 tests** over all 22 live insights × 4 variants: lengths within catalog limits, only the
  insight's player named, every number derivable from facts, estimate markers present,
  "this spot" only at zone level, thin samples flagged, banner wording.

### Task 3: verifier, deterministic checks (MUST) ✅ Done

**Goal:** reject any narration that states something the engine didn't compute. No LLM here, so
it can be measured.

- **3.1 Number check:** extract every number from the text (EN and JA, including full-width
  digits and "%"). Each must match an allowed value from `facts` after display rounding
  (e.g. 84.1 → "84", "84.1"; delta −8.2 → "8"). Allowed values are derived from facts, not
  hand-listed.
- **3.2 Entity check:** the only player named is the insight's player (EN or JA name, surname
  allowed). No other player or club names from the league.
- **3.3 Estimate wording:** any percentile or probability must carry an estimate marker
  ("estimate", "model", "about", "~" / "推定", "約"). No certainty words about probabilities.
- **3.4 Structure:** required slots present, lengths within the catalog limits, no slots outside
  the template.
- **3.5 Verdict:** `Verdict(ok, failures=[{check, detail}])`. The failure details are written
  so they can be fed back to the Narrator as retry instructions.
- **Done when:** template outputs (task 2) always pass, and hand-written bad examples fail
  with the right reason.

**Result** (`formline/agents/verifier.py`, tests in `tests/test_verifier.py`):
- `verify(slots, VerifyContext(template, lang, mode, facts, player_id), league)` →
  `Verdict(failures)`; `Verdict.feedback()` gives retry instructions for the narrator.
- Six checks: numbers, entities, estimates, certainty, language, structure.
- **Unit-aware numbers.** A first version accepted "about **18** km/h below" because 18 *is* a
  fact (the 17.7 m shot distance, rounded). Numbers are now matched by kind: before `km/h` only speed
  facts, before `%` only percentage facts, after `n=` only sample sizes, before `/100` only
  the placement score; bare numbers may use any fact. Full-width digits and the Unicode minus
  are normalised first.
- **Entities:** other players' surnames (EN, word-bounded) or JA names, and other clubs, are
  rejected; surnames shared with the insight's player (two Inglebys) don't raise false alarms.
- **19 tests:** all 22 live insights × 4 template variants and all banners pass; each check
  catches its own hand-written error, in EN and JA.

### Task 4: verifier catch-rate harness (SHOULD; depth lever 4) ✅ Done

**Goal:** a measured number for the README: "the verifier caught X% of injected errors".

- **4.1 Mutators:** take valid narrations and inject one error each:
  - wrong number (±1, ±10%, swapped digits, a number from another insight);
  - wrong entity (a teammate's or opponent's name; the wrong club);
  - missing estimate marker on a percentile or probability;
  - certainty claim ("he will score …");
  - over-length or missing slot.
- **4.2 Run** over all live-match variants (22 insights × 4 variants × mutators); report the
  catch rate per mutation type and the false-positive rate on unmutated text.
- **4.3 CLI and report:** `uv run python -m formline.agents.verifier_eval` writes
  `docs/verifier-catch-rate.md`; a test keeps the catch rate above a floor.
- **Done when:** a README table exists. Any missed category is either fixed or explained.

**Result** (`formline/agents/verifier_eval.py`, report `docs/verifier-catch-rate.md`, tests
`tests/test_verifier_eval.py`):
- 13 mutators in 6 families, applied to all 88 template cards (22 insights × 4 variants).
- **First run:** 97.2% caught. Fixes it led to:
  - the verifier now binds percentiles (`21st`, `21パーセンタイル`), `n=` (comparison sample
    only) and the `/100` scale to their roles, so "Est. 100th pct." and "n=7" (season count)
    no longer pass (numbers 97% → 99%);
  - my estimate-removal mutator was incomplete in Japanese (it left "モデルによる", a valid
    marker). Fixing the **mutator** took that family from 62% to 100%; the verifier did not
    change for it.
- **Final: 1,071 / 1,075 caught (99.6%), 0 false positives on 88 clean cards.**
- **Remaining misses** are role confusions (a real speed fact shown in the norm's place).
  Documented as a known limit, along with English-only club-name checks.
- Tests keep the rate from regressing: no false positives, ≥ 98% overall, 100% for the
  non-numeric families, ≥ 97% for numbers.

### Task 5: LLM client setup and fake client (MUST; D1)

**What needs Azure and what doesn't** (decided 2026-10-17): almost all of task 5, and tasks
6–10, are built and tested against the fake client, with no Azure access. Only creating the
Foundry deployment (5.1) and the real smoke test (5.3) need Azure; they can be done at the
end of the milestone, when the owner has the deployment ready.

| Sub-task | Needs Azure? | When |
|---|---|---|
| 5.1 Foundry project and model deployment | **Yes** (owner, in the Azure portal) | Before the real narration run |
| 5.2 Client factory and fake client ✅ | No | Done |
| 5.3 Smoke test with one real call | **Yes** (deployment plus `az login`) | After 5.1 |
| 5.4 Cost guard (budget, temperature, cache) ✅ | No | Done |
| Settings wiring and tests ✅ | No | Done |

- **5.1 Azure:** create (or reuse) a Microsoft Foundry project with a small model deployment.
  Record the endpoint and deployment in `.env` (`AZURE_AI_PROJECT_ENDPOINT`,
  `AZURE_AI_MODEL_DEPLOYMENT_NAME`, already in `config.py`). Auth via `azure-identity`
  (`az login` locally).
- **5.2 Client factory** (`formline/agents/llm.py`): returns a `FoundryChatClient` when
  configured, otherwise a **fake client** that answers with the template narrator's output
  (optionally injecting errors, to test retries). Tests and CI never call Azure.
- **5.3 Smoke test** (manual, not CI): one real call returns valid JSON for one insight.
- **5.4 Cost guard:** a token budget per run, temperature 0–0.3, short prompts (facts JSON only),
  and a response cache keyed by (insight id, facts hash, lang, mode, prompt version).
- **Done when:** the same code path runs against Foundry and against the fake client.

**Result so far** (`formline/agents/llm.py`, tests `tests/test_llm.py`):
- `FakeChatClient` subclasses Agent Framework's `BaseChatClient`, so the fake runs through the
  same `Agent(client, instructions).run(...)` path as Foundry. It answers from a Python
  function and records every call.
- `make_chat_client(config)`: `FoundryChatClient(project_endpoint, model, AzureCliCredential())`
  when `AZURE_AI_PROJECT_ENDPOINT` is set, otherwise the fake. Constructing the Foundry client
  needs no network, so it's unit-tested.
- `LLMRunner.complete(agent, instructions, input)`: response cache (keyed by prompt version,
  model, agent, instructions and input; optionally persisted) → call budget (600 per run by
  default) → `Agent.run` with temperature 0.2 and max 400 tokens. Retries bypass the cache.
- Manual smoke test: `uv run python -m formline.agents.llm --smoke`.
- `backend/.env.example` documents both modes.
- 9 tests. **Pending (Azure):** 5.1 deployment and 5.3 real smoke test.

### Task 6: agents (MUST; D2, D6) ✅ Done

Each agent has one job, a typed input and output, and a fallback.

- **6.1 Insight Selector**
  - **Rules shortlist** (deterministic): salience threshold; cooldowns (at most one card per
    player per N match minutes, at most M cards per 10 minutes); season records and goals
    first; favorites raise priority later, client-side (D5).
  - **LLM pick** (D2 b): given the shortlist as JSON, choose what to show now and why
    (`{"show": [insight_id], "reason": "..."}`), constrained to shortlist ids. Invalid output
    falls back to the top-ranked item.
  - Output: selected insights with `priority` and a short reason (kept for explainability).
- **6.2 Narrator**
  - Instructions: the voice per mode (casual = short and vivid; analyst = dense, with
    numbers); "use only numbers from FACTS"; estimate wording rules; JSON output
    `{tag, headline, sub, rows?}`. No `bars`: the Composer computes those.
  - One call per (lang, mode) variant: 4 per insight, run concurrently.
  - On retry: the verifier's failure details are appended as feedback.
- **6.3 Overlay Composer** (deterministic executor, not an LLM): fills the catalog template:
  `bars` and `rows` from facts, ids, `match_clock_ms` (shot time + about 2 s),
  `ttl_ms`, `priority`, `metric`, `player_id`, `source_event_ids`, `verified`.
- **Done when:** for one insight, the agents produce 4 verified overlays, against the fake client
  and the real one.

**Result** (`agents/selector.py`, `narrator.py`, `composer.py`, `cards.py`, `fakes.py`; tests
`tests/test_agents.py`):
- **Selector:** rules shortlist (salience ≥ 0.35, one card per shot, 3-minute per-player
  cooldown, at most 3 cards per 10 minutes; salience ≥ 0.9 overrides cooldown and rate),
  then the LLM picks one shortlist id with a reason (JSON). Bad JSON or an id off the
  shortlist falls back to the top candidate (`decided_by="rules"`).
- **Narrator:** one call per (language, mode); the payload carries facts, player name, the
  comparison level, limits and the audience mode. `narrate_verified()`: verify → retry with
  the verifier's feedback (bypassing the cache) → after 3 attempts the template narration,
  which always verifies. Each result records source, attempts and failures.
- **Composer:** deterministic overlay: catalog bars/rows, ids, show time = shot + 2 s,
  TTL 12 s (15 s for season records), priority, metric and lineage.
- **`build_cards()`:** one selection → 4 verified overlays, variants narrated concurrently.
- **`FakeAgents`:** a well-behaved fake model that can also be wrong on the first n attempts or
  return garbage, to test retries and fallback.
- **Whole live match (fake model, wrong on every first attempt):** 22 insights on 16 shots →
  **14 cards** (cooldowns, rate limit, one per shot); all 56 card texts fixed on retry;
  117 model calls.
- **Tuning item for the demo:** at 40:12 the Selector picks Reyner's placement insight
  (salience 0.55) over the flagship speed insight (0.49). Correct by salience, but the video
  story is speed. Revisit when the real model is connected (prompt preference or salience
  weighting).
- 11 tests: shortlist rules, LLM pick and fallbacks, payload, parsing, first-time pass,
  retry with feedback, template fallback (wrong numbers and garbage), composer, full card set.

### Task 7: workflow orchestration with Agent Framework (MUST) ✅ Done

**Goal:** an explicit, inspectable multi-agent workflow: roles, shared state, handoffs, recovery.

- **7.1 Workflow graph** (`WorkflowBuilder`):
  `Selector → fan-out (4 variants) → Narrator → Verifier → switch(pass → Composer,
  fail & tries < N → Narrator with feedback, fail & tries ≥ N → TemplateFallback → Composer)
  → fan-in → output`.
- **7.2 Shared state:** the insight facts, variant, attempt count and verifier history travel in
  a typed message. Every overlay records how it was produced (`llm` or `template`, attempts)
  for the logs and the README.
- **7.3 Failure recovery:** LLM timeout or error → retry once → template fallback. The workflow
  never blocks the event stream.
- **7.4 Observability:** log each handoff and verdict as JSON lines, and count LLM vs fallback
  per run. Agent Framework's OpenTelemetry is optional (COULD).
- **7.5 Tests:** with the fake client, set to inject errors, the retry path and the fallback path
  both produce valid overlays; the attempt counts are right.
- **Done when:** running the workflow on the live match's insights produces all overlays, and the
  run summary shows the LLM, retry and fallback counts.

**Result** (`agents/workflow.py`, tests `tests/test_workflow.py`):

```
Moment ─► Selector ─fan-out─► Narrator[en·casual]  ┐
                              Narrator[en·analyst] ├─► Verifier ─switch─┬─ ok ───► Composer ─► Collector ─► output
                              Narrator[ja·casual]  │                    ├─ retry ► same Narrator (with feedback)
                              Narrator[ja·analyst] ┘                    └─ else ─► TemplateFallback ─► Composer
```

- Built with `WorkflowBuilder`: `add_fan_out_edges` (Selector → 4 narrators, run in
  parallel), `add_edge`, and `add_switch_case_edge_group` on the Verifier (`Case` ok →
  Composer; one `Case` per variant routes a retry back to its own Narrator, which makes the
  retry loop an explicit cycle in the graph; `Default` → TemplateFallback).
- **Typed handoffs:** `Moment` → `Selection` → `Draft` → `Checked` → `Card` → `MomentResult`.
- **Shared state:** the workflow context holds the run trace (every handoff and verdict, also
  logged as JSON lines via `formline.workflow`) and the collected cards.
- **Failure recovery:** bad JSON, timeouts, network errors and an exhausted budget become
  verifier failures (retry, then template); a selector failure falls back to rules. A run
  always completes.
- `run_match(insights, deps)` runs moment by moment in match order (the selector's cooldowns
  carry over) and returns a `RunSummary`.

**Live match (fake model):**

| Model behaviour | Cards | From model | Template | Retried | Model calls |
|---|---|---|---|---|---|
| Well-behaved | 56 | 56 | 0 | 0 | 61 |
| Wrong on first attempt | 56 | 56 | 0 | 56 | 117 |
| Always garbage | 56 | 0 | 56 | 56 | 173 |

- 8 tests: graph roles, the three behaviours, model exceptions (selector falls back to rules,
  narration to templates), an exhausted budget (mix of model and template text),
  determinism, a moment where nothing is selected.

### Task 8: corrections path (MUST)

**Goal:** the VAR moment works end to end, the flagship robustness demo.

- **8.1** `InsightRetracted` → a `retract` overlay for every variant of the withdrawn overlay
  (lineage: insight id → overlay ids).
- **8.2** `InsightCorrected` → a `correct` overlay that supersedes the old one, with re-narrated
  text from the new facts (e.g. "fastest shot of the season", no longer "goal").
- **8.3** A `correction_banner` overlay (all 4 variants), worded from the change reason, with
  `source_event_ids` = the VAR events plus the shot.
- **8.4 Test:** in the live match, the 63:42 overlays are retracted or corrected and a banner
  appears after the VAR decision.
- **Done when:** the viewer shows the withdrawn card, the corrected card and the banner from
  backend data.

### Task 9: live integration, overlay cache and SSE (MUST; D3)

- **9.1 Precompute:** `uv run formline-gen overlays` runs bootstrap → live pipeline → workflow
  over the live match and writes `data/overlays/<match_id>.jsonl` (timed overlays). The result
  is cached, so a rerun costs nothing.
- **9.2 Stream:** `/matches/{id}/stream` merges the event feed and the cached overlays by time.
  `?live=true` runs the workflow during replay instead (overlays arrive when ready).
- **9.3 Chaos:** with `?chaos=true`, overlays still come out right. The engine handles the
  feed; overlays follow insight changes.
- **9.4 End of stream** (frontend gap 4, partial): send `{kind: 'end'}` so the viewer stops
  reconnecting.
- **Done when:** the viewer in live mode shows cards at the right moments without any mock data.

### Task 10: frontend wiring (MUST; gaps 1 and 5)

- **10.1** Remove the mock dependency in live mode: overlays come from the stream (gap 1).
- **10.2** Card slot priority (D5): keep cards visible for `ttl_ms`; show the highest-priority
  visible card, favorites first (gap 5).
- **10.3** Handle `{kind: 'end'}`: show "Full time" and close the stream.
- **10.4** Check the three key moments in a browser: a shot card, the two-viewer view (JA casual
  vs EN analyst) and the VAR retraction.
- **Done when:** the demo runs from backend data only, and `docs/frontend-gaps.md` is updated.

### Task 11: Foundry evaluations (COULD; D7)

- Run `FoundryEvals` (groundedness, fluency, relevance) on a sample of LLM narrations against
  their facts. Record scores in `docs/` and mention them in the pitch.

### Task 12: recap card (COULD; gap 7)

- At half time and full time: "his three most unusual shots tonight", built only from tonight's
  insights. A new `recap_card` template, plus narrator and verifier support.

### Task 13: docs (MUST)

- **ADR-008** agent architecture: roles, why the Selector is a hybrid, why the Composer and
  Verifier are deterministic, retries and fallback, the precompute cache, the cost guard.
- **README:** the agents section, the verifier catch-rate table, how to run with and without
  Azure.
- This file: status per task, as in `docs/milestone-2-engine.md`.

---

## Acceptance criteria for the milestone

1. In live mode, the viewer shows insight cards from backend data, in EN/JA × casual/analyst,
   with no mock data.
2. Every card's numbers come from engine facts. The verifier passes every shown card, and
   failed narrations fall back to templates.
3. The VAR overturn produces retraction, correction and banner overlays end to end.
4. A measured verifier catch rate is in the README.
5. The workflow runs on Microsoft Agent Framework with distinct roles, shared state, explicit
   handoffs and failure recovery, against Microsoft Foundry and a fake client.
6. All tests pass without Azure access.

## Risks

| Risk | Mitigation |
|---|---|
| Azure setup or quota takes long | The fake client means the whole milestone works offline; Azure is only for the real narration run. |
| LLM output fails the verifier often | Retry with feedback, then template fallback. Report the fallback rate honestly. |
| Japanese quality | The verifier checks numbers and names; templates are the floor. A native-speaker skim before recording. |
| Time | MUST items first. Tasks 11–12 are optional. If short, the Selector stays rules-only (D2 a). |

## Out of scope

Azure deployment of the app (milestone 4), the demo video and pitch (milestone 5), and
server-side per-viewer filtering (D4).
