import { describe, expect, it } from 'vitest';
import { freshGoal } from '@/lib/goal';
import type { MatchEvent } from '@/lib/types';

const shot = (id: string, clock: number, outcome: string): MatchEvent =>
  ({ event_id: id, version: 1, type: 'shot', period: 2, match_clock_ms: clock, team_id: 'h', player_id: 'p', x: 90, y: 50, outcome } as MatchEvent);
const pass = (clock: number): MatchEvent =>
  ({ event_id: `p${clock}`, version: 1, type: 'pass', period: 2, match_clock_ms: clock, team_id: 'h', player_id: 'q', x: 50, y: 50 } as MatchEvent);

describe('freshGoal', () => {
  it('flashes a goal that just happened, once', () => {
    const events = [pass(3_800_000), shot('g', 3_822_000, 'goal'), pass(3_830_000)];
    expect(freshGoal(events, 3_823_000, new Set())?.event_id).toBe('g');
    expect(freshGoal(events, 3_823_000, new Set(['g']))).toBeUndefined();
  });

  it('does not flash old goals replayed at once (a jump or a reconnect)', () => {
    const events = [shot('ito', 1_350_000, 'goal'), pass(3_810_000)];
    expect(freshGoal(events, 3_810_000, new Set())).toBeUndefined();
  });

  it('ignores shots that were not goals, and a goal overturned later', () => {
    expect(freshGoal([shot('s', 1000, 'saved')], 1500, new Set())).toBeUndefined();
    expect(freshGoal([shot('g', 1000, 'off_target')], 1500, new Set())).toBeUndefined(); // VAR v2
  });
});
