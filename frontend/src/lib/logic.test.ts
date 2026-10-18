import { describe, expect, it } from 'vitest';
import { advanceTime, applyEvents, applyOverlays, orderedEvents, personalize, score, timeAfter } from '@/lib/logic';
import { buildDemoStream, PLAYERS } from '@/mock/demo-match';
import type { MatchEvent, Overlay, ViewerSettings } from '@/lib/types';

const all = buildDemoStream();
const events = all.flatMap((d) => (d.msg.kind === 'event' ? [d.msg.event] : []));
const overlays = all.flatMap((d) => (d.msg.kind === 'overlay' ? [d.msg.overlay] : []));

const base: ViewerSettings = { lang: 'en', mode: 'analyst', favoriteClubs: [], favoritePlayers: [], focusPlayer: null, metric: 'all' };

describe('event store', () => {
  it('ignores duplicate deliveries', () => {
    const dup = [...events, ...events];
    expect(applyEvents(dup).size).toBe(applyEvents(events).size);
  });

  it('keeps the highest version: the VAR update removes the goal', () => {
    const before = events.filter((e) => !(e.event_id === 'evt_001204' && e.version === 2));
    expect(score(applyEvents(before), ['clb_harbourside', 'clb_northgate'])).toEqual([2, 0]);
    expect(score(applyEvents(events), ['clb_harbourside', 'clb_northgate'])).toEqual([1, 0]);
  });

  it('a late lower version does not overwrite a newer one', () => {
    const v2 = events.find((e) => e.event_id === 'evt_001204' && e.version === 2)!;
    const v1: MatchEvent = { ...v2, version: 1, outcome: 'goal' };
    expect(applyEvents([v2, v1]).get('evt_001204')!.outcome).toBe('off_target');
  });
});

describe('overlays', () => {
  it('retract marks the superseded overlay as withdrawn', () => {
    const states = applyOverlays(overlays);
    const goal = states.find((s) => s.overlay.overlay_id === 'ovl_0004_en_casual')!;
    expect(goal.retracted).toBe(true);
  });

  it('duplicate overlay deliveries are shown once', () => {
    const states = applyOverlays([...overlays, ...overlays]);
    expect(states.length).toBe(applyOverlays(overlays).length);
  });

  it('casual viewer with favorites sees only favorites plus corrections', () => {
    const s: ViewerSettings = { ...base, mode: 'casual', favoritePlayers: ['ply_0107'] };
    const vis = personalize(applyOverlays(overlays), s, PLAYERS);
    const players = new Set(vis.map((v) => v.overlay.player_id));
    expect([...players].every((p) => p === 'ply_0107' || p === null)).toBe(true);
  });

  it('analyst sees every insight in the chosen language', () => {
    const vis = personalize(applyOverlays(overlays), base, PLAYERS);
    expect(vis.length).toBe(6);
    expect(vis.every((v: { overlay: Overlay }) => v.overlay.lang === 'en')).toBe(true);
  });

  it('"my metric" filters to that metric but keeps corrections', () => {
    const vis = personalize(applyOverlays(overlays), { ...base, metric: 'shot_speed' }, PLAYERS);
    expect(vis.every((v) => v.overlay.metric === 'shot_speed' || v.overlay.template_id === 'correction_banner')).toBe(true);
    expect(vis.some((v) => v.overlay.template_id === 'correction_banner')).toBe(true);
  });
  it('secondary cards appear only for viewers whose "my metric" matches', () => {
    const speed = overlays.find((o) => o.metric === 'shot_speed' && o.lang === 'en' && o.audience_mode === 'analyst')!;
    const runnerUp: Overlay = { ...speed, overlay_id: 'ovl_secondary', insight_id: 'ins_secondary', secondary: true };
    const states = applyOverlays([...overlays, runnerUp]);
    const ids = (s: ViewerSettings) => personalize(states, s, PLAYERS).map((v) => v.overlay.overlay_id);
    expect(ids(base)).not.toContain('ovl_secondary');
    expect(ids({ ...base, metric: 'finishing' })).not.toContain('ovl_secondary');
    expect(ids({ ...base, metric: 'shot_speed' })).toContain('ovl_secondary');
  });
});

describe('league URL', () => {
  it('derives the league endpoint from the stream URL', async () => {
    const { leagueUrlFromStream } = await import('./league');
    expect(leagueUrlFromStream('http://localhost:8000/matches/mtc_s26_md11_har_nor/stream?speed=20'))
      .toBe('http://localhost:8000/matches/mtc_s26_md11_har_nor/league');
  });
});

describe('half-time ordering', () => {
  const ev = (id: string, period: number, min: number, sec: number): MatchEvent => ({
    event_id: id, version: 1, type: 'pass', period, match_clock_ms: (min * 60 + sec) * 1000,
    team_id: null, player_id: null, x: null, y: null,
  });

  it('puts first-half stoppage time before the second half', () => {
    const store = applyEvents([ev('b', 2, 45, 10), ev('a', 1, 46, 30), ev('c', 2, 47, 0)]);
    expect(orderedEvents(store).map((e) => e.event_id)).toEqual(['a', 'b', 'c']);
  });

  it('resets the live clock when the second half starts', () => {
    let t = { period: 1, clockMs: 0 };
    t = advanceTime(t, 1, 2_790_000); // 46:30, first-half stoppage
    t = advanceTime(t, 2, 2_700_000); // second half kicks off at 45:00
    expect(t).toEqual({ period: 2, clockMs: 2_700_000 });
    t = advanceTime(t, 1, 2_795_000); // a late first-half message
    expect(t.clockMs).toBe(2_700_000);
    t = advanceTime(t, undefined, 2_710_000); // overlays carry no period
    expect(t).toEqual({ period: 2, clockMs: 2_710_000 });
  });
});

