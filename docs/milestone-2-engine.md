# Milestone 2: engine core

**Status:** In progress. Tasks 1–7 done, 8 to do (updated 2026-10-17)
**Branch:** `feat/engine`, built on `feat/generator`
**Planned:** Oct 12–15 in `CLAUDE.md`, so running late. Estimate 7–9 h in total.

**Goal:** a deterministic engine (no LLM) that reads the generator's feed and produces
personal-baseline shot insights. It must survive a messy live feed (duplicates,
reordering, corrections) and converge to exactly the same state as a clean one.
These are the "depth levers" in `CLAUDE.md`.

## Tasks

| # | Task | Status | Commit | Tests |
|---|---|---|---|---|
| 1 | Event log and ingestion | ✅ Done | `01063bc` | 12 |
| 2 | Shot features (xG, PSxG, placement) | ✅ Done | `cf1e931` | 13 |
| 3 | Baseline engine (like-for-like ladder) | ✅ Done | `a4a025b` | 11 |
| 4 | Empirical Bayes shrinkage | ✅ Done | `a713cd9` | 9 |
| 5 | Insight detection and lineage | ✅ Done | `ccdd59c` | 8 |
| 6 | Chaos injector | ✅ Done | `4d89316` | 9 |
| 7 | Convergence tests (property-based) | ✅ Done | `bbb105a` | 4 (140 random cases) |
| 8 | Shrinkage accuracy vs hidden truth | ⏳ Next | | |

The backend suite is 80 tests in total (including generator and API tests).

---

## Task 1: event log and ingestion ✅

**Files:** `backend/src/formline/engine/log.py`, `ingest.py` · **Tests:** `tests/test_ingest.py`

- **Append-only event log.** Every distinct message is stored once, in arrival order.
  A message is a duplicate if its `(event_id, version)` is already in the log.
  In-memory and JSONL implementations share one interface (Postgres later, in the Azure step).
- **`current_events()`** gives the final state of every event: highest version wins,
  deletes remove it, sorted by event time. Every rebuild starts from this.
- **Ingestor** turns the messy feed into an ordered stream of changes:
  - duplicates and stale (older) versions are dropped and counted;
  - events wait in a **reorder window** (default 5 s of event time) and are released in
    event-time order once the watermark passes them;
  - events arriving after the watermark are applied immediately and flagged `late`;
  - a newer version of a still-buffered event replaces it silently;
  - a newer version or delete of an already-released event becomes a **`Revised`**
    change (before and after), so downstream state can roll back and re-apply.

**Verified:** the clean live feed gives zero late events and each event exactly once in
event-time order. The VAR overturn arrives as exactly one revision (goal → off target).

---

## Task 2: shot features ✅

**Files:** `backend/src/formline/engine/features.py`, `backend/src/formline/pitch.py` · **Tests:** `tests/test_features.py`

Pure functions of one shot plus squad data:

| Feature | How |
|---|---|
| Distance, angle | From the shot location |
| Zone (5) | six-yard, box central, box wide, outside central, long range |
| Body group | strong foot, weak foot, head, other (uses preferred foot) |
| Pressure | Nearest defender in the freeze frame < 2.3 m → pressured |
| Defenders in cone | Defenders inside the shooter–posts triangle |
| Placement (on target) | 0 = at the keeper's centre … 1 = top corner |
| xG | Fixed logistic formula: distance, angle, header, pressure, blockers, free kick; penalty 0.76 |
| PSxG (on target) | xG plus placement, speed and distance |

- The formulas are **fixed and documented**, not fitted to our synthetic outcomes, which
  would just learn the generator back. Only the intercepts are calibrated, to
  league-average conversion.
- **Results on 30 past matches:** mean xG 0.108 per shot (league ~11%), total xG 0.98× goals,
  mean PSxG 0.33 against a 34% on-target goal rate, AUC 0.72 (xG) and 0.73 (PSxG).
- Pitch geometry moved to `formline/pitch.py`, so the engine doesn't import the generator.

**Generator fix found here:** 35% of shots came from the six-yard box (median 11 m).
Open-play passes now stop short of the six-yard box, crosses land shallower, and shot
probability rises more gently near goal. Result: 9% six-yard, median 14 m, 69% inside
the box. Two location checks were added to the realism report (14 checks, all pass).

---

## Task 3: baseline engine ✅

**Files:** `backend/src/formline/engine/baselines.py`, `engine.py` · **Tests:** `tests/test_baselines.py`

