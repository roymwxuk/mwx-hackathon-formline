# Plan: agentic research for typed questions (a tool-using Researcher agent)

**Status:** Planned 2026-10-19, not started; waiting for the owner's review and go.
**Estimate:** 4–5 h. **Prompted by:** the "ask, find a gap, patch" loop on typed questions.

## Context

Typed questions are answered by a one-shot Router that picks 1–3 fact sections, then the
Analyst writes and the Verifier checks. No agent ever decides to look something up,
inspects the result and continues. So a question that needs two chained lookups ("how did
the top scorer do in his last 3 games?": find the top scorer, then his last 3 games) cannot
be answered, and every new kind of question needed a new section (the patching loop of
tonight). The brief's judging criterion "Agentic design and innovation" and the target
category reward exactly this missing piece: an agent that plans, uses tools, recovers.

Outcome: a **Researcher** agent with tools (the existing fact sections, parameterized) that
gathers facts in as many steps as it needs (capped), then the existing Analyst writes and
the existing Verifier checks against everything the tools returned. Compound questions work
without new sections. The safety model is unchanged.

Feasibility (checked): Agent Framework 1.19 has `@tool` / `FunctionTool` and a built-in tool
loop with `max_function_calls` and `max_iterations`; `FoundryChatClient` already includes
`FunctionInvocationLayer`. Only our `FakeChatClient` lacks it.

## Design

### Agents for a typed question
```
question ─► name check (code, existing) ─► Researcher (LLM + tools, ≤5 tool calls)
              │                                 │ tool results = facts (code-computed)
              │                                 ▼
              │                           facts pack (all tool results, one roles map)
              │                                 ▼
              │                           Analyst (writes the answer) ─► Verifier
              │                                 └─ retry with feedback / template (existing)
              └─ Researcher fails (budget, errors, bad output) ─► one-shot Router (existing) ─► same path
```
- **Researcher** (`analyst/researcher.py`, `prompts/researcher.md`): sees the viewer text
  (as data), the two clubs and both squads (ids and names), and the tools. It calls tools,
  reads their results, and may call more (chaining ids it found, e.g. the top scorer's
  player id). Its final reply is `{"done": true}` or `{"cannot_answer": true}`; it never
  writes viewer-facing text. Limits: `max_function_calls=5`, `max_iterations=6`.
- **Tools** (`analyst/tools.py`): thin wrappers over the existing section builders in
  `analyst/sections.py` (no new fact logic): `get_match_info`, `get_match_so_far`,
  `get_score_explanation`, `get_team_comparison`, `get_team_tonight(club_id)`,
  `get_player_profile(player_id)`, `get_player_shooting_tonight(player_id)`,
  `get_best_chances`, `get_discipline`, `get_last_10_minutes`, `get_season_leaders`,
  `get_player_recent(player_id, n)`, `get_team_recent(club_id, n)`, plus
  `find_player(name)` (candidates with id, club, shirt number) for names.
  Each tool validates its arguments in code (the checks of `router.check_route`: a club of
  this match, a squad player, a shooter, n 1–5) and on bad arguments returns an error
  message the agent can act on (agentic recovery), never facts. Each successful call adds a
  section to one shared facts pack (one `_Roles`, so placeholders stay consistent across
  calls) and returns the facts plus a placeholder→player id map so the agent can chain.
- **Analyst + Verifier**: unchanged (`answer_verified(..., viewer_question=...)` with the
  merged pack). The Verifier checks numbers, names, clubs, wording against every tool result.
- **Fallback**: if the Researcher raises, exceeds limits or returns nothing usable, the
  existing one-shot Router path runs (so a typed question always gets the old behaviour at
  worst). Logged as `researcher_fallback`.

### LLM layer (`agents/llm.py`)
- `LLMRunner.research(agent_name, instructions, input, tools, limits)`: runs an `Agent`
  with tools; spends the call budget per model round-trip (counted with a chat middleware
  or by `max_iterations` up front); no response cache (tool loops are not replayable),
  except that identical questions at the same event reuse the gathered pack in-process.
- `FakeToolChatClient(FunctionInvocationLayer, BaseChatClient)`: a scripted fake that emits
  `Content.from_function_call(...)` turns and then `{"done": true}`, so tests run the real
  framework tool loop offline. Its script chains: for "top scorer … last 3 games" it calls
  `get_season_leaders`, reads the returned id map, then calls `get_player_recent` with that
  id: the test proves real chaining, not a hard-coded pair.

### API and viewer
- `POST /ask/free` response gains `research: [{tool, args_label, ok}]` (the steps taken).
  `retrieved.label` becomes the chain, e.g. "Season leaders → Reyner: last 3 games".
- Ask tab: under each typed answer, a small "Looked up: Season leaders · Reyner: last 3
  games" line (makes the agentic steps visible in the video).

### Cost and latency (typed questions only; chips unchanged and precomputed)
About 2–4 Researcher round-trips plus 1–3 Analyst calls: roughly ¥0.3–0.6 and 5–12 s per
typed question on `gpt-4.1-mini`. The per-viewer limit (10 per 10 minutes) and the call
budget stay.

## Files
- New: `backend/src/formline/analyst/researcher.py`, `analyst/tools.py`,
  `prompts/researcher.md`, `backend/tests/test_analyst_research.py`.
- Changed: `agents/llm.py` (`research`, `FakeToolChatClient`), `agents/fakes.py` (scripted
  researcher), `analyst/ask.py` (Researcher first, Router as fallback, `research` in the
  reply), `analyst/sections.py` (expose the shared roles/pack builder for tools; no fact
  changes), `api.py` (response shape), frontend `lib/types.ts`,
  `components/Analyst.tsx` ("Looked up" line), i18n.
- Docs: ADR-013 (agentic research: why tools over one-shot routing, limits, fallback,
  safety), README agents table and flow, architecture diagram (Researcher + tools),
  `DATA_SCHEMA.md` (`research` field), `docs/plan-match-analyst.md`.
- Unchanged: comments, Suggester, chips and their precomputed Foundry answers, the card
  workflow.

## Verification
- Tests (fake, real framework tool loop): compound question chains two tools with the id
  from the first result; bad tool arguments return an error and the agent corrects them;
  over the call limit the loop stops and the Router fallback answers; out-of-scope →
  `cannot_answer` → decline; facts pack from tools equals `facts_for` for the same sections;
  the Verifier rejects an answer citing a fact no tool returned; existing typed-question and
  history tests still pass (via Researcher, or Router fallback).
- Full backend and frontend suites, ruff, typecheck, lint.
- Browser (fake): a compound question shows the "Looked up" chain.
- Real model (owner's go, about ¥2–3): 8–10 questions locally, including "how did the top
  scorer do in his last 3 games?", "info about reyner?", "why nor score nothing today",
  "how was the weather", one out-of-scope; report steps, latency and cost.

Estimate: 4–5 h, then push → PR → redeploy and the video.
