# Formline: project pitch

Three lengths, so whichever the submission form asks for is ready to paste. All data in
Formline is synthetic: no real clubs, players, match data or trademarks.

## Tagline (one line)

Statcast-style personal baselines for football: live, explainable, personalized insights
written by verified AI agents on Microsoft Foundry and Azure.

## Short description (about 70 words)

Formline turns a live stream of match events into on-screen insights that compare each shot
with the shooter's own history: "118 km/h, 31 above his norm, his fastest this season."
Agents on Microsoft Agent Framework and Microsoft Foundry write the cards in English and
Japanese for casual fans and analysts, and answer viewers' own questions through a
tool-using Researcher. A deterministic verifier checks every number. It runs on Azure
Container Apps.

## Full pitch

### The problem

Broadcast stats are generic. "Shot speed 118 km/h" means little unless you know what is
normal for *that* player, from *that* spot, under *that* pressure. Baseball solved this by
comparing every pitch with the pitcher's own norms; football coverage rarely does. And when
an AI writes on-screen text live, one wrong number or name on air is a real cost.

### What Formline does

Formline is a live insight engine for studio and streaming. As a match unfolds, it:

- **Compares like with like.** Each shot is measured against the shooter's own comparable
  shots (same zone, body part and pressure). When his sample is thin, it widens the
  comparison and says so.
- **Never overclaims.** Small samples are shrunk toward his position group (empirical
  Bayes), so three shots never produce a confident percentile, and every probability is
  worded as a model estimate.
- **Explains why the moment matters**, in the viewer's language and depth: short cards for
  casual fans, full numbers (baseline, sample size, weight, comparison group, xG) for
  analysts, in English or Japanese.
- **Personalizes what appears, not just the wording.** Favorite clubs and players win the
  card slot. Casual fans with favorites see only theirs. Player focus keeps a running strip
  of one player against his own norm. "My metric" switches the card: at 40:12 a shot-speed
  viewer sees "84 km/h, 8 below his norm" while everyone else sees the placement insight
  for the same shot.
