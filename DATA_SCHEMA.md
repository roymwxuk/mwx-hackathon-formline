# Formline — Data Schema (draft v0.2, real-world audited)

Every **raw** field below exists in real professional football data today, either from **event data providers** (e.g. Hudl StatsBomb, Opta/Stats Perform) or from **optical tracking providers** (e.g. Second Spectrum/Genius Sports, TRACAB). Anything not delivered by providers is marked **Derived** (computed by our engine) or **Generator-only** (never part of the feed). Field names follow the *structure* of public provider documentation; no provider data is used.

---

## 0. Provenance legend

| Tag | Meaning |
|---|---|
| **RAW-EVENT** | Delivered by event data providers (manually or semi-automatically logged per on-ball action) |
| **RAW-TRACK** | Delivered by optical tracking providers (positions and speeds of players and ball) |
| **RAW-FEED** | Feed mechanics used by live data APIs (insert/update/delete messages, timestamps, sequence) |
| **DERIVED** | Computed by our engine from RAW fields (real analysts compute these the same way) |
| **GEN-ONLY** | Exists only inside the synthetic generator; never exposed to the engine |

---

## 1. Conventions

| Item | Convention |
|---|---|
| Pitch coordinates | 0–100 on both axes (Opta-style). `x` from own goal line to opponent goal line, attacking left → right; `y` across the pitch. Normalized per team per period. |
| Pitch size | 105 m × 68 m for converting to meters (x_m = x × 1.05, y_m = y × 0.68). |
| Shot end location | `end_x`, `end_y`, `end_z` in pitch coordinates and meters of height, as event providers deliver it. The goal-mouth point is **Derived** from these. |
| Units | km/h, meters, degrees, ms |
| Event time vs processing time | `event_time` / `match_clock_ms` = when it happened. `emitted_at` / `received_at` = when sent or received. Ordering and baselines use event time. |

---

## 2. Reference data

### 2.1 `club` (RAW-EVENT, match sheet data)
`club_id`, `name` (fictional), `short_name`, `colors`

### 2.2 `player` (RAW-EVENT, match sheet and squad data)
| Field | Notes |
|---|---|
| player_id, display_name (fictional), club_id, shirt_number | Standard squad data |
| position | Position at the time of the event; providers attach it per event |
| position_group | **Derived**: GK, DEF, MID or FWD, used as the shrinkage prior group |
| preferred_foot | Standard player bio data |

### 2.3 `player_latent_profile` (GEN-ONLY)
Hidden "true" tendencies used to generate events, such as shot power mean and sd, placement skill, shot volume, long-range tendency and pressure sensitivity. **Never visible to the engine.** Use it afterwards to measure how well estimated baselines recover the truth.

### 2.4 `match` (RAW-EVENT, match sheet data)
`match_id`, `season`, `matchday`, `kickoff_at`, `home_club_id`, `away_club_id`, `venue` (fictional), `is_live_demo` (internal flag)

---

## 3. Feed envelope (RAW-FEED)

Real live sports data APIs send each change as an insert/add, update or delete message with a stable event identifier. Updates carry the **full payload** and replace the previous version.

| Field | Notes |
|---|---|
| message_id | Unique per message; a duplicate delivery reuses it |
| op | `create`, `update`, `delete` |
| event_id | Stable across versions |
| version | 1, 2, 3, … |
| emitted_at | Provider send time (UTC) |
| sequence | Provider ordering index; may have gaps or arrive out of order |
| event | Full event payload (null for `delete`) |

Ingestion rules: idempotency on `(event_id, version)`; apply the highest version; reorder by event time within a watermark; treat later arrivals as corrections.

Realism note: providers also re-issue corrected event files after the match (e.g. "instant", then "temporary", then "final" event files), so corrections are a normal part of real data, not an artificial scenario.

---

## 4. Event (common fields)

