# Plan: Match Analyst (proactive comments at key events + contextual question buttons)

**Status:** Planned (2026-10-18). Not started. Owner decisions: proactive comments only after
shots, corners and cards; button answers live with cache; one version per language; phase 1
first, then decide on the buttons.

## Context

Formline shows **insight cards** (personal baselines, about one per shot). That is graphics,
not commentary: nothing explains *why* a moment turned out as it did. The owner's note
(`current-ideas.md`) asks for EN/JA commentary linked to real events, without hallucinated
scores, goals or names. After comparing options (2026-10-18), the owner chose a hybrid:

- **Proactive comments** written by an LLM agent, only after a few key events: **every shot**
  (scored or not), **corners**, **yellow/red cards**. The insight card stays as it is.
- **Contextual question buttons** for every other moment; the viewer clicks to get an answer.
- **Text only.** No continuous commentary (noisy, costs a line a minute); no audio.

Why this shape: comments only where there is something to explain; everything else on demand,
so there is no unwanted information and cost stays predictable. It reuses the owner's
production patterns: two-stage *retrieve facts deterministically → LLM explains*, and *the
LLM picks from a fixed catalog through a JSON contract*.

## Design

One **question catalog**, one **facts-pack builder**, one **Analyst agent**, one verifier path.
A proactive comment is a catalog question answered automatically when its event happens.

### Question catalog (`backend/src/formline/analyst/catalog.py`)

| Question id | Shown as | Offered / fired | Facts pack (deterministic, at match time t) |
|---|---|---|---|
| `shot_outcome` | "Why did [player]'s shot miss / get saved?" · "How did that goal happen?" | **auto** after every shot | distance, angle, body part, pressure, nearest defender, keeper position, xG/PSxG, placement, speed vs his norm, key pass and passer, outcome |
| `corner` | "What came of that corner?" | **auto** when the corner sequence ends (shot, clearance, or 15 s) | side, taker, delivery spot, what followed (shot and xG, or cleared), team corners tonight |
| `card` | "Why was [player] booked / sent off?" | **auto** at the card | the foul (who on whom, where, minute), his fouls and the team's cards tonight, whether it stopped a counter |
| `situation` | "What's happening?" | button, always | score and goal timeline, shots and xG per side, cards, baseline insights so far |
| `score` | "Why is it 2–0?" / "Why is it still 0–0?" | button, always | goals with xG and build-up, best chances both sides, saves |
| `player_tonight` | "How is [focus player] doing?" | button, when a focus player is set | his shots tonight vs his personal baseline (the project's core concept) |
| `var` | "Why was the goal ruled out?" | button, after a VAR decision | VAR review events, the revised shot |

Buttons show the 2–3 applicable questions (rules in the catalog). The model never invents
free questions (it would ask things the data cannot answer); later it may pick follow-ups
**from this catalog** through a JSON contract (phase 3, optional).

### Facts packs (`analyst/facts.py`)
Built from the engine state and events up to time t (reuse `engine/features.py` shot
features, `engine/insights.py`, the event log via `current_events`, `pitch.py` geometry,
freeze frames). Each fact carries its source event ids. Honest limits are explicit (no foul
reasons, weather or opinions): the agent is told to say what the data cannot show.

### Analyst agent (`analyst/agent.py`)
- Writes the answer from the facts pack only, per **language** (EN, JA; one depth for everyone,
  owner's choice), JSON contract `{headline, body}`.
- Reuses `LLMRunner.complete()` (cache, call budget; `agents/llm.py`), names via
  `template_narrator.names_for`, and the retry-then-template pattern of
  `narrate_verified()` (`agents/narrator.py`).
- **Verified** with the existing `verify()` (`agents/verifier.py`) through new
  `analyst_answer` catalog entries in `agents/catalog.py` (lengths per mode; numbers, names,
  estimate wording and certainty checks against the facts pack). Template answer after 3
  failures, so an answer is never blocked and never wrong.
- Every answer lists its **evidence** (source events with minutes).

### Delivery
- **Proactive comments**: precomputed with the match like the cards (one replay loop:
  `LiveOrchestrator.replay()` in `agents/live.py` already yields every message and overlay),
  written to `data/analyst/<match>.jsonl`, shipped in `backend/demo/analyst/` (copied by
  `scripts/start.sh`), streamed as `{"kind": "comment", ...}` with SSE ids (resume and
  `start=` intact). `?live=true` generates them during the replay.
  About 35 shots + 8 corners + 3 cards = 46 moments × 2 languages ≈ 92 calls + retries,
  roughly ¥1 one-off.
- **Button answers (owner's choice: live with cache)**: `POST /matches/{id}/ask {question, t,
  lang, player}` builds the facts pack at t and calls the agent live, cached per (question, t
  rounded to the last event, lang) and under the call budget; about ¥0.02–0.05 per uncached
  answer, 1–3 s.

### Viewer
- A **comment bubble** stacked with the insight card in the card slot, shown for the card's
  time window; a **Commentary** panel keeps the history (newest first, minute, evidence on
  expand, ★ favourites, struck through if the event is later corrected by VAR).
- **Question chips** under the pitch with the applicable catalog questions; the answer opens
  in the panel with a "thinking…" state and its evidence. Language and mode follow the
  viewer's settings; two-viewer page shows each viewer's own.

## Phasing (owner's choice: phase 1 first, then decide; deadline treated as Oct 26)
1. **Now: proactive comments** (shots, corners, cards): catalog entries `shot_outcome`,
   `corner`, `card`; facts packs; agent; verifier entries; precompute; stream; bubble and
   panel. About 3.5–4 h. Demo-ready on its own. The Foundry precompute run (about ¥1) waits for
   the owner's go.
2. **Then decide: question buttons** (`situation`, `score`, `player_tonight`, `var`, the live
   `/ask` endpoint with cache, chips). About 2.5 h, weighed against the remaining time.
3. Optional: catalog-picked follow-up questions.

## Files
- New: `backend/src/formline/analyst/{__init__,catalog,facts,agent,writer}.py`,
  `backend/tests/test_analyst*.py`, `backend/demo/analyst/<match>.jsonl`,
  `frontend/src/components/{Commentary,AskChips}.tsx`, frontend tests.
- This plan is saved as `docs/plan-match-analyst.md` (owner asked for
  the plan in the repo).
- Changed: `agents/catalog.py`, `agents/fakes.py` (fake analyst answers), `agents/precompute.py`,
  `generator/cli.py`, `replay.py`, `api.py` (stream + `/ask`), `scripts/start.sh`,
  `frontend/src/lib/{types,useMatchStream,i18n}.ts`, `frontend/src/components/{Viewer,App}.tsx`,
  `globals.css`, `DATA_SCHEMA.md`, `docs/decisions.md` (ADR-011), README, pitch, diagram.

## Verification
- Backend: facts packs exact for known events (shot at 63:42, corners, a card); a comment fires
  for every shot, corner and card and nothing else; verifier rejects a wrong number or name and
  falls back after 3 failures; VAR overturn marks the goal comment corrected; stream carries
  comment messages with ids; `/ask` returns verified answers with evidence, caches repeats,
  respects the budget; tests never call Azure (fake model).
- Frontend: bubble timing, panel history, chips shown only when applicable, language/mode.
- Foundry precompute run (owner's go): all comments verified, fallbacks counted, EN/JA texts
  reviewed by eye. Browser check in Chrome via Jump to: 40:05 (saved shot comment), a corner,
  63:30 (goal comment), 64:05 (VAR), and a button answer.
