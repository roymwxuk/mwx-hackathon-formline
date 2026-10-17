# Roadmap and status

**Updated:** 2026-10-17 · **Deadline:** submissions close Oct 27; treat Oct 26 (JST) as the
deadline. · **Time budget:** 30–40 h in total.

The original plan lives in `CLAUDE.md` (kept local since the history cleanup). This file
is the tracked, up-to-date view: milestones, status, decisions and open actions. Each
milestone doc keeps its own detailed task table; the checklist below is the short version.

## Remaining checklist

**Must (needed to submit)**
- [ ] Merge `feat/deploy` (ahead of `main`: deploy scripts, live playback controls, roadmap) so CI publishes new images
- [ ] Redeploy to Azure with the resumable stream; confirm the ~240 s ingress cutoff is handled; measure the cold start; stop the apps again
- [ ] `scripts/azure/teardown.sh`
- [ ] ADR-009: Container Apps + scale to zero, GHCR, managed identity, Japan East, JSONL instead of Postgres, the Foundry 403 / "Foundry User" finding, the ingress cutoff
- [ ] README: "Deploy to Azure" and "Production readiness" sections (M4 task 8)
- [ ] Milestone 5: README polish (what it is, run locally, Azure services, data realism item (v), limitations, headline numbers)
- [ ] Milestone 5: architecture diagram
- [ ] Milestone 5: `docs/decisions.md` cleanup
- [ ] Milestone 5: demo video under 2 minutes, recorded against Azure (no trademarks, no copyrighted music)
- [ ] Milestone 5: pitch text naming the Microsoft and Azure technologies
- [ ] Submit (buffer day Oct 26)

**Should**
- [ ] Observability: confirm the JSON trace lines are queryable in Log Analytics (optional App Insights) (M4 task 5)
- [ ] Demo tuning: at 40:12 the Selector shows the placement card instead of the flagship speed card
- [ ] Live seek bar in the viewer (the backend already supports `start=mm:ss`)

**Could (only if time allows)**
- [ ] Infrastructure as code: Bicep + `azd` (M4 task 6)
- [ ] Foundry evaluations (M3 task 11)
- [ ] Half-time or full-time baseline recap card (M3 task 12, frontend gap 7)
- [ ] Studio graphics producer copilot (milestone 3b)

**Done recently**
- [x] Foundry resource, project and `gpt-4.1-mini` deployment; smoke test; identity-based auth (no keys)
- [x] Demo overlays narrated by Foundry (64 overlays, 60/60 model texts verified)
- [x] CI publishes amd64 images to GHCR on `main`
- [x] Container Apps environment and both apps deployed and verified (health, matches, stream, live narration via managed identity); now stopped
- [x] Budget alert (¥3,000/month, 50% and 100%)
- [x] Live playback controls: speed, pause/play, restart, slow-down near shots, resumable streams (`63d8b66`)

## Milestones

| # | Milestone | Planned | Status | Detail |
|---|---|---|---|---|
| 1 | Data schema, synthetic generator, history and live match, replay, realism report | Oct 9–11 | ✅ Done | ADR-005, `docs/realism-report.md` |
| 2 | Event log, stats engine, personal baselines with shrinkage, chaos injector, convergence tests | Oct 12–15 | ✅ Done | `docs/milestone-2-engine.md`, ADR-006, ADR-007 |
| 3 | Agents (Selector, Narrator, Verifier, Composer), overlay contract, EN/JA | Oct 16–19 | ✅ Done (Foundry connected); optional 11–12 not started | `docs/milestone-3-agents.md`, ADR-008 |
| 3b | ⭐ Optional plus: studio graphics producer copilot (a real agent with human approval, autonomy levels, audit log) | Only if time allows after milestone 4 MUST tasks | ⬜ Not started | `docs/milestone-3b-studio-copilot.md` |
| 4 | Azure deployment and live viewer UI | Oct 20–22 | 🟡 Tasks 1–4 and 7 done; deployed once and stopped; redeploy, task 5 (observability) and task 8 (docs) left; task 6 (IaC) optional | `docs/milestone-4-deployment.md`, `docs/frontend-gaps.md` |
| 5 | README, architecture diagram, decisions cleanup, demo video, pitch | Oct 23–25 | ⬜ Not started | — |
| — | Buffer and submit | Oct 26 | ⬜ | — |

## Branches

| Branch | Contains | State |
|---|---|---|
| `main` | Milestones 1–3, containers, CI, Foundry, deploy groundwork (PRs #1–#5) | Pushed; CI green |
| `feat/deploy` | Azure deploy/stop/start scripts, live playback controls, this roadmap | Ahead of `main` (these changes plus this roadmap); not pushed |

Feature branches are merged through pull requests; `main` is what CI publishes to GHCR.

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
| Tests and docs: 192 backend + 18 frontend tests, ADR-001 to ADR-008 | ✅ (ADR-009 pending) |
| Config via environment, no secrets in code | ✅ managed identity for Foundry, no keys |
| Cost controls: LLM call budget, response cache, scale to zero, budget alert | ✅ |
| Observability: JSON-line traces → Log Analytics / App Insights | 🟡 logs reach Log Analytics; queries not checked |
| Containers | ✅ backend 639 MB (non-root, health check), viewer 325 MB |
| CI | ✅ GitHub Actions: backend, frontend, image builds, GHCR publish on `main` |
| Azure deployment | ✅ Container Apps (scale to zero), Foundry; redeploy pending |
| Infrastructure as code (Bicep + `azd`, or Terraform) | ❌ milestone 4 task 6 (**optional**) |

## Decisions

| Where | Decision | Status |
|---|---|---|
| M3 D1–D2 | Foundry client + fake; hybrid Selector | ✅ Decided and built |
| M3 D3 | Precompute vs live narration | ✅ Both: precomputed Foundry overlays ship in the image; `?live=true` narrates live |
| M3 D4–D7 | Client-side personalization, favorites priority, JA narration, Foundry evals | See `docs/milestone-3-agents.md`; evals open (optional) |
| M4 E1 | Postgres for the event log | ✅ JSONL for the demo (Postgres not deployed) |
| M4 E2 | Viewer hosting | ✅ Container Apps |
| M4 E3 | IaC tool, if done | Open: Bicep + `azd` recommended (Terraform is the alternative) |
| Frontend gap 5 | Favorites priority for the card slot | ✅ Client picks the highest-priority card, favorites first |

## Actions waiting on the owner

1. **Check the official Hackathon Rules page** for any extra submission conditions and the exact
   deadline time zone.
2. **Check the five demo player names** (Tomas Reyner, Kenji Ito, Marco Silvestri, Daniel Okafor,
   Lukas Brandt) don't match real Premier League players.
3. **Approve each Azure step** of the redeploy (explained one at a time).
4. **Choose which optional tasks** to do, if any (IaC, Foundry evals, recap card, studio copilot).

## Known tuning item for the demo

At 40:12 the Selector picks Reyner's placement insight (salience 0.55) over the flagship speed
insight (0.49). Correct by salience, but the video story is speed. Revisit before recording.

## README numbers so far

| Claim | Number | Source |
|---|---|---|
| Realism | 14/14 checks within range of 2024/25 league figures | `docs/realism-report.md` |
| Feed robustness | 300/300 chaotic replays converge exactly | `python -m formline.convergence` |
| Shrinkage | 30% lower error than raw averages (45% for 1–4 shots) | `docs/shrinkage-accuracy.md` |
| Verifier | 99.6% of 1,075 injected errors caught, 0 false positives | `docs/verifier-catch-rate.md` |
