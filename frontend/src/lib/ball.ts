import type { MatchEvent } from '@/lib/types';

/**
 * The ball's position reconstructed from event data (no tracking feed): it travels along
 * each pass and shot over the action's duration, goes to where duels, interceptions and
 * recoveries happen, and rests where play stopped until the next on-ball event. Only
 * events already received are used, so it never runs ahead of the live feed.
 *
 * Coordinates are percentages of one shared pitch (home attacks left to right; the away
 * team's own-frame coordinates are flipped).
 */

export interface BallPoint {
  x: number;
  y: number;
}

const ON_BALL = new Set<MatchEvent['type']>(['pass', 'shot', 'duel', 'interception', 'ball_recovery']);
const DEFAULT_PASS_MS = 1_000; // when a feed omits duration_ms
const DEFAULT_SHOT_MS = 600;
const CENTRE: BallPoint = { x: 50, y: 50 };

function shared(x: number, y: number, flip: boolean): BallPoint {
  return flip ? { x: 100 - x, y: 100 - y } : { x, y };
}

/** Ease out: the ball leaves fast and slows down, like a pass rolling on grass. */
function easeOut(t: number): number {
  return 1 - (1 - t) * (1 - t);
}

/**
 * Where the ball is at `clockMs` (match time in the current period), given the events
 * received so far in event-time order.
 */
export function ballAt(events: MatchEvent[], clockMs: number, awayTeamId: string): BallPoint {
  let last: MatchEvent | undefined;
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type === 'half_start') return CENTRE; // kick-off, until the first touch arrives
    if (ON_BALL.has(e.type) && e.x !== null && e.y !== null) {
      last = e;
      break;
    }
  }
  if (!last) return CENTRE;

  const flip = last.team_id === awayTeamId;
  const start = shared(last.x!, last.y!, flip);
  if (last.type !== 'pass' && last.type !== 'shot') return start; // duel, interception, recovery

  const end = shared(last.end_x ?? last.x!, last.end_y ?? last.y!, flip);
  const duration = last.duration_ms ?? (last.type === 'shot' ? DEFAULT_SHOT_MS : DEFAULT_PASS_MS);
  const t = duration > 0 ? (clockMs - last.match_clock_ms) / duration : 1;
  if (t <= 0) return start;
  if (t >= 1) return end; // arrived: rests there until the next on-ball event
  const k = last.type === 'shot' ? t : easeOut(t);
  return { x: start.x + (end.x - start.x) * k, y: start.y + (end.y - start.y) * k };
}
