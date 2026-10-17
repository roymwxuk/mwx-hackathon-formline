# Frontend gaps: from mock data to real backend data

**Updated:** 2026-10-17 · **Branch:** `feat/agents`

The viewer UI (`frontend/`) is feature-complete for the demo **on its built-in mock data**
(`frontend/src/mock/demo-match.ts`). This list tracks what remains for it to work on
**real backend data** (the generator feed, engine insights and agent overlays).

## Summary

| # | Gap | Status | Blocked on | Commit |
|---|---|---|---|---|
| 1 | No overlay cards in live mode | ✅ Fixed | | milestone 3 tasks 9–10 |
| 2 | Clubs and players hard-coded from the mock | ✅ Fixed | | `7ac4ec1` |
| 3 | Half-time ordering and live clock | ✅ Fixed | | `c4db013` |
| 4 | Live mode: no pause, seek, slow-down or end-of-stream | 🟡 Partly | End of stream and `until=mm:ss` done; slow-down and seek in milestone 4 task 7 | milestone 3 task 10 |
| 5 | Favorites don't take priority for the overlay slot | ✅ Fixed | | milestone 3 task 10 |
| 6 | Not checked in a browser against the backend | ✅ Done | Three key moments rendered from backend data (`docs/ui/live/`) | milestone 3 task 10 |
| 7 | Optional half-time or full-time recap card | ⬜ Open | Milestone 3 | |

---

## 1. No overlay cards in live mode ✅ Fixed (milestone 3, tasks 9–10)

- **Now:** the backend streams overlays with the events (cached by `formline-gen overlays`, or
  live with `?live=true`); the viewer renders them in live mode with no mock data.

**Original problem:**

- **Problem:** the backend streams raw match events only, so in live mode the card slot
  shows "Waiting for the first insight…" all match.
- **Fix:** milestone 3. The agent layer (Insight Selector, Narrator, Verifier, Overlay
  Composer) turns engine insights into overlays and streams them as
  `{kind: 'overlay', overlay}` messages on the same SSE stream.
- **Contract to honour:** `frontend/src/lib/types.ts` `Overlay` (DATA_SCHEMA.md §6.5): generic
  slots (`tag`, `headline`, `sub`, `bars` for casual, `rows` for analyst), `player_id`,
  `metric`, `source_event_ids`, `verified`, and `op` show/correct/retract.

## 2. Clubs and players hard-coded from the mock ✅ Fixed (`7ac4ec1`)

- **Was:** the settings lists showed the mock's 2 clubs and 5 players, and focus mode used
  hand-written season norms.
- **Now:**
  - The backend serves `GET /matches/{match_id}/league`: both clubs (home first) and their
    full squads (36 players for HAR vs NOR), with each player's season shot-speed norm, which
    is the engine's shrunk strong-foot baseline from the 30 past matches (e.g. Reyner 88.4 km/h).
  - The viewer loads it in live mode (`frontend/src/lib/league.ts`, URL derived from the stream
    URL), groups players by club, and offers focus mode only for players with a norm.
  - The focus strip averages foot shots only. If the league can't load, the header says so
    and the mock squads remain as a fallback.
- **Verified:** live-mode render against the backend showed the real squads, Reyner's 97 km/h
  tonight against his norm of 88, and the 1–0 final score after VAR.

## 3. Half-time ordering and live clock ✅ Fixed (`c4db013`)

- **Was:** the match clock restarts at 45:00 in the second half. Sorting by clock alone
  interleaved first-half stoppage time (e.g. 46:30) with the start of the second half, and
  the live clock froze at 46:30 until the second half passed it. The mock never hit this;
  the real feed does.
- **Now:** events sort by period, then clock, then event id (`compareEvents`).
  `advanceTime()` resets the live clock at a new period and ignores late messages from an
  earlier period. Covered by 2 tests.

## 4. Live mode: no pause, seek, slow-down or end-of-stream 🟡 Partly

- **Done (milestone 3, task 10):** the stream ends with `{kind: 'end'}`; the viewer closes it and
  shows "Full time" (no reconnect loop). `until=mm:ss` stops the replay at a moment.
- **Still to do (milestone 4, task 7):** slow-down around cards, start time, speed control.

**Original problem:**

- **Problem:**
  - The mock replay has play/pause, a speed selector, `?t=mm:ss` and automatic slow-down
    around key moments, so cards stay readable. The SSE stream plays at one fixed speed
    from kickoff.
  - When the stream ends, the browser's EventSource reconnects and the replay starts again
    from kickoff. The viewer ignores the repeated events, but the header shows "Reconnecting…".
- **Fix (proposal):**
  - Backend replay accepts `start` (mm:ss) and slows down around shots and overlays (as the
    mock does).
  - It sends a final `{kind: 'end'}` message; the viewer closes the stream and shows
    "Full time".
  - The viewer passes its speed and start time to the stream URL.
- **When:** just before recording the demo video (Oct 23–25).

## 5. Favorites don't take priority for the overlay slot ✅ Fixed (milestone 3, task 10)

- **Now:** `pickCard()` shows, among cards within their display window, favorites first, then
  priority, then the newest; with no active card the most recent one stays up. 2 tests.

**Original problem and options:**

- **Problem:** `CLAUDE.md` says "favorite players get priority for overlay slots". The UI
  shows the newest card, and casual mode simply filters to favorites. Nothing actually
  competes for the slot by priority.
- **Decision needed:** where to rank.
  - (a) Backend: the Insight Selector already decides what to surface, so it ranks per viewer
    profile. This fits ADR-003's original intent.
  - (b) Client: keep cards visible for their `ttl_ms` and pick the highest-priority card,
    favorites first.
- **Recommendation:** (b) for the slot, because it's cheap and visible in the two-viewer demo,
  plus favorites as an input to the selector's `priority` in milestone 3.

## 6. Browser check against the backend ✅ Done (milestone 3, task 10)

- Three key moments rendered from backend data with `until=mm:ss`: the 40:14 card, the VAR
  correction at 65:24 (corrected card, banner, withdrawn card in the log), and the two-viewer
  page (`?view=two`). Screenshots in `docs/ui/live/`.

**Earlier notes:**

- Headless Chrome hangs on an open SSE stream, so automated screenshots are unreliable.
- A render with a fast, finishing stream worked for gap 2 (real squads, focus strip, score).
- **Still to do:** a full manual run once overlays stream (gap 1). Check the three key moments:
  a shot card, the two-viewer view and the VAR retraction.

## 7. Optional half-time or full-time recap card ⬜

- Allowed by `CLAUDE.md` only as a summary of baseline insights
  (e.g. "his three worst finishes tonight"), not as a generic recap.
- Needs a new overlay template (e.g. `recap_card`) and agent support. Milestone 3, only if time allows.

---

## How to run the viewer against the backend

```bash
cd backend && uv run formline-gen generate && uv run uvicorn formline.api:app
cd frontend && NEXT_PUBLIC_STREAM_URL="http://localhost:8000/matches/mtc_s26_md11_har_nor/stream?speed=20" pnpm dev
```

The API accepts requests from `http://localhost:3000` by default. Set `CORS_ORIGINS` to run
the viewer on another port.
