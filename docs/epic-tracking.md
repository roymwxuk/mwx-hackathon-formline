# Epic: synthetic tracking data (all 22 players and the ball)

**Status:** In progress. T0 (ADR-010), T1 (schema) and T2 (team shape, preview in
`docs/tracking/t2-shape-preview.png`) done on 2026-10-17.
**Goal:** the 2D pitch shows all 22 players and the ball moving continuously, from
synthetic **optical-tracking-style data** consistent with the event feed, the way
professional providers deliver tracking alongside events.
**Estimate:** about 12–13 h in total; MVP cut line about 8 h (below).

## Why

- The viewer today shows only the event actors (passer, shot freeze frame) and a ball path
  reconstructed from events. A full pitch reads as live football and lifts UX (20%).
- It strengthens "data innovation": events + tracking is what professional feeds look like
  today, and the project plan allows only fields that event and optical tracking data capture.
- It unlocks the plan's optional extension with the same baseline engine: **sprint speed vs
  the player's own norm** (stretch task S1).

## Approach (decisions to confirm in ADR-010)

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Generate tracking inside the match simulator, or derive it afterwards from each match's events | **Afterwards, from the events** (a new `tracking` module) | The event generator, the seeded data, the baselines, the 88 Foundry overlays and all their tests stay unchanged; tracking can't break the core |
| D2 | Which matches | **The live demo match** (plus a short committed sample) | The viewer only plays the live match; 30 history matches of tracking add size, not value. Sprint baselines (S1) would need history too |
| D3 | Frame rate | **10 Hz** generated (providers deliver 25 Hz) | Smooth enough with client interpolation; about 54,000 frames per match |
| D4 | Storage | Compact JSONL per period: `{t, ball:[x,y,z], home:[[n,x,y]…], away:[…]}` with shirt numbers and 0.1 m precision, gzip on disk | About 5 MB compressed instead of ~25 MB raw JSON |
| D5 | How the viewer receives it | **Frame messages replace clock messages**: every 0.25 s real, the stream sends the frame at the current match time | One message type does both jobs; the client glides between frames as it does for the ball now |
| D6 | Consistency with events | Hard anchors: at each event, its actor (passer, receiver at pass end, presser, duel and recovery players) is exactly at the event position; at each shot, the freeze-frame positions are taken by the nearest real players | The pitch must never contradict a card or a freeze frame |

## Model (how positions are produced)

1. **Team shape:** each side keeps its 4-3-3 slots (`SQUAD_TEMPLATE`), shifted toward the ball
   and the possession phase: higher and wider in possession, compact (about 35–45 m deep)
   out of possession; the goalkeeper tracks the ball along his line.
2. **Anchors:** event actors are pulled to their event positions at event times; shot freeze
   frames are matched to the nearest outfield players and the goalkeeper.
3. **Motion:** between anchors, each player moves toward his target with speed and
   acceleration limits (sprint about 9–10 m/s, typical jog 2–4 m/s), smoothed so paths
   look human. Substitutions swap the player at his slot; kick-offs reset to formation.
4. **Ball:** follows the event path (passes and shots over their duration, carries between
   receiver and next action), with a small height `z` for lofted passes and shots.

## Tasks