describe('card slot priority', () => {
  const card = (id: string, priority: number, at: number, player: string): Overlay => ({
    overlay_id: id, op: 'show', supersedes_overlay_id: null, match_clock_ms: at, ttl_ms: 12_000,
    template_id: 'shot_speed_card', priority, audience_mode: 'casual', lang: 'en',
    slots: { tag: 't', headline: id }, insight_id: `ins_${id}`, player_id: player,
    metric: 'shot_speed', source_event_ids: ['e'], verified: true,
  });
  const s: ViewerSettings = { ...base, mode: 'casual', favoritePlayers: ['ply_fav'] };
  const players = [
    { player_id: 'ply_fav', display_name: 'A', display_name_ja: 'A', club_id: 'c', shirt_number: 1, season_shot_speed_norm_kmh: 80 },
    { player_id: 'ply_other', display_name: 'B', display_name_ja: 'B', club_id: 'd', shirt_number: 2, season_shot_speed_norm_kmh: 80 },
  ];

  it('prefers a favorite, then priority, then the newest among active cards', async () => {
    const { pickCard } = await import('@/lib/logic');
    const states = applyOverlays([
      card('fav_low', 3, 1_000, 'ply_fav'),
      card('other_high', 1, 2_000, 'ply_other'),
    ]);
    expect(pickCard(states, s, players, 5_000)!.overlay.overlay_id).toBe('fav_low');
    expect(pickCard(states, { ...s, favoritePlayers: [] }, players, 5_000)!.overlay.overlay_id).toBe('other_high');
  });

  it('keeps the last card up when nothing is active', async () => {
    const { pickCard } = await import('@/lib/logic');
    const states = applyOverlays([card('a', 1, 1_000, 'ply_other'), card('b', 2, 20_000, 'ply_other')]);
    expect(pickCard(states, s, players, 60_000)!.overlay.overlay_id).toBe('b');
    expect(pickCard([], s, players, 0)).toBeUndefined();
  });
});

describe('live stream controls', () => {
  it('builds the stream URL for a speed and a resume point', async () => {
    const { liveStreamUrl, initialLiveSpeed } = await import('@/lib/useMatchStream');
    const base = 'http://localhost:8000/matches/m/stream?speed=20';
    expect(initialLiveSpeed(base)).toBe(20);
    expect(initialLiveSpeed('http://x/stream')).toBe(20);
    expect(liveStreamUrl(base, 60, null)).toBe('http://localhost:8000/matches/m/stream?speed=60');
    expect(liveStreamUrl(base, 20, { period: 1, clockMs: 40 * 60_000 + 12_000 })).toContain('start=40%3A12');
    // first-half stoppage time is capped at 45:00; the second half stays above it
    expect(liveStreamUrl(base, 20, { period: 1, clockMs: 46 * 60_000 })).toContain('start=45%3A00');
    expect(liveStreamUrl(base, 20, { period: 2, clockMs: 45 * 60_000 })).toContain('start=45%3A01');
  });
});

describe('clock messages', () => {
  it('move the match time during gaps, never backwards, and reset with a new period', () => {
    let t = { period: 1, clockMs: 190_000 };
    t = timeAfter(t, { kind: 'clock', period: 1, match_clock_ms: 195_000 });
    expect(t).toEqual({ period: 1, clockMs: 195_000 });
    t = timeAfter(t, { kind: 'clock', period: 1, match_clock_ms: 192_000 });
    expect(t.clockMs).toBe(195_000);
    t = timeAfter(t, { kind: 'clock', period: 2, match_clock_ms: 2_705_000 });
    expect(t).toEqual({ period: 2, clockMs: 2_705_000 });
    expect(timeAfter(t, { kind: 'end' })).toBe(t);
    const frame = { kind: 'frame' as const, p: 2, t: 2_710_000, b: [50, 50, 0] as [number, number, number], h: [], a: [] };
    expect(timeAfter(t, frame)).toEqual({ period: 2, clockMs: 2_710_000 });
  });
});

describe('key moments', () => {
  it('jump a few seconds before each moment, in the right half', async () => {
    const { MOMENTS, liveStreamUrl } = await import('@/lib/useMatchStream');
    const base = 'http://localhost:8000/matches/m/stream?speed=20';
    const starts = MOMENTS.map((m) => new URL(liveStreamUrl(base, 20, m.at)).searchParams.get('start'));
    expect(starts).toEqual(['12:00', '22:20', '40:05', '52:35', '63:30', '64:05']);
    expect(MOMENTS.filter((m) => m.at.period === 2).map((m) => m.label.slice(0, 5))).toEqual(['52:35', '63:30', '64:05']);
  });
});
