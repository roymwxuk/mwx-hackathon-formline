# Milestone 4: Azure deployment and production readiness

**Status:** Planned, not started (2026-10-17)
**Branch:** `feat/deploy`, to be built after milestone 3 (`feat/agents`)
**Planned:** Oct 20–22 in `CLAUDE.md` ("Azure deployment and the live viewer UI"). The viewer UI
is already done (see `docs/frontend-gaps.md`), so this milestone focuses on deployment and on
the rubric's **"production deployment readiness"** (20%).
**Estimate:** about 4–5 h for MUST and SHOULD items; optional IaC adds about 2–3 h.

## Why

The brief describes "an AI insights engine **running on Azure**", and the demo video must show it
"working on its target platform". A permanently running public server is not listed as a
submission requirement (check the official Hackathon Rules page to confirm), so the plan is:
deploy, record the video against Azure, then scale to zero.

## Readiness: where we stand

| Signal | Status before this milestone |
|---|---|
| Reliability: failure recovery, retries, fallbacks, deterministic replays | ✅ Workflow recovery, convergence 300/300, chaos stress runs |
| Correctness controls: verifier, lineage, corrections | ✅ 99.6% verifier catch rate, VAR correction path |
| Tests and docs | ✅ 174 backend + 15 frontend tests, ADR-001 to ADR-007 |
| Config via environment, no secrets in code | 🟡 Done; managed identity not yet |
| Cost controls | 🟡 LLM call budget and cache done; scale to zero comes with deployment |
| Observability | 🟡 JSON-line logs and run traces; not wired to Azure |
| Containers, deployment, CI | ❌ This milestone |
| Infrastructure as code | ❌ Optional, this milestone |

## Decisions to make

| # | Decision | Options | Recommendation |
|---|---|---|---|
| E1 | Postgres for the event log? | (a) keep the JSONL log in the container; (b) Azure Database for PostgreSQL Flexible Server | ★ (a) for the demo: the event log interface already allows Postgres later. (b) only if time allows; it costs money while running. |
| E2 | How the viewer is hosted | (a) Next.js server in Container Apps; (b) static export on Azure Static Web Apps | ★ (a): one platform, one deploy flow, same scale-to-zero. |
| E3 | IaC tool (if task 6 is done) | (a) Bicep + Azure Developer CLI (`azd`); (b) Terraform | ★ (a): Azure-native, `azd up` is a one-command deploy, and `azd` can generate the GitHub Actions pipeline. (b) is fine if the owner prefers his AWS experience. |

## Tasks

| # | Task | Priority | Estimate |
|---|---|---|---|
| 1 | Dockerfiles (backend, viewer) and local `docker compose` | MUST | 1 h |
| 2 | GitHub Actions CI: lint, typecheck, tests on every push | MUST | 0.5 h |
| 3 | Deploy to Azure Container Apps (manual `az` steps, scripted) | MUST | 1.5 h |
| 4 | Managed identity for Foundry (no API keys) | SHOULD | 0.5 h |
| 5 | Observability: logs to Log Analytics, optional Application Insights traces | SHOULD | 0.5 h |
| 6 | **Optional: infrastructure as code** (Bicep + `azd`, or Terraform) | COULD | 2–3 h |
| 7 | Live replay controls and end of stream (frontend gap 4) | SHOULD | 1 h |
| 8 | Docs: README "Deploy" and "Production readiness" sections, ADR-009 | MUST | 0.5 h |

### Task 1: containers (MUST)

- `backend/Dockerfile`: Python 3.12 slim, `uv sync --frozen --no-dev`, runs `formline-gen generate`
  at build time (the data is deterministic and about 28 MB), serves `uvicorn`, health check on
  `/health`.
- `frontend/Dockerfile`: multi-stage Next.js build (`output: "standalone"`), stream URL passed at
  build time (`NEXT_PUBLIC_STREAM_URL` is inlined).
- `docker-compose.yml` at the root: both services, so `docker compose up` runs the whole demo
  locally.
- **Done when:** `docker compose up` shows the viewer playing the live match with cards.

### Task 2: CI (MUST)

- `.github/workflows/ci.yml`: backend (`uv sync`, `ruff`, `pytest`) and frontend (`pnpm install`,
  `lint`, `typecheck`, `test`, `build`) on every push and pull request. Tests never need Azure (the
  fake LLM client).
- **Done when:** the workflow is green on GitHub.

### Task 3: deploy to Azure Container Apps (MUST)

- Resource group, Container Apps environment, Azure Container Registry (or GitHub Container
  Registry), two container apps (backend, viewer), min replicas 0 so they scale to zero.
- Settings as environment variables: Foundry endpoint and deployment, CORS origin (the viewer's URL).
- A script (`scripts/deploy.sh`) with the `az` commands, so the deploy is repeatable even without IaC.
- **Done when:** the viewer's Azure URL plays the live match with LLM-narrated cards from Foundry.

### Task 4: managed identity for Foundry (SHOULD)

- The backend container app gets a system-assigned managed identity with the right role on the
  Foundry project. `llm.py` uses `DefaultAzureCredential` (managed identity in Azure,
  `az login` locally) instead of `AzureCliCredential`.
- **Done when:** no API key or secret exists anywhere, and Azure narration still works.

### Task 5: observability (SHOULD)

- Container logs flow to Log Analytics (the default for Container Apps). The workflow's JSON-line
  trace makes every handoff and verdict queryable.
- Optional: Agent Framework's OpenTelemetry export to Application Insights for per-agent spans.
- **Done when:** a KQL query shows the run's verifier rejections and template fallbacks.

### Task 6: optional infrastructure as code (COULD; E3)

Only if milestones 3–4 MUST items are done and time allows. Task 3's script remains the fallback.

- **Bicep + `azd`** (recommended):
  - `infra/main.bicep` (+ modules): Log Analytics, Container Apps environment, container
    registry, two container apps (scale to zero), managed identity and its role assignment on the
    Foundry project.
  - `azure.yaml`: services `backend` and `frontend` mapped to their Dockerfiles, so `azd up`
    provisions and deploys everything.
  - Optional: `azd pipeline config` to generate a GitHub Actions deploy workflow.
- **Or Terraform:** the same resources with the `azurerm` provider, plus a short deploy script.
- **Done when:** a fresh resource group can be created and deployed with one command, and the README
  documents it.

### Task 7: live replay controls (SHOULD; frontend gap 4)

- Backend replay accepts a start time and slows down around overlays (as the mock does), and sends
  `{kind: 'end'}`. The viewer passes speed and start time, shows "Full time" and stops reconnecting.
- **Done when:** the demo video can be recorded from the Azure deployment at a readable pace.

### Task 8: docs (MUST)

- README: "Deploy to Azure" (script or `azd up`), "Production readiness" (the table above, updated),
  and the Azure services used, for the pitch.
- ADR-009: hosting, scale to zero, managed identity, why JSONL instead of Postgres for the demo, and
  the IaC choice if done.

## Acceptance criteria

1. The live demo runs on Azure Container Apps with LLM-narrated cards from Microsoft Foundry.
2. CI runs lint and tests on every push.
3. No secrets in code or configuration; Foundry access uses identity.
4. The README explains how to deploy and what makes the system production-ready.
5. Optional: one-command provisioning and deployment with IaC.

## Out of scope

Kubernetes (AKS), multi-region, autoscaling rules beyond scale to zero, a production Postgres
cluster, and authentication for the viewer.
