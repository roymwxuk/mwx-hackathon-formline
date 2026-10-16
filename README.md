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