- **Fallback ladder** (most specific first), filled per player **and** per position group:

  | Level | Key | Narrator wording |
  |---|---|---|
  | L0 | zone × body × pressure | "same zone, body part and pressure" |
  | L1 | zone × body | "same zone and body part" |
  | L2 | area (inside/outside box) × body | "same area and body part" |
  | L3 | body | "same body part, anywhere" |

  A lookup uses the most specific level with **≥ 5 shots** and reports which one, or
  flags the comparison as `thin` when no level reaches 5.
- **Exact fixed-point buckets:** values are stored as integers (speed × 10, placement × 1000,
  PSxG × 10000) in sorted lists plus integer sums. Add and remove are exact and
  order-independent. Percentiles and season bests or worsts come straight from the sorted values.
- **Metrics:** shot speed (all non-penalty shots), placement and PSxG (on-target shots).
- **Engine:** compares each shot **before** adding it (never against itself). A revision
  removes the old version and re-adds the new one, with no recompute.

**Verified:** Reyner's 84.1 km/h shot at 40:12 reads below his norm. After the VAR
revision, the cancelled goal's placement and PSxG are gone from every bucket. Incremental
processing of the live feed equals a rebuild from the final log, exactly.

**Finding:** the busiest strikers have only 33–44 shots across 30 matches. With a minimum
of 8, they rarely got a zone-level comparison, so the minimum is 5 and shrinkage handles
small samples.

---

## Task 4: empirical Bayes shrinkage ✅

**Files:** `backend/src/formline/engine/shrinkage.py` (plus `engine.py`, `baselines.py`) · **Tests:** `tests/test_shrinkage.py`

- **Model** (per metric × position group × body part): a player's true mean ~ N(group mean, τ²),
  each shot ~ N(true mean, σ²).
  **shrunk = (n · his mean + k · prior) / (n + k)**, with **k = σ² / τ²** and weight on his
  own shots = n / (n + k).
- σ² and τ² come from the history by method of moments. **k is learned, not hand-picked**
  (capped at 50).
- **Prior** = the group's mean at the **same ladder level, excluding the player**.
- **Fallback** when a group has too few players: the same body part across all groups,
  never across body parts, so headers don't inherit a foot-shot average.
- **Priors are fitted once** after the historical bootstrap, then frozen.
- **Percentiles are model estimates** from N(shrunk, σ² + σ²/(n+k)), clipped to 1–99,
  reported next to the raw rank.

**Examples (live match):**

| Shot | Raw rank | After shrinkage |
|---|---|---|
| Okafor header 57.1 km/h (5 comparable) | 0th (last of 5) | 59th |
| Reyner 93.1 km/h (5 comparable) | 100th | 75th |
| Reyner 84.1 km/h, 40:12 (well supported) | 20th | 21st |

**Finding:** PSxG gets the maximum k (50). Players barely differ in finishing compared with
shot-to-shot noise, which matches the public view that finishing skill is hard to detect.
Finishing insights need cautious wording.

---

## Task 5: insight detection and lineage ✅

**Files:** `backend/src/formline/engine/insights.py`, `pipeline.py` · **Tests:** `tests/test_insights.py`

- **Detection** (deterministic): a metric on a live shot becomes an insight when its
  **estimated** percentile (after shrinkage) is ≤ 25 or ≥ 75, or when it is a **season
  best or worst** speed with the same body part.
  - Types: `shot_speed_vs_norm`, `placement_vs_norm`, `finish_vs_norm`, `season_best`, `season_worst`.
  - Season records need ≥ 5 earlier shots with that body part and must agree with the
    direction against the norm. Speed only, because placement and PSxG are too noisy.
  - Thin comparisons with fewer than 3 shots are skipped.
  - **Salience** (0–1) grows with extremity, scaled by the weight on the player's own
    shots, plus bonuses for season records and goals. **Confidence** is high, medium or
    low from that weight. Choosing what to show is the Insight Selector's job (milestone 3).
- **`facts`**: every number a narrator may use, rounded for display (value, norm, delta,
  estimated percentile, sample size, comparison label, weight, group prior, zone, body
  part, pressure, distance, outcome, xG, PSxG, season record). The verifier checks
  narratives against these.
- **Lineage:** each insight cites `source_event_ids` (the shot plus its key pass) and has a
  deterministic id. The tracker indexes event id → insights. On a revision it re-detects
  from the corrected shot. Each dependent insight is then unchanged, **corrected**
  (version 2, `supersedes`, with a reason such as "outcome goal → off_target"), or
  **retracted** (with a reason such as "placement no longer applies (outcome off_target)").
  Deletes retract everything citing the event.
- **`LivePipeline`**: feed message → ingestor → baseline engine → insight tracker.

