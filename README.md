# mwx-hackathon-formline

**Formline** — a Synthetic Match Insights Engine for the *Inside the Game* Developer Hackathon
(Microsoft × Premier League). Submissions close **Oct 27, 2026**. Full brief: [HACKATHON_BRIEF.md](HACKATHON_BRIEF.md).

Formline turns synthetic football events into explainable, personalized match intelligence
for studio and streaming use.

## Pipeline

| Stage | Where | Status |
|---|---|---|
| a. Ingest | `backend/src/formline/generator/` (synthetic feed), `replay.py` (live replay) | Generator done; event log next |
| b. Interpret | deterministic stats engine: shot geometry, xG, personal baselines | Next |
| c. Explain | agents: Insight Selector, Narrator, Verifier, Overlay Composer | Planned |
| d. Render | overlay contract (`DATA_SCHEMA.md` §6.5), viewer UI in `frontend/` | UI done on mock data |
| e. Personalize | language, casual/analyst, favorites, player focus, "my metric" | UI done; backend planned |

## Layout

```
backend/    Python 3.12 · FastAPI · Pydantic (uv)
  src/formline/schema/      DATA_SCHEMA.md as Pydantic models
  src/formline/generator/   synthetic league, match simulator, realism report
  data/sample/              committed excerpt of the generated data
frontend/   Next.js · React · TypeScript (pnpm): live viewer UI
docs/       decisions.md (ADRs), realism-report.md, ui/ reference images
```

## Run locally

```bash
# backend → http://localhost:8000
cd backend
uv sync
uv run formline-gen generate     # writes backend/data/ (seed 2026, ~3 s, ~28 MB)
uv run formline-gen report       # writes docs/realism-report.md
uv run uvicorn formline.api:app --reload
uv run pytest

# frontend → http://localhost:3000 (mock replay by default)
cd frontend
pnpm install
pnpm dev
# or against the backend feed:
NEXT_PUBLIC_STREAM_URL="http://localhost:8000/matches/mtc_s26_md11_har_nor/stream?speed=20" pnpm dev
```

## Personal baselines: does shrinkage help?

Each shot is compared with the shooter's own comparable shots, blended with his position
group's average by sample size (empirical Bayes, ADR-006). Checked against the generator's
hidden truth (each player's population mean from 300 extra simulated matches),
`uv run python -m formline.evaluation`:

| Shots in history | Raw average error | Shrunk error | Error cut |
|---|---|---|---|
| All players (39) | 4.11 km/h | 2.87 km/h | **30%** |
| 1–4 shots | 6.26 | 3.45 | **45%** |
| 5–9 shots | 5.41 | 3.91 | 28% |
| 10–19 shots | 2.14 | 1.84 | 14% |
| 20+ shots | 2.20 | 2.05 | 7% |

The group average alone is worse than both (5.03 km/h), so baselines must be personal.
Known limitation: 30 matches slightly underestimate the shrinkage strength (k 2.2 fitted vs
3.9 implied for forwards), so the tiniest samples are under-shrunk a little. Details:
[docs/shrinkage-accuracy.md](docs/shrinkage-accuracy.md).

## Feed robustness: convergence under chaos

Real feeds deliver duplicates, late and out-of-order messages, and corrections. The
engine is event-sourced (append-only log, highest version wins) and its baselines use
exact integer arithmetic, so the final state must not depend on delivery order.

`uv run python -m formline.convergence --runs 300` replays the live match 300 times
through the chaos injector with random rates and seeds:

| Check | Result |
|---|---|
| Messages delivered | 464,365 (60,482 duplicates, 62,890 reordered, 7,902 late, 2,098 injected corrections, 1,049 reverts, 3,536 deletes) |
| Baselines == batch rebuild from the log | **300 / 300** |
| Baselines == clean run (no corrections or deletes injected) | **107 / 107** |
| Insights == clean run (also no beyond-window late messages) | **57 / 57** |

Insights describe what was known when a shot happened, so a shot arriving after the
reorder window may legitimately be compared differently. In this sweep late messages
were almost always passes, and insights still matched in 50 of 50 such runs. The same
properties run as `hypothesis` tests in CI (`backend/tests/test_convergence.py`).

## Synthetic data

- **League:** 6 fictional clubs, 18 players each, 30 past matches and 1 live demo match.
  No real clubs, players or match data.
- **Realism:** calibrated against public league aggregates (passes, completion, shots,
  goals, conversion, shot speed). Results and sources: [docs/realism-report.md](docs/realism-report.md).
- **Format:** modeled on the *structure* of industry event and tracking feeds
  (create/update envelopes, versions, freeze frames, tracking shot speed); see
  [DATA_SCHEMA.md](DATA_SCHEMA.md). Each player has a hidden generator-only profile, so
  baseline estimates can be checked against the truth.
- **Sample:** `backend/data/sample/` holds the league, the match list and a live-feed
  excerpt including the VAR correction.

API: `GET /matches`; `GET /matches/{match_id}/league` (both squads with each player's
shrunk season shot-speed norm); and `GET /matches/{match_id}/stream?speed=N`, where each SSE
`data:` line is one viewer `StreamMessage`. In live mode the viewer loads the league endpoint
next to the stream URL, so its settings list the real squads.

## Planned Azure stack

Azure AI Foundry (models + agents), Microsoft Agent Framework (multi-agent orchestration),
Azure Container Apps (hosting).
