# Milestone 3b: studio graphics producer copilot

**Status:** Planned, not started (2026-10-17)
**Branch:** `feat/studio-copilot`, built on `main` (milestone 3 merged)
**Order:** before the Azure deployment (milestone 4 tasks 3+), so the deployed demo includes it.
Milestone 4 task 1 (containers) is already done on `feat/deploy`.
**Estimate:** MVP about 6 h; full scope about 8 h (see "Cut line").

## Why

The engine decides *what* is notable with deterministic math, and the existing workflow
(Selector → Narrators → Verifier → Composer) is an **agentic workflow**: the paths are fixed and
the model only picks a card and words it. That is sound, but the model rarely makes a meaningful
decision. This milestone adds a **real agent** where autonomy matters: a copilot in the
broadcaster's production gallery.

**Fit with the brief** (checked 2026-10-17 against `HACKATHON_BRIEF.md`):
- The challenge is "for **Premier League Studio**", for "studio, broadcast or streaming"; stage (e)
  explicitly allows focusing on "synchronized graphical overlays on a live match feed, as the
  platform's rendering partner does in the **production path**".
- **Best Enterprise Solution:** "reliability, transparency and the **controls** needed for
  production": a human approval loop with an audit log.
- **Best Multi-Agent Orchestration:** the copilot is a new role that collaborates with the
  existing agents through shared state and handoffs.
- **Stage (e) personalization stays** (already built) and is framed as the broadcaster's
  **audience feeds**: e.g. a Japanese casual feed and an English analyst feed from the same
  engine. The two-viewer page is "one engine, two broadcast feeds".
- Still to confirm: the official Rules page.

## What the copilot does

**Goal:** keep the on-air graphics useful, timely and uncluttered for every feed.

During the live match, on each new moment (and on a slow timer), the copilot:
1. **Looks** at the new insights, what is on air now, what aired recently, and the producer's
   feedback so far, using engine **tools** (below).