**Live match result:** 22 insights. Examples: Reyner's 84.1 km/h at 40:12 (below his norm
of 92.3, est. 21st percentile, medium confidence) and Silvestri's 107.6 km/h season best.
**VAR at 63:42:** Reyner's goal had a season-best speed insight (118.3 km/h) and a placement
insight. After the overturn, placement was **retracted** (no longer on target) and the
season best was **corrected** (still his fastest shot, but no longer a goal).

**Known limit:** a revision rolls the baseline back exactly, but insights already produced
for later shots are not recomputed (their baseline briefly included the revised shot).

## Task 6: chaos injector ✅

**Files:** `backend/src/formline/chaos.py` (plus the `chaos` option in `api.py`) · **Tests:** `tests/test_chaos.py`

- `inject(feed, ChaosConfig(seed=...))` gives every message an arrival time, damages the
  schedule and delivers in arrival order. It returns the messages plus a `ChaosReport`.

  | Damage | Default rate | What happens |
  |---|---|---|
  | Duplicate | 3% of messages | Same message (same `message_id`) again, 0.1–10 s later |
  | Reorder | 5% | Jitter of 0.2–3 s, inside the 5 s reorder window |
  | Late | 1% | Delay of 6–30 s, beyond the window |
  | Correction | 15% of eligible shots | New version 20–120 s later: outcome swapped (e.g. saved → off target) or, 30% of the time, a different shooter from the same team |
  | Revert | 50% of corrections | A further version restoring the original |
  | Delete | 0% (opt-in) | The event is retracted entirely |

- **Nothing is dropped** (missing data is out of scope). Provider `emitted_at` and
  `sequence` stay on each message; injected versions get new, higher versions and sequence numbers.
- Shots that already have a real update (the VAR overturn) are never given injected
  corrections, so versions never collide.
- Deterministic per seed, so any failing convergence case can be replayed exactly.
- **API:** `GET /matches/{id}/stream?chaos=true&chaos_seed=N` replays the live match with
  chaos, for showing the pipeline coping live in the demo.

**On the live match (seed 1):** 1,324 messages in, 1,386 out: 51 duplicates, 60 reordered,
12 delayed, 6 corrections, 5 reverts. The ingestor dropped all 51 duplicates and produced
12 revisions. 9 of the 12 delayed messages crossed the window and were flagged late; the
other 3 still landed inside it, because the window follows the latest event time and
quiet spells leave room.

## Task 7: convergence tests ✅

**Files:** `backend/src/formline/convergence.py` · **Tests:** `tests/test_convergence.py`

- **Truth** = the final version of every event in the log (`current_events`), per ADR-007.
- `ConvergenceChecker` holds the clean reference for a match. For each chaotic replay it runs
  the full live pipeline (ingest → baselines → insights) from a fresh copy of the
  season-so-far engine and checks:
  1. **Baselines == batch rebuild from the log**: always required.
  2. **Baselines == clean run**: required when no corrections or deletes were injected.
  3. **Insights == clean run**: required when there were also no beyond-window late
     messages. A late shot can legitimately change what later shots were compared against.
- **Property-based tests** (`hypothesis`): 60 + 40 + 40 random chaos configurations per run,
  plus one fixed heavy-chaos case (50% duplicates, 50% reorder, 20% late, corrections on
  every eligible shot, 10% deletes).
- **Sweep CLI** for the README: `uv run python -m formline.convergence --runs 300`.

**Result (300 replays, 464,365 messages):** 60,482 duplicates, 62,890 reordered, 7,902 late,
2,098 corrections, 1,049 reverts and 3,536 deletes injected.

| Check | Result |
|---|---|
| Baselines == rebuild from log | **300/300** |
| Baselines == clean run | **107/107** |
| Insights == clean run (in-window chaos) | **57/57** |
| Info: insights unchanged despite late messages | 50/50 (late messages were almost always passes) |

**Why it holds:** idempotent ingestion keyed on (event_id, version), highest version wins,
the reorder buffer releases in event-time order, and the integer buckets make add and
remove exact and order-independent (ADR-006).

## Task 8: shrinkage accuracy vs hidden truth ⬜

- Compare raw and shrunk baselines with the generator's hidden profiles
  (`gen_only/latent_profiles.json`), especially for small samples. This gives a concrete
  number for the README ("shrinkage cuts error by X% for players with fewer than N shots").

---

## Decisions

- ADR-005, item 8: generator shot-location fix.
- ADR-006: fallback ladder, exact fixed-point buckets, empirical Bayes shrinkage, frozen
  priors, model-estimated percentiles.
- ADR-007: chaos injector design (damage delivery not content, five damage types,
  realistic corrections, no drops, real updates left alone, deterministic per seed) and the
  definition of convergence.

## Out of scope here

Overlays, narration, verification and agents (milestone 3); connecting the engine to the
UI; Postgres and Azure.
