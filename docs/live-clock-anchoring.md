# Live clock: anchoring to kick-off time instead of the last event

**Status:** Implemented (2026-10-18), see "Result" below.
**Context:** at 1× the viewer's clock did not feel like real seconds. The tracking frames are
picked by the same clock, so player movement at 1× had the same slight unevenness.

## What was measured

One stream at 1× from 05:00 for 12 s (no code changed):

- the effective speed was exactly **1.0×** on average;
- but each displayed second stayed on screen for an uneven time: mostly 1.01 s, sometimes
  **0.76 s** or **1.26 s**.

So the speed is right; the rhythm is not.

## Why it happens

Every event carries two times:

- **when it happened** on the pitch: its match clock (and its wall-clock `event_time`);
- **when it was sent**: the feed delivers each event 0.25–0.9 s after it happens, as real
  providers do, and the delay varies per event.

Between events the stream sends a clock message every 0.25 s of real time (see the clock
messages in `backend/src/formline/replay.py`). Today it computes:

> clock = match time of the **last event** + real time elapsed **since that event was sent**

That treats each event as if it had been sent the instant it happened, so the clock runs
behind by **the last event's delay**, which changes with every event. A clock message also
never runs past the next event's time.

### Worked example at 1×

| Real moment | What happens | Clock shown | True match time |
|---|---|---|---|
| 5:10.300 | Pass A arrives (happened 5:10.000, **0.3 s late**) | 5:10.0 | 5:10.3 |
| 5:12.300 | clock message | 5:12.0 | 5:12.3 (0.3 s behind) |
| 5:13.000 | (pass B happens, not sent yet) | 5:12.7 | 5:13.0 |
| 5:13.700 | clock message | **capped at 5:13.0** | 5:13.7 |
| 5:13.900 | Pass B arrives (happened 5:13.000, **0.9 s late**) | 5:13.0 | 5:13.9 (0.9 s behind) |

Before B arrives the clock, counting from A, would pass B's time, so it **stops and waits**
about 0.7 s; after B it counts on from B, now 0.9 s behind instead of 0.3 s. The reverse also
happens: when the next event has a shorter delay, the clock jumps forward a little.

On average it is exactly 1×, but seconds are held longer or shorter. At 1× every second is
visible, so the rhythm feels wrong; at higher speeds the variation is too small to notice.

## Proposed fix

Every event also records the wall-clock time it happened (`event_time`). In football the
match clock never stops within a half (stoppage time keeps running), so for every event in
a half:

> kick-off time = event_time − match clock (the same value for every event in that half)

The clock is then:

> clock = current feed time − kick-off time

It no longer depends on any single event's delay: each second lasts exactly 1 s at 1×, the
clock never has to stop and wait (events always arrive after they happen, so it cannot overtake
them), and the tracking frames follow the same even clock.

## Is it more robust than the current method?

Yes in this setting, with one new dependency that is guarded.

| Situation | Current (from the last event) | Proposed (from kick-off time) |
|---|---|---|
| Normal play, delays vary 0.25–0.9 s | Clock stalls and catches up after events | Even ticking |
| **A late event** (the chaos mode delays some by 10 s or more, as real feeds do) | Anchors to the old event and freezes until the clock catches up; the viewer's no-backwards rule hides the jump but not the stall | **No effect:** every event, late or not, gives the same kick-off time |
| A duplicate or corrected event | Can re-anchor to an older time (same stall) | No effect |
| The feed goes quiet (stoppage, provider hiccup) | Clock keeps running | Clock keeps running |

The current method trusts whichever event came last, and late or corrected events are
exactly where that breaks. The proposed method uses one value per half, so individual
delays, late events and corrections cannot disturb it.

### Dependency and guards

1. **Events need a consistent `event_time`.** The generator guarantees it, and real providers
   send it, but one corrupted value could shift the clock. **Guard:** fix the kick-off time
   **once per half**, from the half's first event, and ignore later estimates.
2. **An event without `event_time`** (malformed message): fall back to the current method for
   that half.
3. **Safety net:** keep the rule that a clock message never runs past the next event's time.
   With consistent data it never triggers; with inconsistent data it prevents nonsense.

### One honest difference

The proposed clock shows the **true** match time, up to about 0.9 s ahead of the latest event
the viewer has received; that matches a real broadcast clock. The current clock runs behind by
that delay instead.

## Effort and tests

About 30 minutes, backend only (`backend/src/formline/replay.py`), local, ¥0. Tests: even
clock messages at 1× with varying delays; a late event (chaos) does not stall the clock; the
kick-off anchor is fixed per half; fallback without `event_time`; ids and resume unchanged.

## Result

- Clock messages count from each half's kick-off, fixed once per half; a half without
  `event_time` falls back to counting from the last event.
- The "never past the next event" cap became too strict for the true clock (which leads the
  next event by its send delay, so it kept stalling): with kick-off anchoring the cap is the
  next event plus 15 s (bad data only), and clock messages never go backwards.
- A second unevenness surfaced in the same measurement: each clock message picked the nearest
  stored tracking frame (every 100 ms), so at 1x frames stepped 0.2 s, 0.3 s, 0.2 s of match
  time. The backend now blends the two neighbouring frames to the exact time.
- Measured on the real stream at 1x: every displayed second lasts 1.01 s (was 0.76–1.26 s),
  and every frame steps exactly 0.25 s of match time (38 of 38).
- Tests: even ticks with varying send delays, a late event does not stall the clock, the
  kick-off is fixed per half, frame blending.

## Related: high speeds feel slower than selected (question 2)

Measured in the same run: 60× averaged about 41×, 120× about 56× (115× with the slow-down
off). The slow-down near key moments (120× drops to 20×) applies around every shot **and
every card**, so a large share of the match plays slowly. Ideas: slow down only around shots;
slow down less at high speeds (120× to 40×); show the actual speed or a "slow-mo" badge; or
leave it, since the Jump to menu now covers skipping ahead.
