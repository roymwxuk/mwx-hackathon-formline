import { describe, expect, it } from 'vitest';
import { ballAt } from '@/lib/ball';
import type { MatchEvent } from '@/lib/types';

const HOME = 'clb_home';
const AWAY = 'clb_away';

function ev(over: Partial<MatchEvent>): MatchEvent {
  return {
    event_id: over.event_id ?? 'e', version: 1, type: 'pass', period: 1, match_clock_ms: 0,
    team_id: HOME, player_id: 'p', x: 20, y: 50, ...over,
  };
}

describe('ballAt', () => {
  it('starts at the centre spot', () => {
    expect(ballAt([], 0, AWAY)).toEqual({ x: 50, y: 50 });
    expect(ballAt([ev({ type: 'half_start', x: null, y: null })], 1000, AWAY)).toEqual({ x: 50, y: 50 });
  });

  it('travels along a pass over its duration, then rests at the receiver', () => {
    const pass = ev({ match_clock_ms: 10_000, x: 20, y: 50, end_x: 60, end_y: 50, duration_ms: 1_000 });
    expect(ballAt([pass], 10_000, AWAY)).toEqual({ x: 20, y: 50 });
    const mid = ballAt([pass], 10_500, AWAY);
    expect(mid.x).toBeGreaterThan(40); // eased: more than half way at half time
    expect(mid.x).toBeLessThan(60);
    expect(ballAt([pass], 11_000, AWAY)).toEqual({ x: 60, y: 50 });
    expect(ballAt([pass], 40_000, AWAY)).toEqual({ x: 60, y: 50 }); // dead ball: it stays
  });

  it('flips the away team into the shared frame', () => {
    const pass = ev({ team_id: AWAY, x: 20, y: 30, end_x: 60, end_y: 40, duration_ms: 1_000 });
    expect(ballAt([pass], 5_000, AWAY)).toEqual({ x: 40, y: 60 });
  });

  it('goes to duels, interceptions and recoveries, but not to pressure', () => {
    const pass = ev({ event_id: 'a', x: 20, y: 50, end_x: 60, end_y: 50, duration_ms: 1_000 });
    const interception = ev({ event_id: 'b', type: 'interception', team_id: AWAY, match_clock_ms: 3_000, x: 30, y: 40 });
    expect(ballAt([pass, interception], 3_500, AWAY)).toEqual({ x: 70, y: 60 });
    const pressure = ev({ event_id: 'c', type: 'pressure', match_clock_ms: 4_000, x: 10, y: 10 });
    expect(ballAt([pass, interception, pressure], 4_500, AWAY)).toEqual({ x: 70, y: 60 });
  });

  it('flies to the goal-mouth end of a shot', () => {
    const shot = ev({ type: 'shot', x: 85, y: 45, end_x: 100, end_y: 48, duration_ms: 600 });
    expect(ballAt([shot], 300, AWAY).x).toBeCloseTo(92.5);
    expect(ballAt([shot], 2_000, AWAY)).toEqual({ x: 100, y: 48 });
  });

  it('uses a default duration when the feed has none', () => {
    const pass = ev({ x: 0, y: 50, end_x: 100, end_y: 50 });
    expect(ballAt([pass], 999, AWAY).x).toBeLessThan(100);
    expect(ballAt([pass], 1_000, AWAY).x).toBe(100);
  });
});
