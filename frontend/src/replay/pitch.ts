/**
 * Pitch geometry and ball position for the 2D replay.
 *
 * Feed coordinates are 0–100 per team, attacking toward x = 100. The pitch view
 * shows the home team attacking left to right, so away-team coordinates are
 * flipped, then scaled to meters (105 × 68).
 */

import type { ClubId, MatchEvent, PlayerId } from "@/contract";

export const PITCH_LENGTH_M = 105;
export const PITCH_WIDTH_M = 68;

export interface PitchPoint {
  x: number;
  y: number;
}

export function toPitch(teamId: ClubId, homeClubId: ClubId, x: number, y: number): PitchPoint {
  const flip = teamId !== homeClubId;
  return {
    x: ((flip ? 100 - x : x) / 100) * PITCH_LENGTH_M,
    y: ((flip ? 100 - y : y) / 100) * PITCH_WIDTH_M,
  };
}

export interface BallState {
  position: PitchPoint;
  /** The player tagged next to the ball: receiver once a pass lands, else the last toucher. */
  playerId: PlayerId | null;
  teamId: ClubId;
  inFlight: boolean;
}

const ON_BALL_TYPES = new Set<MatchEvent["type"]>([
  "pass",
  "shot",
  "ball_recovery",
  "duel",
  "interception",
]);

const lerp = (a: PitchPoint, b: PitchPoint, t: number): PitchPoint => ({
  x: a.x + (b.x - a.x) * t,
  y: a.y + (b.y - a.y) * t,
});

/** Where the ball is at `clockMs`, interpolated along passes and shots. */
export function ballState(
  events: MatchEvent[],
  clockMs: number,
  homeClubId: ClubId,
): BallState | null {
  let last: MatchEvent | undefined;
  for (const e of events) {
    if (e.match_clock_ms > clockMs) break;
    if (ON_BALL_TYPES.has(e.type)) last = e;
  }
  if (!last) return null;

  const start = toPitch(last.team_id, homeClubId, last.x, last.y);
  const elapsed = clockMs - last.match_clock_ms;

  if (last.type === "pass" || last.type === "shot") {
    const end = toPitch(last.team_id, homeClubId, last.end_x, last.end_y);
    const progress = Math.min(1, elapsed / Math.max(1, last.duration_ms ?? 1));
    const landed = progress >= 1;
    const receiver = last.type === "pass" && last.outcome === "complete" ? last.recipient_id : null;
    return {
      position: lerp(start, end, progress),
      playerId: landed && receiver ? receiver : last.player_id,
      teamId: last.team_id,
      inFlight: !landed,
    };
  }

  return { position: start, playerId: last.player_id, teamId: last.team_id, inFlight: false };
}
