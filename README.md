# mwx-hackathon-formline

**Formline** — a Synthetic Match Insights Engine for the *Inside the Game* Developer Hackathon
(Microsoft × Premier League). Submissions close **Oct 27, 2026**. Full brief: [HACKATHON_BRIEF.md](HACKATHON_BRIEF.md).

Formline turns synthetic football events into explainable, personalized match intelligence
for studio and streaming use.

## Pipeline

| Stage | Module | What it does |
|---|---|---|
| a. Ingest | `backend/src/formline/pipeline/ingest.py` | Synthetic, football-realistic event generator |
| b. Interpret | `.../interpret.py` | Live match state: score, possession, pass accuracy, pass difficulty |
| c. Explain | `.../explain.py` | Agents explain *why* moments matter (Microsoft Agent Framework + Azure AI Foundry) |
| d. Render | `.../render.py` | Timed, machine-readable overlay payloads |
| e. Personalize | `.../personalize.py` | Casual / analyst / player-focus modes, language, favorite club & player |

## Layout

```
backend/    Python 3.12 · FastAPI · Microsoft Agent Framework (uv)
frontend/   Next.js · TypeScript · Tailwind (pnpm)
HACKATHON_BRIEF.md  Hackathon brief
```

## Run locally

```bash
# backend → http://localhost:8000
cd backend
cp .env.example .env        # fill in Azure AI Foundry details
uv sync
uv run uvicorn formline.api:app --reload

# frontend → http://localhost:3000
cd frontend
pnpm install
pnpm dev
```

Live event stream: `GET /matches/{match_id}/stream` (Server-Sent Events).

Tests: `cd backend && uv run pytest`

## Planned Azure stack

Azure AI Foundry (models + agents), Microsoft Agent Framework (multi-agent orchestration),
Azure Container Apps (hosting).
