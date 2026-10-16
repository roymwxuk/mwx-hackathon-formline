/**
 * Feed envelope and match events (DATA_SCHEMA.md §1, §3–5).
 *
 * Coordinates: 0–100 on both axes, normalized so the acting team always attacks
 * toward x = 100. Renderers must flip the away team (x' = 100 - x, y' = 100 - y)
 * to draw both teams on one pitch. Meters: x_m = x * 1.05, y_m = y * 0.68.
 */

import type { ClubId, MatchId, PlayerId } from "./reference";

export type EventId = string;

export type PlayPattern =
  | "regular_play"
  | "from_counter"
  | "from_corner"
  | "from_free_kick"
  | "from_throw_in"
  | "from_goal_kick"
  | "from_kick_off";

interface EventBase<T extends string> {
  event_id: EventId;
  match_id: MatchId;
  type: T;
  period: 1 | 2;
  match_clock_ms: number;
  /** UTC time the action happened. Ordering uses this, never arrival time. */
  event_time: string;
  team_id: ClubId;
  /** Null only for match-level events such as half_start. */
  player_id: PlayerId | null;
  position: string | null;
  possession: number;
  possession_team_id: ClubId;
  play_pattern: PlayPattern;
  x: number;
  y: number;
  under_pressure: boolean;
  duration_ms: number | null;
  related_event_ids: EventId[];
}

export interface FreezeFramePlayer {
  x: number;
  y: number;
  teammate: boolean;
  goalkeeper: boolean;
}

export interface ShotEvent extends EventBase<"shot"> {
  body_part: "left_foot" | "right_foot" | "head" | "other";
  technique:
    | "normal"
    | "volley"
    | "half_volley"
    | "lob"
    | "backheel"
    | "diving_header"
    | "overhead_kick";
  shot_type: "open_play" | "free_kick" | "penalty" | "corner";
  first_time: boolean;
  deflected: boolean;
  end_x: number;
  end_y: number;
  /** Height in meters where the shot ended. */
  end_z: number;
  /** A goal is a shot with outcome "goal". */
  outcome: "goal" | "saved" | "off_target" | "post" | "blocked";
  key_pass_event_id: EventId | null;
  freeze_frame: FreezeFramePlayer[];
  tracking: { shot_speed_kmh: number };
}

export interface PassEvent extends EventBase<"pass"> {
  recipient_id: PlayerId | null;
  end_x: number;
  end_y: number;
  length_m: number;
  height: "ground" | "low" | "high";
  pass_type: "open_play" | "corner" | "free_kick" | "goal_kick" | "throw_in" | "kick_off";
  cross: boolean;
  through_ball: boolean;
  outcome: "complete" | "incomplete" | "out" | "offside";
  tracking?: { ball_speed_kmh: number };
}

export interface PressureEvent extends EventBase<"pressure"> {
  counterpress: boolean;
}

export interface DuelEvent extends EventBase<"duel"> {
  duel_type: "tackle" | "aerial";
  outcome: "won" | "lost";
}

export interface InterceptionEvent extends EventBase<"interception"> {
  outcome: "won" | "lost";
}

export interface BallRecoveryEvent extends EventBase<"ball_recovery"> {
  recovery_failure: boolean;
}

export interface FoulCommittedEvent extends EventBase<"foul_committed"> {
  card: "none" | "yellow" | "red";
  penalty: boolean;
}

export interface CardEvent extends EventBase<"card"> {
  card: "yellow" | "second_yellow" | "red";
}

export interface SubstitutionEvent extends EventBase<"substitution"> {
  player_off_id: PlayerId;
  player_on_id: PlayerId;
}

/** VAR arrives as a pair: review started, then concluded. */
export interface VarReviewStartEvent extends EventBase<"var_review_start"> {
  review_subject: "goal" | "penalty" | "red_card";
}

export interface VarReviewEndEvent extends EventBase<"var_review_end"> {
  outcome: "goal" | "no_goal" | "penalty" | "no_penalty" | "red_card" | "no_red_card";
}

export type HalfStartEvent = EventBase<"half_start">;
export type HalfEndEvent = EventBase<"half_end">;

export type MatchEvent =
  | ShotEvent
  | PassEvent
  | PressureEvent
  | DuelEvent
  | InterceptionEvent
  | BallRecoveryEvent
  | FoulCommittedEvent
  | CardEvent
  | SubstitutionEvent
  | VarReviewStartEvent
  | VarReviewEndEvent
  | HalfStartEvent
  | HalfEndEvent;

export type EventType = MatchEvent["type"];

interface EnvelopeBase {
  /** Unique per message; a duplicate delivery reuses it. */
  message_id: string;
  event_id: EventId;
  /** 1, 2, 3, … The highest version wins. */
  version: number;
  emitted_at: string;
  /** Provider ordering index; may have gaps or arrive out of order. */
  sequence: number;
}

/** `update` carries the full payload and replaces the previous version. */
export type FeedMessage =
  | (EnvelopeBase & { op: "create" | "update"; event: MatchEvent })
  | (EnvelopeBase & { op: "delete"; event: null });
