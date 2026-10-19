# Plan: agentic research for typed questions (a tool-using Researcher agent)

**Status:** Built 2026-10-19 (ADR-013), after Codex's review; real-model evaluation pending
the owner's go.
**Estimate:** 5.5–6.5 h (verifier binding and adversarial tests added by the review).
**Prompted by:** the "ask, find a gap, patch" loop on typed questions.
**Review:** `private/researcher-plan-review.md` (Codex), all six points adopted.

## Context

Typed questions are answered by a one-shot Router that picks 1–3 fact sections; the
Analyst writes and the Verifier checks. No agent decides to look something up, inspects the
result and continues, so chained questions ("how did the top scorer do in his last 3
games?") fail, and each new question type needed a new section. The brief's "Agentic design
and innovation" criterion and the Multi-Agent Orchestration category reward exactly this.

Outcome: a **Researcher** agent uses the existing fact sections as tools, in as many steps
as it needs within hard limits, and hands every result to the Analyst and the Verifier.

**What this does not solve on its own** (review point 3): retrieving more facts does not
show that an answer addresses the question or uses facts in the right relationships. The
current verifier checks that each number and name appears somewhere in the facts, not that
they belong together: Codex reproduced an answer swapping two players' goal counts that
passes today. More facts per question would widen that gap, so this plan includes a
binding check (below) and a separate relevance evaluation.

Feasibility (checked): Agent Framework 1.19 has `@tool` / `FunctionTool` and a tool loop
(`max_function_calls`, `max_iterations`); `FoundryChatClient` includes
`FunctionInvocationLayer`; only our `FakeChatClient` lacks it.

## Design

### Flow
```
question ─► name check (code, existing) ─► Researcher (LLM + tools; hard caps in our code)
                                              │ each valid call → one lookup result
                                              ▼
                              facts pack: lookups keyed by tool + arguments, one roles map
                                              ▼
                              Analyst ─► Verifier (existing checks + number-to-subject binding)
                                              └─ retry with feedback / template (existing)
 Researcher fails (timeout, budget, malformed, no evidence) ─► one-shot Router (reserved budget)
```

### 1. Researcher and tools
- `analyst/researcher.py`, `prompts/researcher.md`; tools in `analyst/tools.py` as thin
  wrappers over the existing builders in `analyst/sections.py`: `get_match_info`,
  `get_match_so_far`, `get_score_explanation`, `get_team_comparison`,
  `get_team_tonight(club_id)`, `get_player_profile(player_id)`,
  `get_player_shooting_tonight(player_id)`, `get_best_chances`, `get_discipline`,
  `get_last_10_minutes`, `get_season_leaders`, `get_player_recent(player_id, n)`,
  `get_team_recent(club_id, n)`, `find_player(name)`.
- Arguments validated in code with the existing `router.check_route` rules (club of this
  match, squad player, shooter, n an int 1–5, not bool). Invalid arguments return an error
  the agent can act on; **errors and the Researcher's own text never enter the facts**.
- Final reply `{"done": true}` or `{"cannot_answer": true}`; it writes nothing viewers see.
- Scope stated in the prompt and docs: season leaders cover the two match clubs only.

### 2. Hard limits in application code (review point 1)
- The framework's `max_function_calls` is best-effort (checked after a parallel batch), and
  iteration exhaustion adds a final no-tools model call. So: a **request-local admission
  counter** checked and charged **before** each tool executes (concurrency-safe); call 6 is
  refused even inside one parallel batch. Invalid attempts count, so errors cannot loop.
- **Every provider round-trip** is charged to the call budget through a chat middleware on
  the Researcher's request, including the final no-tools call. No per-request mutation of a
  shared client's settings (configuration passed per run).

### 3. Lookups keyed by tool and arguments (review point 2)
- The facts pack becomes a list of lookups `{id, tool, args, subject, scope, facts,
  source_event_ids}`; key = tool + validated arguments; identical calls deduplicate,
  different arguments (two players, two windows) both survive. One request-local roles map
  across all lookups. `facts_for` stays for the Router path; both feed the same Analyst.

### 4. Verifier: bind numbers to their subject (review point 3)
- Lookups keep each player's numbers together (per-subject sub-facts). A new check: in a
  sentence (or clause) that names a player or club, every number must come from that
  subject's facts (or from subject-free facts such as the score). Rejects the reproduced
  swap ("Reyner 1, Ito 2" when the facts say 2 and 1) and season totals given as recent
  totals where the scope is labelled. Applies to typed answers on both paths.
- Limitation stated in README: binding is per sentence; a fact in the wrong role inside one
  subject (goals vs shots of the same player) is still not caught, as today's catch-rate
  report notes.

### 5. Budget reservation, deadline and outcomes (review point 4)
- Separate allowances: research (≤ 6 model calls), fallback Router (1 + retry), Analyst
  (3); the fallback allowance is reserved up front, so it can still run. Overall request
  deadline (e.g. 25 s) across research, fallback and narration.
- Distinct outcomes, logged: `answered`, `cannot_answer`, `fallback_malformed`,
  `fallback_timeout`, `fallback_budget`, `fallback_no_evidence`, `budget_exhausted`
  (decline politely). On fallback, partial research is **discarded**, not mixed in.
- No gathered-pack cache in this version (avoids stale facts after corrections); if added
  later, key it by match, event id and version, question, prompt and model versions.

### 6. API and viewer
- `POST /ask/free` reply gains `research: [{tool, args_label, ok}]` and `outcome`;
  `retrieved.label` is the chain ("Season leaders → Reyner: last 3 games").
- Ask tab: a "Looked up: …" line under each typed answer (shows the agent's steps).

## Tests (fake tool client, real framework loop; review point 5)
`FakeToolChatClient(FunctionInvocationLayer, BaseChatClient)` with scripted turns:
- chaining: the first tool's result carries a **changed** player id; the second call must
  use the returned id, not a hard-coded one;
- invalid player/club ids, `n` as bool, string, 0, 6, 2.5: no lookup added, error returned;
- one response requesting more than 5 parallel calls: the 6th never executes;
- iteration exhaustion: every round-trip charged, including the final no-tools call;
- repeated tool with different subjects/windows: all results kept, placeholders consistent;
- malformed final reply, `done` with no evidence, timeout, research budget exhausted while
  the reserved fallback still answers, global budget already exhausted → polite decline;
- tied top scorers named together; unspecified club scope not resolved arbitrarily;
  the existing name clarification still runs first;
- verifier binding: swapped counts, season totals as recent totals, goals vs shots, wrong
  period → rejected; the original correct answer → accepted;
- existing typed-question and history tests pass on both paths.

## Real-model evaluation (owner's go; review point 6)
About 30 questions, EN and JA: direct, compound, ambiguous, unanswerable, hostile, the
owner's reported wording verbatim and unseen paraphrases. Scored separately: relevance
(does it answer the question), factual relationships, coverage, clarify/decline behaviour,
verifier acceptance; measured provider calls, tokens, latency, fallback rate. Cost and
latency in the docs are reported as measured, not estimated. Roughly ¥5–10.

## Files
- New: `analyst/researcher.py`, `analyst/tools.py`, `prompts/researcher.md`,
  `tests/test_analyst_research.py`, `tests/test_verify_binding.py`.
- Changed: `agents/llm.py` (research run with admission counter and per-round-trip budget
  middleware; `FakeToolChatClient`), `agents/fakes.py`, `analyst/verify.py` (binding check),
  `analyst/sections.py` (lookup records), `analyst/ask.py` (Researcher first, reserved
  fallback, outcomes, deadline), `api.py`, frontend `lib/types.ts`,
  `components/Analyst.tsx`, i18n.
- Docs: ADR-013, README (agents, flow, limitations incl. the binding scope), architecture
  diagram, `DATA_SCHEMA.md`, `docs/plan-match-analyst.md`.
- Unchanged: comments, Suggester, chips and their precomputed Foundry answers, the card
  workflow.