| Field | Tag | Notes |
|---|---|---|
| event_id, match_id, type | RAW-EVENT | |
| period, match_clock_ms (minute, second, ms) | RAW-EVENT | |
| event_time (UTC recorded time) | RAW-EVENT | |
| team_id, player_id, position | RAW-EVENT | |
| possession (possession sequence number) | RAW-EVENT | Providers number possessions per match |
| possession_team_id | RAW-EVENT | |
| play_pattern | RAW-EVENT | `regular_play, from_counter, from_corner, from_free_kick, from_throw_in, from_goal_kick, from_kick_off` |
| location `x, y` | RAW-EVENT | |
| under_pressure | RAW-EVENT | Boolean |
| duration_ms | RAW-EVENT | For passes and shots |
| related_event_ids | RAW-EVENT | Links between events (e.g. the pass leading to a shot) |

**Event types (raw):** `pass, shot, pressure, duel, interception, ball_recovery, foul_committed, card, substitution, var_review_start, var_review_end, half_start, half_end`

> `possession_change` is **Derived**: it is detected when the possession number changes. It is not a raw event type.
> A goal is a `shot` with `outcome: goal`.
> Match-level events (`half_start`, `half_end`, `var_review_*`) have null `team_id`, `player_id` and location.
> `match_clock_ms` restarts at 45:00 in period 2, so first-half stoppage time and the start of the second half share clock values (as providers report "45+2"). Order by `event_time` or `(period, match_clock_ms)`.

---

## 5. Type-specific fields

### 5.1 `shot` (flagship)
| Field | Tag | Values |
|---|---|---|
| body_part | RAW-EVENT | `left_foot, right_foot, head, other` |
| technique | RAW-EVENT | `normal, volley, half_volley, lob, backheel, diving_header, overhead_kick` |
| shot_type | RAW-EVENT | `open_play, free_kick, penalty, corner` |
| first_time | RAW-EVENT | Boolean |
| deflected | RAW-EVENT | Boolean |
| end_x, end_y, end_z | RAW-EVENT | Where the shot ended; `end_z` is the height |
| outcome | RAW-EVENT | `goal, saved, off_target, post, blocked` |
| key_pass_event_id | RAW-EVENT | The assisting pass |
| freeze_frame[] | RAW-EVENT | Positions of players at the moment of the shot: `{x, y, teammate: bool, goalkeeper: bool}` |
| tracking.shot_speed_kmh | **RAW-TRACK** | Peak ball speed at the start of the shot |

### 5.2 `pass`
| Field | Tag | Values |
|---|---|---|
| recipient_id | RAW-EVENT | |
| end_x, end_y, length_m | RAW-EVENT | |
| height | RAW-EVENT | `ground, low, high` |
| pass_type | RAW-EVENT | `open_play, corner, free_kick, goal_kick, throw_in, kick_off` |
| cross, through_ball | RAW-EVENT | Booleans |
| outcome | RAW-EVENT | `complete, incomplete, out, offside` |
| tracking.ball_speed_kmh | **RAW-TRACK** | Optional |

### 5.3 Other events
| Type | Fields (all RAW-EVENT) |
|---|---|
| pressure | `duration_ms`, `counterpress` (bool) |
| duel | `duel_type: tackle / aerial`, `outcome: won / lost` |
| interception | `outcome: won / lost` |
| ball_recovery | `recovery_failure` (bool) |
| foul_committed | `card: none / yellow / red`, `penalty` (bool) |
| card | `card: yellow / second_yellow / red` |
| substitution | `player_off_id`, `player_on_id` |
| var_review_start | `review_subject: goal / penalty / red_card`, `related_event_ids` |
| var_review_end | `outcome: goal / no_goal / penalty / no_penalty / red_card / no_red_card`, `related_event_ids` |
| half_start / half_end | none |

> VAR in real feeds is a **pair of events**: review started, then review concluded with an outcome. If the goal is cancelled, the target shot then receives an `update` (outcome changed) through the envelope.

### 5.4 Tracking frame (RAW-TRACK, synthetic)

Every player on the pitch and the ball, 10 frames per second (tracking providers deliver about 25). In Formline, frames are **derived from the event feed** by a team shape model with hard event anchors and motion limits (ADR-010), for the live demo match only.

