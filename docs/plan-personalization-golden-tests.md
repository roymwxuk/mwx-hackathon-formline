# Plan: golden tests for viewer personalization

**Status:** Planned (2026-10-18). Not started. Optional: no behaviour change.
**Origin:** a review by another LLM (used as a reference, not a spec) pointed at unclear
ownership of personalization and missing end-to-end checks. This plan takes its most useful
point; see "Context" for what was kept and what was not.

## Goal

Lock the product's core promise, *different viewers see different insights at the same
moment*, with **golden tests**: given a viewer profile and a moment in the real demo match,
the card on screen must be exactly the expected one.

## What is tested today, and what is missing

- **Today:** the selection functions are tested separately on small hand-made inputs.
  `personalize()` (which cards this viewer may see) gets 2–3 fake overlays; `pickCard()`
  (which of those wins the slot) gets 2 fake cards (`frontend/src/lib/logic.test.ts`).
- **Missing:** nothing checks the **whole chain on the real data**: the 88 Foundry-narrated
  demo overlays (`backend/demo/overlays/mtc_s26_md11_har_nor.jsonl`) through
  `applyOverlays` (corrections, retractions), `personalize` and `pickCard` to the one card
  on screen. A later change could break that chain while every unit test still passes.

## Test design

A table of canonical viewer profiles × key moments, each with the expected card. The cells
below are illustrations; the real expected values are read from the data once, checked by
eye, then fixed in the test.

| Viewer profile | 12:10 | 40:16 | 63:46 | 65:30 (after VAR) |
|---|---|---|---|---|
| English analyst, no favorites, metric all | Reyner 101 km/h | Reyner placement 44/100 | Reyner 118 km/h | corrected 118 card |
| English casual, favorite **Reyner** | Reyner 101 km/h | Reyner placement | Reyner 118 km/h | corrected card + banner |
| English casual, favorite **Brandt** only | no card yet | no card | Brandt's previous card, or none | banner only |
| Japanese casual, favorite Reyner | JA card | JA placement card | 「今季最速シュート！」 | JA corrected card |
| English casual, Reyner, **my metric: shot speed** | Reyner 101 km/h | **speed card, 84 km/h** (secondary) | 118 km/h card | corrected card |
| English casual, Reyner, **my metric: finishing** | (nothing new) | placement card | **placement secondary** (47/100) | placement withdrawn |
| English casual, favorite **club** (Harbourside) | Reyner card | Reyner card | Reyner card | corrected card |

Each test:

1. loads the real demo overlays file (`frontend/src/lib/contract.test.ts` already reads a
   backend file this way) and the league's players (for favorite clubs);
2. replays the overlays up to the moment, in emission order, through `applyOverlays`;
3. applies the profile with `personalize` and picks with `pickCard` at that match time;
4. asserts the exact card: its `overlay_id`, plus the headline for readability. "No card"
   and "banner shown" are asserted explicitly.

## Edge cases covered

- no favorites; one favorite player; several favorites; a favorite club;
- player focus (does not filter, only the strip; asserted unchanged);
- each "my metric" value, including the secondary cards only those viewers see;
- casual vs analyst, English vs Japanese;
- competing cards at the same time (primary and secondary for one shot; favorites first,
  then priority, then newest);
- the VAR correction: a retracted secondary, a corrected primary, and the banner.

## What it protects

- the core promise, so a regression fails a test instead of surfacing during recording;
- the edge cases above, deterministically, on the data the demo actually uses;
- an easy interview answer: "the personalization rules have golden tests on the real match".

## Effort and scope

About 45 minutes; frontend tests only (`frontend/src/lib/personalization.golden.test.ts`);
no change to app behaviour. If the demo overlays are ever regenerated, the expected values
are re-read and re-checked once.

## Context: what the review got right and what was not taken

- **Taken:** golden tests on real data (this plan); a short ADR stating who decides what (the
  backend decides which insights exist and their priority, the browser decides which of them
  each viewer sees), which fits with this work.
- **Worth recording as a known limitation:** viewer settings cannot bring back an insight the
  backend never produced. The Selector runs once for everyone (one card per shot, a
  per-player cooldown, at most 3 cards per 10 minutes); the "my metric" secondary cards are a
  partial answer. True per-viewer selection would need the backend to select per profile.
- **Not taken now:** moving personalization to the server (4–6 h of risky change before the
  deadline, no visible demo gain; a post-hackathon option). The review's claim that the docs
  contradict each other is mostly outdated: ADR-004 superseded ADR-003 item 3, and the ADR
  index says so. Contract fields it listed ("slot", "viewer profile") do not exist and are not
  needed with client-side selection.
