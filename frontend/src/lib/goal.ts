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

export type RestartType = 'throw_in' | 'corner' | 'goal_kick' | 'free_kick' | 'kick_off';
const RESTARTS = new Set<string>(['throw_in', 'corner', 'goal_kick', 'free_kick', 'kick_off']);

/** The newest set piece (the pass that restarts play) that just happened and has not been
 *  labelled yet. Only the latest on-ball pass counts, so a restart already followed by open
 *  play is not labelled late. */
export function freshRestart(events: MatchEvent[], clockMs: number, shown: Set<string>): MatchEvent | undefined {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type !== 'pass') continue;
    if (!e.pass_type || !RESTARTS.has(e.pass_type) || shown.has(e.event_id)) return undefined;
    return Math.abs(clockMs - e.match_clock_ms) <= GOAL_FLASH_RECENT_MS ? e : undefined;
  }
  return undefined;
}
