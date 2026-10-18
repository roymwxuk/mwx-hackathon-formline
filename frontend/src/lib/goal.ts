import type { MatchEvent } from '@/lib/types';

/** How recent (in match time) a goal must be to flash: goals replayed at once after a jump
 *  or a reconnect are older than this when they arrive, so they do not flash. */
export const GOAL_FLASH_RECENT_MS = 20_000;

/** The newest goal that has not flashed yet and just happened, if any. */
export function freshGoal(events: MatchEvent[], clockMs: number, flashed: Set<string>): MatchEvent | undefined {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type !== 'shot' || e.outcome !== 'goal') continue;
    if (flashed.has(e.event_id)) return undefined; // the newest goal already flashed
    return Math.abs(clockMs - e.match_clock_ms) <= GOAL_FLASH_RECENT_MS ? e : undefined;
  }
  return undefined;
}