| Field | Meaning |
|---|---|
| `period`, `match_clock_ms` | Match time of the frame (every 100 ms) |
| `ball` | `x`, `y` on the pitch, `z` height in meters |
| `home[]`, `away[]` | `{shirt, x, y}` for each player on the pitch |

Unlike events, tracking uses **one shared frame**: 0–100 on both axes, the home team attacking toward x = 100 in both periods. Stored as gzipped JSONL (`data/tracking/<match_id>.jsonl.gz`), one compact row per frame: `{"p": 1, "t": 12300, "b": [x, y, z], "h": [[shirt, x, y], ...], "a": [...]}`.

### 5.5 Analyst comment (DERIVED, LLM-written and verified)

`comment_id`, `op (show / retract)`, `supersedes_comment_id`, `question (shot_outcome /
corner / card / var)`, `period`, `match_clock_ms`, `lang (en / ja)`, `headline`, `body`,
`player_id`, `evidence[] {event_id, minute, type}`, `verified`, `source (llm / template)`.
Streamed as `{"kind": "comment", "comment": {...}}` with an SSE id. A retract withdraws a
comment whose event was revised (the VAR overturn).

Follow-up questions (phase 2): `ask {moment, seq}` names the comment's moment
(`<question>_<event_id>`) and the feed sequence it was written at; `suggestions[] {question
(situation / score / player_tonight / team_stats), label, player_id}` are the 2–3 questions
the Suggester agent picked from the fixed catalog, with the catalog's wording in the
comment's language. The viewer posts `{moment, seq, question, player_id, lang}` to
`POST /matches/{match_id}/ask` and receives `{question, lang, headline, body, evidence[],
verified, source, cached}` (`cached`: precomputed with the match). Unknown moments, questions
that do not apply to the moment, or a `player_id` other than the moment's player get a 422.

---

## 6. Derived data (engine output)

### 6.1 Shot geometry and context (DERIVED from RAW)
| Field | Computed from |
|---|---|
| distance_m, angle_deg, zone | Shot location |
| goal_y_m, goal_z_m (goal-mouth point) | end_x, end_y, end_z |
| gk_x, gk_y | freeze_frame (goalkeeper = true) |
| nearest_defender_m, defenders_in_cone | freeze_frame (teammate = false) |
| xg | Location, angle, body part, pressure, freeze frame |
| psxg (post-shot xG, also called xGOT) | xg plus end location and shot speed; null if not on target |

### 6.2 `possession_change` (DERIVED)
Emitted when the possession number changes. `from_team_id`, `to_team_id`, `ending_event_id`.

### 6.3 `baseline`
`player_id`, `metric` (`shot_speed_kmh`, `psxg_minus_xg`, placement metrics), `bucket` (zone × body_part × pressure, with fallbacks), `n`, `raw_mean`, `raw_sd`, `prior_mean`, `prior_sd`, `shrinkage_weight`, `shrunk_mean`, `through_event_time`, `contributing_event_ids`

### 6.4 `insight`
`insight_id`, `type`, `player_id`, `values{}`, `confidence`, `salience`, `source_event_ids[]`, `status (active / retracted / corrected)`

### 6.5 `overlay` (output contract)
`overlay_id`, `op (show / correct / retract)`, `supersedes_overlay_id`, `match_clock_ms`, `ttl_ms`, `template_id`, `priority`, `audience_mode (casual / analyst)`, `lang (en / ja)`, `slots{}`, `insight_id`, `player_id`, `metric (shot_speed / finishing / null)`, `source_event_ids[]`, `verified`, `secondary` (default false)

`secondary: true` marks a runner-up insight of the *other* metric for a shot that already has a
shown card. Viewers see it only when their "my metric" equals its `metric`, so that setting
changes which insight appears (e.g. a shot-speed viewer gets the speed card where everyone
else gets the placement card). Secondaries are corrected and retracted like any card.

---

## 7. Examples

