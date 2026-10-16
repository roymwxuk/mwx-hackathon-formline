import { describe, expect, it } from 'vitest';
import { applyEvents, applyOverlays, personalize, score } from '@/lib/logic';
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
});

describe('league URL', () => {
  it('derives the league endpoint from the stream URL', async () => {
    const { leagueUrlFromStream } = await import('./league');
    expect(leagueUrlFromStream('http://localhost:8000/matches/mtc_s26_md11_har_nor/stream?speed=20'))
      .toBe('http://localhost:8000/matches/mtc_s26_md11_har_nor/league');
  });
});