2. **Proposes** 0–2 graphics: which insight, which template, when to air, priority, and a short
   **reason** a producer can judge in seconds ("Reyner's slowest shot from outside the box this
   season; he's had three below-norm shots tonight").
3. **Waits for the producer:** approve (air now), edit (change the headline; the verifier
   re-checks the edited text), or reject with a reason ("too many cards", "not interesting",
   "wrong moment").
4. **Adapts within the match:** rejections and edits go into the copilot's memory for the rest
   of the match (e.g. after two "too many cards" it proposes less often; after "not interesting"
   for a type, it stops proposing that type unless it's a season record).
5. **Hands off:** approved graphics go through the existing Narrator → Verifier → Composer
   workflow per feed (EN analyst, JA casual, …) and stream to the viewers.

**Autonomy levels** (an enterprise control, set by the producer):
- **Manual:** nothing airs without approval; proposals expire if not decided within N match seconds.
- **Assisted:** high-confidence proposals (season records, high salience) auto-air after a short
  countdown unless rejected; others wait.
- **Autopilot:** the current behaviour (rules + Selector), with the copilot's reasons still logged.

**Audit log:** every proposal, decision (who, when, approve/edit/reject, reason), edit diff, and
verifier result, shown in the console and exportable as JSON lines. Transparency for compliance
and post-match review.

## Engine tools (shared, deterministic)

The copilot calls these; every number it shows is checked against their results by the verifier.

| Tool | Returns |
|---|---|
| `new_insights(since)` | Insights created or corrected since a match time, with facts and salience |
| `on_air(feed)` / `recent_graphics(n)` | What is showing now and what aired recently |
| `player_tonight(player_id)` | Tonight's shots for a player with their comparisons |
| `player_baseline(player_id, metric, context)` | His shrunk baseline for a context, with sample size |
| `shot_detail(event_id)` | One shot's features and comparisons |
| `producer_feedback()` | This match's decisions and reasons so far |

## Decisions to make first

| # | Decision | Options | Recommendation |
|---|---|---|---|
| S1 | How the copilot uses tools | (a) real model tool calls (Agent Framework function tools); (b) the tools run first and their results go into one structured prompt | ★ (a) for the agent story, after a short spike to confirm tool calls work with Foundry **and** can be faked in tests; (b) as the fallback if the spike fails |
| S2 | Relationship to the Selector | (a) the copilot replaces the Selector in studio mode; (b) it sits above it | ★ (a): in studio mode the copilot *is* the selection role (with a human); autopilot keeps today's Selector |
| S3 | Edits | (a) headline edits only; (b) edit any text slot | ★ (a) for the MVP; the verifier re-checks the edited text |

## Tasks

| # | Task | Priority | Estimate |
|---|---|---|---|
| 1 | Spike: model tool calls with Foundry and a fake client | MUST | 0.5 h |
| 2 | Engine tools (above) over the live orchestrator state | MUST | 1 h |
| 3 | Copilot agent: proposals with reasons, JSON contract, fallback to rules | MUST | 1.5 h |
| 4 | Producer session: queue, approve/edit/reject, expiry, autonomy levels, audit log | MUST | 1 h |
| 5 | Adaptation from feedback (memory + rule parameters) | SHOULD | 0.5 h |
| 6 | API: studio SSE stream (proposals + feeds) and a decisions endpoint | MUST | 0.5 h |
| 7 | Producer console UI (`/studio`): pitch and clock, proposal queue, on-air per feed, audit log, autonomy switch | MUST | 2 h |
| 8 | Tests and docs (ADR-009, README "Studio copilot", demo script) | MUST | 1 h |

**Cut line (MVP ≈ 6 h):** tasks 1–4, 6, 7 and 8 with approve/reject only and Manual + Autopilot
levels. Edits, Assisted mode and adaptation (task 5) only if time allows.

### Task details

1. **Spike.** Confirm an Agent Framework agent with function tools works against Foundry and that
   the test fake can return tool calls (the current `FakeChatClient` has no function invocation).
   Outcome decides S1.
2. **Tools.** Thin functions over the `LiveOrchestrator`'s engine and insight tracker; typed
   results; unit-tested.
3. **Copilot.** Instructions: the gallery's goal, clutter limits, the feed list, and "propose only
   from tool results"; output `{"proposals": [{insight_id, template, air_at, priority, reason}]}`.
   Invalid output → the rules shortlist (as today). Reasons are verified like card text (numbers
   must come from tool results).
4. **Session.** Per match: pending proposals, decisions, on-air state per feed, autonomy level,
   expiry by match time, audit log (JSON lines). Approved proposals go through the existing
   workflow per feed.
5. **Adaptation.** Feedback memory added to the copilot's prompt; deterministic knobs (proposal
   rate, blocked types) updated from reject reasons.
6. **API.** `GET /studio/{match_id}/stream` (proposals, decisions, feed overlays, end) and
   `POST /studio/{match_id}/decisions`.
7. **Console.** A second page in the existing Next.js app; reuses the pitch, clock and overlay
   card components; keyboard shortcuts (A approve, R reject) for a real gallery feel.
8. **Docs.** ADR-009 (why a copilot, autonomy levels, human control, audit), README section,
   a demo script for the video (producer approves a card, rejects one with a reason, the copilot
   adapts, VAR correction flows to both feeds).

## Acceptance criteria

1. During a replay, the copilot proposes graphics with reasons grounded in tool results.
2. A producer can approve or reject in the console; approved graphics appear in the viewer feeds
   (EN and JA) within the same moment; rejected ones never air.
3. Every proposal and decision is in the audit log; reasons with numbers pass the verifier.
4. Model failure never blocks the broadcast: proposals fall back to the rules shortlist.
5. Tests run without Azure.

## Risks

| Risk | Mitigation |
|---|---|
| Tool calling hard to fake or flaky on Foundry | Spike first; fallback S1 (b) keeps the same UI and audit flow |
| Time (≈ 6–8 h on top of milestones 4–5) | Strict cut line; Assisted mode, edits and adaptation are optional |
| Demo needs a human clicking | Record the video with the operator approving live; the audit log shows the decisions |
