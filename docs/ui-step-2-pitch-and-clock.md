# UI step 2: pitch and match clock

**Status:** Done (2026-10-16). Superseded by ADR-004: the viewer was replaced by the claude.ai prototype.

**Goal:** open the viewer and watch the mock match (`frontend/src/mock/demo-match.ts`)
replay on a 2D pitch with a controllable clock. Overlay cards come in step 3.

## What gets built

| Piece | What it does |
|---|---|
| **Replay clock** (`useReplayClock` hook) | Owns match time, advanced by `requestAnimationFrame`. Play/pause, speed 1×/2×/4×/8×, scrub bar over 38:00–41:42. At 4× the mock runs about 56 s, which fits the 2-minute demo video. |
| **Feed resolver** (`resolveFeed(feed, clockMs)`, pure function) | Returns the events visible at the current clock. An update applies only once its `emitted_at` has passed, so Reyner's header shows as a goal until VAR concludes, then flips to disallowed. The highest version wins. |
| **Pitch** (SVG, in meters, 105 × 68) | Full markings: halfway line, centre circle, boxes, six-yard boxes, spots, arcs, goals. The away team is flipped onto the shared pitch (ADR-003). |
| **Ball and name tag** | The ball moves along each pass over its `duration_ms`, with the carrier's name tagged. This is the brief's "player identification" feature in minimal form. |
| **Trails and shot markers** | The last few passes fade behind the ball. Shot markers: goal, saved, off target, VAR-overturned. |
| **Scoreboard** | Score and clock, derived from resolved events, so the score visibly reverts when VAR cancels the goal. |
| **Event log** | A compact list under the pitch. Useful for debugging; later, overlays link back to the events they cite. |

The Next.js starter page (`frontend/src/app/page.tsx`) is replaced by this viewer.

## Decisions

- **SVG, not canvas.** A few dozen moving elements is trivial for SVG, which stays
  sharp at any size and is easy to style and test.
- **No animation library.** One `requestAnimationFrame` loop drives everything,
  so all elements share one clock.
- **The clock is in match milliseconds,** the same unit as `match_clock_ms` on
  overlays, so step 3 reuses it directly.

## Changes from the plan

- Added a `?t=mm:ss` URL parameter that opens the replay at a given moment, for
  screenshots and for recording the demo video.
- The mock covers 38:00–41:42, not 38:00–43:30 as first stated.
- The Next.js starter assets in `frontend/public/` were removed (unused).

## Out of scope

Overlay cards (step 3), settings panel (step 4), two-viewer split (step 5),
connecting to the backend (step 6), and visual polish (Oct 20–22).

## Verification

- Unit tests for `resolveFeed` (including the VAR flip) and for ball interpolation along a pass.
- Typecheck and lint.
- Run in a browser and screenshot the pitch mid-match.

**Estimate:** 1–1.5 hours.

## Where this fits

| Step | What | When (per `CLAUDE.md`) |
|---|---|---|
| 1 | Contract types and mock replay | Done (`9d0c74b`) |
| 2 | Pitch and match clock | Done |
| 3 | Overlay layer: show/correct/retract, timed, with lineage | Now |
| — | Backend core: generator to schema, event log, baseline engine with shrinkage, chaos injector, convergence tests | Overdue (planned Oct 12–15) |
| — | Agent layer: Selector, Narrator, Verifier, Composer; EN/JA | Oct 16–19 |
| 4 | Settings panel | Oct 20–21 |
| 5 | Two viewers side by side | Oct 21–22 |
| 6 | Connect the UI to the backend stream | After the agents work |
| — | Azure deployment, README, video, pitch | Oct 23–25, submit Oct 26 |

After steps 2 and 3, UI work pauses so the backend core, now the main schedule
risk, gets the next block of time.
