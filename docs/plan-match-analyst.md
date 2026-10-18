# Plan: Match Analyst (proactive comments at key events + contextual question buttons)

**Status:** Phase 1 built (2026-10-18): comments after every shot, corner and card, the VAR
withdrawal, bubble and panel; 96 verified comments on the live match with the fake model.
Phase 2 built (2026-10-18): follow-up questions picked by a Suggester agent, answered by
`/ask` (see "Phase 2 as built" below). The Foundry run for both (about ¥25–50, measured
prompt sizes) waits for the owner's go. Owner decisions: proactive comments only after
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

## Phase 2 as built (2026-10-18)

Owner's choices: the LLM **picks** the questions from the fixed catalog (it does not write
them); answers come from a **live endpoint whose cache is pre-warmed** by the precompute run.

- **Catalog** (`analyst/followups.py`): `situation` ("What's happening?"), `score` ("Why is it
  1–0?"), `player_tonight` ("How is Ito doing tonight?", only if the moment's player has shot;
  his shots vs his shrunk season norm), `team_stats` ("Compare the teams"). Wording is fixed per
  language in code. Each has a deterministic facts pack built from the events known when the
  comment was written; players appear as roles (SCORER_A, CHANCE_B, PLAYER).
- **Question Suggester** (`analyst/suggester.py`): one call per moment for both languages;
  OPTIONS are only the questions that apply, in the moment's default order; the reply
  `{"pick": [...]}` must use known ids, no repeats, 2–3 of them; one retry with the problem,
  then the default order.
- **Answers**: the Match Analyst agent and verifier as for comments, with new templates.
  `formline-gen analyst` answers every suggested question in EN and JA into
  `data/analyst/<match>.answers.jsonl`; `POST /matches/{id}/ask` serves those and otherwise
  replays the feed up to the comment's sequence and answers live (same facts, same verifier).
  The comment carries `ask {moment, seq}` and `suggestions[]` (`DATA_SCHEMA.md` §5.5).
- **Viewer**: the Match analyst panel has two tabs (owner's choice, 2026-10-18): *Commentary*
  (the comments) and *Ask the analyst*: the latest moment's 2–3 question chips, and below them
  every answer asked so far, newest first, with its evidence ("Thinking…" while it loads, a
  retry on error). A dot on the tab marks new questions. Both pages; live mode only.
- **Typed questions (owner's request, 2026-10-18):** the Ask tab keeps the two suggested
  chips and adds a text box. A **Question Router** agent (`analyst/router.py`) maps the text
  to `{question, player_id}` from the catalog, or `cannot_answer` (owner's choice: route to
  the catalog rather than one broad facts pack, so every answer stays as verifiable as a
  click). Code checks the route (known id; for `player_tonight` any player who has shot so
  far), one retry, then a polite decline. The typed text reaches only the Router; the
  Analyst answers the routed catalog question, so prompt injection can at worst choose
  another valid question. `POST /ask/free`, 200 characters, 10 per viewer per 10 minutes
  (in-memory limiter keyed on `X-Forwarded-For`). The answer shows *Answered as: …*.
- **Typed questions v2, "RAG over computed facts" (2026-10-18).** Routing to the nearest
  catalog question answered "why nor score nothing today" as "Why is it 1–0?" from the other
  side: fluent, verified and off-target, because the verifier checks facts, not fit. Now the
  Router retrieves 1–3 of 8 fact sections (`analyst/sections.py`: the 4 catalog packs plus
  one team, best chances, fouls and cards, last 10 minutes), merged with one placeholder per
  player; the Analyst (`prompts/analyst_free.md`) answers the viewer's own question from them
  with `coverage` full / partial / none (none → decline); the verifier is unchanged. The
  viewer shows *Based on: Northgate Rovers tonight · Score*. Chip answers are unchanged.
  Typed questions are asked "as of" the latest event the viewer has received (`event_id`,
  `version`; the backend replays the feed to that message), so they work from kick-off,
  before any comment, and always reflect the current minute. A `match_info` section (from
  `matches.json`: season, matchday, venue, kick-off, home and away; plus both clubs' record
  before tonight from the 30 history matches) answers "where is this game played?", which was
  declined before. A `player_info` section covers any squad player, not just those who have
  shot: public profile (club, shirt number, position, preferred foot; never the generator's
  hidden ratings), his season before tonight (appearances, goals, assists, shots, shot-speed
  norm) and his involvement tonight; "info about reyner?" at 2' was declined before.
  Matches now carry match-day `conditions` (weather, temperature, attendance, a fictional
  referee) from a per-match random stream (events byte-identical), so "how was the
  weather?" is answered from `match_info`.
  History questions (no generator change): one pass over the 30 past feeds
  (`store.history_rows`) gives per-game rows (opponent, score, scorers, each player's goals,
  assists, shots, passes). Three sections use them: `season_leaders` (each club's top
  scorers, assists, shots), `player_recent` and `team_recent` (last `n` games, n 1–5, checked
  in code). "Top scorer this season for these two teams" and "Reyner's last 3 games" were
  declined before.
- **Measured on the fake model:** 48 moments, 96 comments, 48 Suggester picks (0 fallbacks),
  288 answers (0 template fallbacks); a live answer equals the precomputed one (test).
- **Cost of the Foundry run:** about 96 + 48 + 288 calls plus retries; measured prompts are
  about 1,300 characters in and 160 out per answer, so roughly ¥25–50 with `gpt-4.1-mini`
  (the earlier "about ¥1" for 96 comments was too low).
- **Foundry runs (2026-10-18).** The first run hit its 600-call cap: 40% of first attempts
  failed the verifier (English bodies twice the limit, because LIMITS were not called
  characters; xG without estimate wording; role words such as "SHOOTER Ingleby"; a club name
  translated into Japanese) and the retries used the budget, so half the output was templates.
  Fixes: limits stated in characters, the exact estimate marker to write, no role words, no
  computed totals, club names as in FACTS, one EN and one JA example; the verifier accepts
  "3 m" for "3.0 m" and rejects Japanese renderings of club names. A 6-moment sample went from
  53% to 78% first-attempt passes. The full run: 296 calls, 96/96 comments and 190/192
  answers by the model (2 templates), 48/48 Suggester picks (always 2 questions). Shipped in
  `backend/demo/analyst/`. About 1,000 calls in all, roughly ¥50–70 (estimate).

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