| # | Task | Estimate | MVP | Done when |
|---|---|---|---|---|
| T0 | ADR-010: confirm D1–D6, model and scope | 0.5 h | ✅ | Decisions recorded |
| T1 | Tracking schema: Pydantic models, `DATA_SCHEMA.md` section, compact storage format, reader/writer | 0.5 h | ✅ | Round-trip test passes |
| T2 | Team shape model: formation slots, shift with ball and possession, compactness, goalkeeper | 2 h | ✅ | Unit tests: shapes stay on the pitch, lines ordered, compactness in range |
| T3 | Event anchors: passer, receiver, other actors; freeze-frame matching at shots | 2 h | ✅ (passes and shots) | Every anchor is met within 0.5 m at its event time |
| T4 | Motion: speed and acceleration limits, smoothing, substitutions, kick-offs, half-time | 1.5 h | ✅ (limits, kick-offs) | No player exceeds 10 m/s; property test over the whole match |
| T5 | Integration: `formline-gen tracking`, built into the Docker image like the season, committed sample excerpt | 0.5 h | ✅ | `docker compose up` serves tracking |
| T6 | Realism checks in the realism report: top speeds, distance covered (about 10–11 km per outfield player, about 5 km for goalkeepers), team length and width | 1 h | Partial | Checks within published ranges, failing test if not |
| T7 | Streaming: frame messages at a fixed real-time rate (a timer merged into `paced`), replacing clock messages; `start`, `until` and resume still work | 1.5 h | ✅ | Stream tests: frame rate, monotonic times, ids unchanged |
| T8 | Viewer: 22 players (club colour, shirt number), ball from frames, glide between frames, labels for actors and the focus player, shot view kept; fall back to the event-only pitch when there is no tracking | 1.5 h | ✅ | Frontend tests; browser check at 10×, 20× and around a shot |
| T9 | Performance and size: frame payload size, browser main thread at 20×, image size | 0.5 h | ✅ | No long tasks over 50 ms at 20×; image growth under 10 MB |
| T10 | Docs: README (data innovation, limitations), architecture diagram, realism report, screenshots | 0.5 h | ✅ | README claims match what is built |
| S1 | Stretch: sprint speed vs the player's own norm (tracking for history matches, baseline engine, a new card type, re-narration with Foundry) | 3–4 h | — | Only if everything else in milestone 5 is done |

**MVP (about 8 h):** T0, T1, T2, T3 for passes and shots, T4 with limits and kick-offs, T5, T7,
T8, T9, T10. T6 can start with speeds and distance only.

## Schedule (deadline treated as Oct 26 JST)

The epic is optional; the submission must-haves come first if time runs short.

| Date | Work | Must-have? |
|---|---|---|
| Oct 17 | Epic planned; confirm D2, D3 and D5 | — |
| Oct 18 | T0 ADR, T1 schema, T2 team shape | Epic |
| Oct 19 | T3 anchors, T4 motion, T5 integration | Epic |
| Oct 20 | T7 streaming, T8 viewer, T9 performance | Epic |
| **Oct 21** | **Checkpoint:** review the pitch at 10× and 20×. Convincing: T6 realism checks and T10 docs. Not convincing: shelve the epic and keep the event-based ball path | Decision |
| Oct 22 | Redeploy to Azure (each step approved), rehearse long streams, measure cold start | ✅ |
| Oct 23 | Video script and shot list (`docs/video-plan.md`) | ✅ |
| Oct 24 | Record, edit and publish the video; add its URL to the pitch and README | ✅ |
| Oct 25 | Final repository check (public, no secrets, no real names, clean clone runs, CI green) | ✅ |
| Oct 26 | Buffer; submit | ✅ |

Other open optional work (half-time shortening, observability, IaC, studio copilot) fits only
in the buffer. Stretch task S1 starts only if everything above is done early.

## Open decisions

| # | Question | Recommendation |
|---|---|---|
| D2 | Tracking for which matches | Live match only |
| D3 | Generated frame rate | 10 Hz |
| D5 | How frames reach the viewer | Frame messages replace clock messages, every 0.25 s real time |

## Risks and how they are contained

| Risk | Mitigation |
|---|---|
| Looks robotic or fake | Formation shifts plus smoothing plus small per-player noise; review at 10× before building the viewer polish; T6 numbers keep it honest |
| Contradicts events or freeze frames | Hard anchors (D6) with tests; events stay the source of truth |
| Time: the deadline is Oct 26 with the video and redeploy still to do | Built on its own branch; the MVP cut line; if it isn't convincing by about Oct 21, it is shelved and the ball path (already built) stays |
| Stream volume at high speed | Frames are sampled at 4 per second of real time regardless of playback speed; the client interpolates |
| Image and memory size | Live match only, gzip on disk, frames loaded per period |

## Out of scope

Tracking-based insights other than S1, player orientation and body pose, off-ball tactics
analysis, generating tracking for every history match (unless S1 is done), real tracking data.
