import type { MatchEvent, PlayerId } from "@/contract";

import type { Correction } from "./resolve";

export function formatClock(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** Parse "mm:ss" into match milliseconds; null if absent or malformed. */
export function parseClock(value: string | null): number | null {
  const match = value?.match(/^(\d{1,3}):([0-5]\d)$/);
  return match ? (Number(match[1]) * 60 + Number(match[2])) * 1000 : null;
}

const label = (s: string) => s.replaceAll("_", " ");

export function describeEvent(e: MatchEvent, nameOf: (id: PlayerId | null) => string): string {
  const who = nameOf(e.player_id);
  switch (e.type) {
    case "pass":
      return `Pass ${who} → ${nameOf(e.recipient_id)}${e.cross ? " (cross)" : ""}${e.through_ball ? " (through ball)" : ""}`;
    case "shot":
      return `Shot ${who} · ${label(e.body_part)} · ${label(e.outcome)} · ${e.tracking.shot_speed_kmh} km/h`;
    case "pressure":
      return `Pressure by ${who}`;
    case "duel":
      return `${e.duel_type === "aerial" ? "Aerial duel" : "Tackle"} ${who} · ${e.outcome}`;
    case "interception":
      return `Interception ${who}`;
    case "ball_recovery":
      return `Ball recovery ${who}`;
    case "foul_committed":
      return `Foul by ${who}`;
    case "card":
      return `${label(e.card)} card · ${who}`;
    case "substitution":
      return `Substitution: ${nameOf(e.player_on_id)} for ${nameOf(e.player_off_id)}`;
    case "var_review_start":
      return `VAR review started: ${e.review_subject}`;
    case "var_review_end":
      return `VAR review ended: ${label(e.outcome)}`;
    case "half_start":
      return "Half started";
    case "half_end":
      return "Half ended";
  }
}

export function describeCorrection(c: Correction, nameOf: (id: PlayerId | null) => string): string {
  if (!c.current) return `Correction: event ${c.event_id} withdrawn`;
  if (c.previous?.type === "shot" && c.current.type === "shot") {
    return `Correction: ${nameOf(c.current.player_id)} shot ${label(c.previous.outcome)} → ${label(c.current.outcome)}`;
  }
  return `Correction: ${c.current.type} by ${nameOf(c.current.player_id)} updated`;
}