- **Answers the viewer's questions.** A Match Analyst comments on every shot, corner and
  card and offers follow-up questions. Viewers can also type their own question ("how did
  the top scorer do in his last 3 games?"). A Researcher agent looks up the season leaders,
  finds the top scorer, fetches his last three games and answers from those facts. It says
  so when the data cannot answer (injuries, the referee's reasons).
- **Stays correct when the feed is messy.** Duplicate, late, out-of-order and corrected
  events are absorbed. When VAR overturns a goal, every dependent card is corrected or
  withdrawn through its lineage, and the baselines are rebuilt from the event log.

A 2D pitch shows the match as it unfolds: all 22 players and the ball from synthetic 10 Hz
tracking, the cards on top, a GOAL! flash and set-piece labels, speeds from 1× to 120× and a
Jump to menu for the key moments. A two-viewer page shows the same moment for a Japanese
casual fan and an English analyst side by side.

### How it works

The five stages of the brief, end to end:

1. **Ingest.** A seeded generator produces a fictional league (6 clubs, 30 past matches and
   a live match) and replays it as a live feed. A chaos injector adds duplicates,
   reordering, late messages and corrections. Events go into an append-only, idempotent
   event log with a reorder window (and an idle timeout, so a goal's card never waits for
   the next event). Synthetic tracking for all 22 players and the ball is derived from the
   events: a team-shape model, with every player exactly on his event spots.
2. **Interpret.** A deterministic engine, with no LLM, computes shot features and
   incremental personal baselines with like-for-like buckets and shrinkage.
3. **Explain.** Detectors find notable shots, each citing its source events. A
   multi-agent workflow decides which insight to show and how to say it.
4. **Render.** Every card fills a template from a fixed catalog as timed, machine-readable
   JSON, with its source event ids, streamed over resumable server-sent events.
5. **Personalize.** The viewer filters and ranks the cards per viewer settings.

**The card agents** (Microsoft Agent Framework `WorkflowBuilder`, shared state, explicit
handoffs):

- **Insight Selector** (rules plus LLM): rules build a shortlist (salience, cooldowns,
  rate limits); the model picks one card and explains why through a JSON contract.
- **Four Narrators** (LLM, in parallel): English and Japanese, casual and analyst. Each
  writes from the engine's facts only.
- **Verifier** (deterministic): checks every number, name, estimate wording, certainty
  claim, language and structure. On a mismatch it sends feedback and the Narrator
  retries.
- **Template fallback**: after three failed attempts a deterministic template is used, so
  a card is never blocked and never wrong.
- **Overlay Composer** (deterministic): fills the catalog template, so the numbers in bars
  and rows are correct by construction.

**The analyst agents** (the viewer's questions):

- **Match Analyst** (LLM with its own verifier): writes comments and answers from a facts
  pack that code computes. It retries with feedback, then falls back to a template.
- **Question Suggester** (LLM, checked in code): picks 2–3 follow-up questions per comment
  from a fixed catalog.
- **Researcher** (LLM with 14 Agent Framework tools): decides which facts a typed question
  needs, reads each result and chains ids into the next lookup. Code admits each tool call
  (at most 5), validates arguments, charges every model round-trip to a budget, and applies
  one 25 s deadline.
- **Question Router** (LLM, one shot): the Researcher's fallback when research times out,
  runs out of budget or replies badly.

**Why multi-agent.** A single prompt would have to choose, write four audiences, check
itself and format JSON at once, with nothing between it and the screen. Splitting the roles
puts deterministic checks at every handoff, lets four audiences be written in parallel,
and gives each failure a defined recovery path: retry with feedback, rules fallback for the
Selector, template fallback for text. A correction (VAR) re-enters the same workflow as a
forced selection. For typed questions, the agent that decides what to look up never writes
the answer, and the agent that writes it only sees facts computed by code. The verifier sits
between them and the screen.

### Microsoft and Azure technologies

| Technology | How Formline uses it |
|---|---|
| **Microsoft Agent Framework** (Python) | The multi-agent workflow: `WorkflowBuilder` graph, fan-out to four Narrators, a switch-case retry cycle with the Verifier, shared state, `Agent` and chat clients; the Researcher's 14 function tools and tool-calling loop |
| **Microsoft Foundry** | A Foundry project with a `gpt-4.1-mini` deployment behind every LLM agent: Selector, Narrators, Match Analyst, Suggester, Researcher and Router (`FoundryChatClient`) |
| **Azure Container Apps** | Hosts the backend (FastAPI) and the viewer (Next.js); scales to zero; HTTPS ingress for long-lived streams |
| **Microsoft Entra ID** | The backend's managed identity holds the "Foundry User" role, so there are no API keys anywhere |
| **Azure Monitor (Log Analytics)** | Container logs from both apps |
| **Azure Cost Management** | Monthly budget with alerts at 50% and 100% |
| **GitHub Actions** | CI on every push (lint, typecheck, tests, image builds); publishes images to GitHub Container Registry on `main` |
| **GitHub Copilot in Visual Studio Code** | Used during development |

### Evidence

The repository measures its own claims:

- **Verifier:** catches **99.3%** of 1,066 injected errors (wrong numbers, wrong players
  or clubs, missing estimate wording, certainty claims, wrong language, bad structure),
  with **0** false positives.
- **Feed robustness:** **300 / 300** chaotic replays (duplicates, reordering, late
  messages, corrections) end with exactly the same baselines as a clean rebuild.
  Property-based tests run the same check in CI.
- **Shrinkage:** **30%** lower error than raw personal averages, **45%** for players with
  1–4 shots, measured against the generator's hidden ground truth.
- **Realism:** **14 / 14** event-data checks within range of public league aggregates.
  Tracking puts **99.5%** of players on their event spots; the report also shows honestly
  where it falls short (players cover about 8 km per 90, against 10–12 km in real football).
- **Agents in practice:** **80 / 80** Foundry-written card texts for the demo match passed
  the verifier, with no template fallbacks. The Match Analyst wrote **96 / 96** comments and
  **190 / 192** follow-up answers that passed verification.
- **Typed questions** (single-match smoke evaluations, scored by hand against the engine's
  facts): **27 / 27** answerable questions relevant in a full run of the 38-question EN/JA
  set on the current code (26 / 27 in the first baseline), with no false claim confirmed,
  ambiguous names clarified and nothing leaked to injection.
  On a harder 75-case set: 61 pass, 6 safe but weak, 8 fail. Most failures were claims
  without a number, so they became deterministic checks and were rechecked on the model.
  The remaining limits are documented. Median 5.4 s per question.
- **Engineering:** 375 backend and 75 frontend tests, 13 design decision records, CI on
  every push. Model costs for all development and evaluation runs: roughly ¥150–200
  (estimated from call counts).

### Production readiness and impact

Formline is built the way a broadcaster would need to run it:

- every overlay cites its source events, for audit and corrections;
- deterministic guardrails sit between the model and the screen;
- no secrets anywhere (managed identity);
- a deterministic replay reproduces any match exactly;
- containers scale to zero, with a response cache, a call budget and budget alerts.

The same engine could serve a studio graphics team, a second-screen app or a
multilingual streaming feed. Each viewer gets the comparison that matters to them, in
their language, with numbers that hold up.

### Links

- Repository: https://github.com/roymwxuk/mwx-hackathon-formline
- Live demo: https://formline-web.bravestone-2a024c10.japaneast.azurecontainerapps.io (scales
  to zero; the first load takes about 30 s)
- Demo video: *(add the URL after publishing)*
- Architecture diagram: `docs/architecture/architecture.png`
- Screenshots: `docs/ui/live/hero-two-viewers-64m.png` (two viewers),
  `docs/ui/live/analyst-researcher-chain.png` (a chained typed question)
