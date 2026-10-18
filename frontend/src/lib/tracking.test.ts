import { describe, expect, it } from 'vitest';
import { eventsReached, labelledPlayers, trackedMarkers } from '@/lib/tracking';
import type { Club, MatchEvent, Player, TrackingFrameMessage } from '@/lib/types';

const clubs: Club[] = [
  { club_id: 'h', name: 'Home', short_name: 'HOM', color: '#00f', text_color: '#fff' },
  { club_id: 'a', name: 'Away', short_name: 'AWY', color: '#fff', text_color: '#000' },
];
const player = (id: string, club: string, shirt: number): Player =>
  ({ player_id: id, club_id: club, shirt_number: shirt, display_name: id, display_name_ja: id } as Player);
const players = [player('h9', 'h', 9), player('a4', 'a', 4)];
const frame: TrackingFrameMessage = { kind: 'frame', p: 1, t: 1000, b: [50, 50, 0], h: [[9, 70, 40], [7, 60, 20]], a: [[4, 72, 42]] };

describe('trackedMarkers', () => {
  it('maps shirts to players per side without flipping', () => {
    const m = trackedMarkers(frame, clubs, players);
    expect(m.map((x) => x.key)).toEqual(['h9', 'h7', 'a4']);
    expect(m[0]).toMatchObject({ x: 70, y: 40, club: clubs[0], player: players[0] });
    expect(m[2]).toMatchObject({ x: 72, y: 42, club: clubs[1], player: players[1] });
    expect(m[1].player).toBeUndefined(); // unknown shirt: drawn, but no name
  });
});

describe('labelledPlayers', () => {
  const pass = { event_id: 'e', version: 1, type: 'pass', period: 1, match_clock_ms: 10_000, team_id: 'h',
    player_id: 'h9', recipient_id: 'h7', x: 50, y: 50 } as MatchEvent;
  it('names the passer, receiver and focus player shortly after a pass', () => {
    expect([...labelledPlayers([pass], 12_000, 'a4')].sort()).toEqual(['a4', 'h7', 'h9']);
  });
  it('always names the favorite players too', () => {
    expect([...labelledPlayers([pass], 30_000, 'h9', ['h9', 'h11'])].sort()).toEqual(['h11', 'h9']);
  });

  it('keeps only the focus player once the action is old', () => {
    expect([...labelledPlayers([pass], 30_000, 'a4')]).toEqual(['a4']);
    expect([...labelledPlayers([pass], 30_000, null)]).toEqual([]);
  });
});

describe('isNewerFrame', () => {
  it('accepts only frames later in match time', async () => {
    const { isNewerFrame } = await import('@/lib/useMatchStream');
    const f = (p: number, t: number): TrackingFrameMessage => ({ kind: 'frame', p, t, b: [50, 50, 0], h: [], a: [] });
    expect(isNewerFrame(null, f(1, 1000))).toBe(true);
    expect(isNewerFrame(f(1, 1000), f(1, 1250))).toBe(true);
    expect(isNewerFrame(f(1, 1250), f(1, 1000))).toBe(false); // a stale stream's frame
    expect(isNewerFrame(f(1, 1250), f(1, 1250))).toBe(false);
    expect(isNewerFrame(f(1, 2_800_000), f(2, 2_700_000))).toBe(true); // second half
  });
});

describe('eventsReached', () => {
  const ev = (id: string, period: number, clock: number, type: MatchEvent['type'] = 'pass', duration_ms?: number) =>
    ({ event_id: id, version: 1, type, period, match_clock_ms: clock, team_id: 'h', player_id: 'p', x: 1, y: 1, duration_ms } as MatchEvent);
  it('shows a pass line only once the ball has arrived', () => {
    const pass = ev('p', 1, 10_000, 'pass', 1_200);
    expect(eventsReached([pass], 1, 10_500)).toEqual([]); // ball still travelling
    expect(eventsReached([pass], 1, 11_200)).toEqual([pass]);
  });
  it('other events once they happened; earlier periods always', () => {
    const shot = ev('s', 1, 10_000, 'shot');
    expect(eventsReached([shot], 1, 9_999)).toEqual([]);
    expect(eventsReached([shot], 1, 10_000)).toEqual([shot]);
    expect(eventsReached([ev('old', 1, 2_790_000)], 2, 2_700_100).length).toBe(1);
  });
});