### 7.1 Shot (create)
```json
{
  "message_id": "msg_10231",
  "op": "create",
  "event_id": "evt_000873",
  "version": 1,
  "emitted_at": "2026-12-05T15:40:12.900Z",
  "sequence": 10231,
  "event": {
    "event_id": "evt_000873",
    "match_id": "mtc_s26_md14_har_nor",
    "type": "shot",
    "period": 1,
    "match_clock_ms": 2412300,
    "event_time": "2026-12-05T15:40:12.300Z",
    "team_id": "clb_harbourside",
    "player_id": "ply_0107",
    "position": "ST",
    "possession": 58,
    "possession_team_id": "clb_harbourside",
    "play_pattern": "regular_play",
    "x": 84.2, "y": 41.0,
    "under_pressure": true,
    "duration_ms": 420,
    "related_event_ids": ["evt_000871"],
    "body_part": "right_foot",
    "technique": "normal",
    "shot_type": "open_play",
    "first_time": false,
    "deflected": false,
    "end_x": 100.0, "end_y": 47.2, "end_z": 0.6,
    "outcome": "saved",
    "key_pass_event_id": "evt_000871",
    "freeze_frame": [
      { "x": 98.1, "y": 49.0, "teammate": false, "goalkeeper": true },
      { "x": 86.0, "y": 43.5, "teammate": false, "goalkeeper": false },
      { "x": 90.2, "y": 46.8, "teammate": false, "goalkeeper": false },
      { "x": 88.7, "y": 55.1, "teammate": true,  "goalkeeper": false }
    ],
    "tracking": { "shot_speed_kmh": 84.1 }
  }
}
```

### 7.2 VAR cancels a goal
1. `evt_001204`: a shot with `outcome: goal` (create, v1). The engine updates the baseline and shows overlay `ovl_0133`.
2. `evt_001217`: `var_review_start`, `review_subject: goal`, `related_event_ids: ["evt_001204"]`.
3. `evt_001219`: `var_review_end`, `outcome: no_goal`, `related_event_ids: ["evt_001204"]`.
4. `evt_001204` arrives again as an **update** (v2) with `outcome: off_target` (or the outcome the provider assigns).
5. The engine retracts `ovl_0133` (lineage lookup on `source_event_ids`), emits a `correction_banner`, and re-folds the baseline.

### 7.3 Overlay (show)
```json
{
  "overlay_id": "ovl_0091",
  "op": "show",
  "supersedes_overlay_id": null,
  "match_clock_ms": 2414000,
  "ttl_ms": 8000,
  "template_id": "shot_speed_card",
  "priority": 2,
  "audience_mode": "casual",
  "lang": "en",
  "slots": {
    "headline": "Reyner — not his usual strike",
    "stat": "84 km/h",
    "sub": "About 15 km/h below his typical shot from this range (estimate)"
  },
  "insight_id": "ins_0042",
  "source_event_ids": ["evt_000873"],
  "verified": true
}
```

---

## 8. Generator realism targets

**Status: calibrated (2026-10-17).** The generator is tuned against public season aggregates; the generated values, target ranges and sources are in [`docs/realism-report.md`](docs/realism-report.md). The table below is the original draft.

| Metric | Assumed target |
|---|---|
| Passes per match | 900–1,100 |
| Pass completion | 78–86% |
| Shots per match | 20–30 |
| Goals per match | mean about 2.7 |
| Shot speed | Most foot shots well under 100 km/h; above 100 km/h is notable (broadcasters highlight these); headers much slower |
| Chaos injector (demo only) | Duplicates 2–5%, reordering within a few seconds, 1–2 updates, 1 VAR cancellation |

---

## 9. Deliberately excluded (not in real broadcast-level data, or out of scope)

| Excluded | Reason |
|---|---|
| Ball spin / rotation rate | Not a standard football data point (unlike baseball pitch tracking) |
| Full 25 Hz tracking of all players | Real but heavy; we use only the shot freeze frame and speed values |
| Player intentions or "what they should have done" | Not observable data |
| Explicit possession_change raw events | Providers number possessions instead; we derive changes |
