# Roadmap and status

**Updated:** 2026-10-17 · **Deadline:** submissions close Oct 27; treat Oct 26 (JST) as the
deadline. · **Time budget:** 30–40 h in total.

The original plan lives in `CLAUDE.md` (kept local since the history cleanup). This file
is the tracked, up-to-date view: milestones, status, decisions and open actions.

## Milestones

| # | Milestone | Planned | Status | Detail |
|---|---|---|---|---|
| 1 | Data schema, synthetic generator, history and live match, replay, realism report | Oct 9–11 | ✅ Done | ADR-005, `docs/realism-report.md` |
| 2 | Event log, stats engine, personal baselines with shrinkage, chaos injector, convergence tests | Oct 12–15 | ✅ Done | `docs/milestone-2-engine.md`, ADR-006, ADR-007 |
| 3 | Agents (Selector, Narrator, Verifier, Composer), overlay contract, EN/JA | Oct 16–19 | ✅ Code complete; Azure steps 5.1/5.3 wait on the owner; optional 11–12 not started | `docs/milestone-3-agents.md`, ADR-008 |
| 3b | ⭐ Optional plus: studio graphics producer copilot (a real agent with human approval, autonomy levels, audit log) | Only if time allows after milestone 4 MUST tasks | ⬜ Not started | `docs/milestone-3b-studio-copilot.md` |
| 4 | Azure deployment and live viewer UI | Oct 20–22 | 🟡 UI done early; tasks 1–2 (containers, CI) done; Azure deployment next | `docs/milestone-4-deployment.md`, `docs/frontend-gaps.md` |
| 5 | README, architecture diagram, decisions cleanup, demo video, pitch | Oct 23–25 | ⬜ Not started | — |
| — | Buffer and submit | Oct 26 | ⬜ | — |

## Branches

| Branch | Contains | Pushed? |
|---|---|---|
| `main` | First commit only | Yes |
| `scaffold/initial-setup` | Scaffold, viewer UI (milestone 4 UI) | Yes |
| `feat/generator` | Milestone 1 | No |
| `feat/engine` | Milestone 2, frontend gaps 2–3 | No |
| `feat/agents` | Milestone 3, milestone 4 plan | No |

Each branch builds on the previous one. Nothing is merged into `main` yet.

## Product focus (updated 2026-10-17)

**Main path:** the current product: deterministic engine → agentic workflow (Selector,
Narrators, Verifier, Composer on Microsoft Agent Framework) → timed overlays on personalized
audience feeds (EN/JA, casual/analyst, favorites, focus mode, "my metric"), with the VAR
correction path. Then milestone 4 (CI, Azure deployment) and milestone 5 (README, video, pitch).

**Optional plus: studio copilot (milestone 3b).** A graphics producer copilot for the
broadcaster's gallery: a real agent that proposes graphics with reasons, a human approves or
rejects in a producer console, and approved cards appear on the audience viewer. It strengthens
agentic design and the Enterprise angle, and the brief supports a studio focus (title "for
Premier League Studio"; stage (e) allows focusing on overlays in the "production path"). Do it
only if time allows after milestone 4's MUST tasks, and before the final deployment and video.

## What the hackathon requires (from `HACKATHON_BRIEF.md`)

**Hard submission requirements:**
1. A project pitch or description naming the Microsoft and Azure technologies used.
2. A demo video under 2 minutes, "showing the project working on its target platform", at a
   public URL, with no third-party trademarks or copyrighted music.
3. A public GitHub repository.

**Is a live Azure server required?** Not listed as a requirement: there is no requirement for a
URL judges can open. But Azure clearly matters:
- the challenge is "an AI insights engine **running on Azure**";
- the video must show it on its target platform (Azure);
- the rubric scores "effective use of hero technologies" and "production deployment readiness"
  (20% each), and the categories include Best Use of Microsoft Foundry and Best Azure Cloud
  Native Integration.

**Plan:** deploy to Azure (Foundry model + Container Apps), record the video against it, then
scale to zero. **To confirm:** the official Hackathon Rules page (eligibility, exact deadline
time zone, data rules) may add conditions such as a working demo during judging.

## Production deployment readiness

"Production deployment readiness" is broader than IaC: it asks whether a team could run this in
production. Signals and status:

| Signal | Status |
|---|---|
| Reliability: failure recovery, retries, fallbacks, deterministic replays | ✅ |
| Correctness controls: verifier (99.6% catch rate), lineage, corrections | ✅ |
| Tests and docs: 182 backend + 17 frontend tests, ADR-001 to ADR-008 | ✅ |
| Config via environment, no secrets in code | 🟡 managed identity in milestone 4 |
| Cost controls: LLM call budget, response cache, scale to zero | 🟡 scale to zero in milestone 4 |
| Observability: JSON-line traces → Log Analytics / App Insights | 🟡 milestone 4 |
| Containers | ✅ backend 639 MB (non-root, health check), viewer 325 MB |
| CI | ✅ GitHub Actions: backend, frontend, image builds |
| Azure deployment | ❌ milestone 4 (MUST) |
| Infrastructure as code (Bicep + `azd`, or Terraform) | ❌ milestone 4 task 6 (**optional**) |

## Open decisions

| Where | Decision | Recommendation |
|---|---|---|
| M3 D1–D7 | Model and provider, hybrid Selector, precompute vs live narration, client-side personalization, favorites priority, JA narration, Foundry evals | See `docs/milestone-3-agents.md`; D1 and D2 are already implemented as recommended (Foundry client + fake; hybrid Selector) |
| M4 E1 | Postgres for the event log | Keep JSONL for the demo |
| M4 E2 | Viewer hosting | Container Apps |
| M4 E3 | IaC tool, if done | Bicep + `azd` (Terraform is the alternative) |
| Frontend gap 5 | Favorites priority for the card slot | Client picks the highest-priority card, favorites first |

## Actions waiting on the owner

1. **Create a Microsoft Foundry project and a small model deployment** (milestone 3, task 5.1),
   then run `uv run python -m formline.agents.llm --smoke`. Not blocking until the real narration
   run.
2. **Check the official Hackathon Rules page** for any extra submission conditions.
3. **Push the local branches** for backup:
   `git push -u origin feat/generator feat/engine feat/agents`.
4. **Check the five demo player names** (Tomas Reyner, Kenji Ito, Marco Silvestri, Daniel Okafor,
   Lukas Brandt) don't match real Premier League players.
5. Choose the IaC tool (E3) if you want the optional IaC task.

## Known tuning item for the demo

At 40:12 the Selector picks Reyner's placement insight (salience 0.55) over the flagship speed
insight (0.49). Correct by salience, but the video story is speed. Revisit when the real model is
connected.

## README numbers so far

| Claim | Number | Source |
|---|---|---|
| Realism | 14/14 checks within range of 2024/25 league figures | `docs/realism-report.md` |
| Feed robustness | 300/300 chaotic replays converge exactly | `python -m formline.convergence` |
| Shrinkage | 30% lower error than raw averages (45% for 1–4 shots) | `docs/shrinkage-accuracy.md` |
| Verifier | 99.6% of 1,075 injected errors caught, 0 false positives | `docs/verifier-catch-rate.md` |
