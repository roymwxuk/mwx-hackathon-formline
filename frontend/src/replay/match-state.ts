import type { ClubId, MatchEvent, ShotEvent } from "@/contract";

import type { Correction } from "./resolve";

export function score(events: MatchEvent[], clubIds: ClubId[]): Record<ClubId, number> {
  const result = Object.fromEntries(clubIds.map((id) => [id, 0]));
  for (const e of events) if (e.type === "shot" && e.outcome === "goal") result[e.team_id] += 1;
  return result;
}

/** True while a VAR review has started and not yet concluded. */
export function varReviewInProgress(events: MatchEvent[]): boolean {
  const open = new Set<string>();
  for (const e of events) {
    const key = e.related_event_ids.join(",");
    if (e.type === "var_review_start") open.add(key);
    if (e.type === "var_review_end") open.delete(key);
  }
  return open.size > 0;
}

/** Shots whose goal was later overturned by a correction. */
export function overturnedGoalIds(corrections: Correction[]): Set<string> {
  const ids = new Set<string>();
  for (const c of corrections) {
    const wasGoal = c.previous?.type === "shot" && c.previous.outcome === "goal";
    const isGoal = c.current?.type === "shot" && (c.current as ShotEvent).outcome === "goal";
    if (wasGoal && !isGoal) ids.add(c.event_id);
  }
  return ids;
}
