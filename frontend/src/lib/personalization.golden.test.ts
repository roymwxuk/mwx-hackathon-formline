import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import league from '../../../backend/data/sample/league.json';
import { applyOverlays, personalize, pickCard } from '@/lib/logic';
import type { Overlay, Player, ViewerSettings } from '@/lib/types';

/**
 * Golden tests: the exact card each viewer sees at key moments of the real demo match
 * (the 88 Foundry-narrated overlays the app ships), through the whole chain the viewer runs:
 * applyOverlays (corrections, retractions) → personalize → pickCard. Plan and context:
 * docs/plan-personalization-golden-tests.md. If the demo overlays are regenerated, re-read
 * the expected values once and check them by eye.
 */

const rows = readFileSync(new URL('../../../backend/demo/overlays/mtc_s26_md11_har_nor.jsonl', import.meta.url), 'utf8')
  .trim().split('\n').map((l) => JSON.parse(l) as { emitted_at: string; overlay: Overlay });
const players = league.players as unknown as Player[];

const REYNER = 'ply_0107';
const BRANDT = 'ply_0208';
const base: ViewerSettings = { lang: 'en', mode: 'casual', favoriteClubs: [], favoritePlayers: [], focusPlayer: null, metric: 'all' };

const PROFILES: Record<string, ViewerSettings> = {
  'analyst, no favorites': { ...base, mode: 'analyst' },
  'casual, favorite Reyner': { ...base, favoritePlayers: [REYNER] },
  'casual, favorite Brandt': { ...base, favoritePlayers: [BRANDT] },
  'casual, favorites Reyner and Brandt': { ...base, favoritePlayers: [REYNER, BRANDT] },
  'casual, favorite club Harbourside': { ...base, favoriteClubs: ['clb_harbourside'] },
  'casual JA, favorite Reyner': { ...base, lang: 'ja', favoritePlayers: [REYNER] },
  'casual, Reyner, my metric shot speed': { ...base, favoritePlayers: [REYNER], metric: 'shot_speed' },
  'casual, Reyner, my metric finishing': { ...base, favoritePlayers: [REYNER], metric: 'finishing' },
  'casual, no favorites, focus Reyner': { ...base, focusPlayer: REYNER },
};

// match clock (ms) of each moment
const MOMENTS = { '12:10': 730_000, '40:16': 2_416_000, '44:50': 2_690_000, '63:46': 3_826_000, '65:30': 3_930_000 };
type Moment = keyof typeof MOMENTS;

/** Expected card: overlay id without the 'ovl_evt_' prefix, or null for no card; '!' marks a
 *  withdrawn (struck-through) card. The correction banner is checked separately. */
const EXPECTED: Record<string, Record<Moment, string | null>> = {
  'analyst, no favorites': {
    '12:10': '3100199_shot_speed_vs_norm_en_analyst',
    '40:16': '3100558_placement_vs_norm_en_analyst',
    '44:50': '3100617_season_best_en_analyst',
    '63:46': '3100937_season_best_en_analyst',
    '65:30': '3100937_season_best_en_analyst_v2',
  },
  'casual, favorite Reyner': {
    '12:10': '3100199_shot_speed_vs_norm_en_casual',
    '40:16': '3100558_placement_vs_norm_en_casual',
    '44:50': '3100558_placement_vs_norm_en_casual', // Brandt's card is filtered out; the last Reyner card stays
    '63:46': '3100937_season_best_en_casual',
    '65:30': '3100937_season_best_en_casual_v2',
  },
  'casual, favorite Brandt': {
    '12:10': null,
    '40:16': '3100273_season_worst_en_casual', // no card active: his most recent one stays up
    '44:50': '3100617_season_best_en_casual',
    '63:46': '3100895_season_worst_en_casual',
    '65:30': '3100895_season_worst_en_casual',
  },
  'casual, favorites Reyner and Brandt': {
    '12:10': '3100199_shot_speed_vs_norm_en_casual',
    '40:16': '3100558_placement_vs_norm_en_casual',
    '44:50': '3100617_season_best_en_casual',
    '63:46': '3100937_season_best_en_casual',
    '65:30': '3100937_season_best_en_casual_v2',
  },
  'casual, favorite club Harbourside': {
    '12:10': '3100199_shot_speed_vs_norm_en_casual',
    '40:16': '3100558_placement_vs_norm_en_casual',
    '44:50': '3100558_placement_vs_norm_en_casual', // Brandt plays for Northgate
    '63:46': '3100937_season_best_en_casual',
    '65:30': '3100937_season_best_en_casual_v2',
  },
  'casual JA, favorite Reyner': {
    '12:10': '3100199_shot_speed_vs_norm_ja_casual',
    '40:16': '3100558_placement_vs_norm_ja_casual',
    '44:50': '3100558_placement_vs_norm_ja_casual',
    '63:46': '3100937_season_best_ja_casual',
    '65:30': '3100937_season_best_ja_casual_v2',
  },
  'casual, Reyner, my metric shot speed': {
    '12:10': '3100199_shot_speed_vs_norm_en_casual',
    '40:16': '3100558_shot_speed_vs_norm_en_casual', // the secondary card only these viewers get
    '44:50': '3100558_shot_speed_vs_norm_en_casual',
    '63:46': '3100937_season_best_en_casual',
    '65:30': '3100937_season_best_en_casual_v2',
  },
  'casual, Reyner, my metric finishing': {
    '12:10': null,
    '40:16': '3100558_placement_vs_norm_en_casual',
    '44:50': '3100558_placement_vs_norm_en_casual',
    '63:46': '3100937_placement_vs_norm_en_casual', // secondary placement card for the goal
    '65:30': '!3100937_placement_vs_norm_en_casual', // withdrawn after VAR
  },
  'casual, no favorites, focus Reyner': { // focus drives the strip, not the card slot
    '12:10': '3100199_shot_speed_vs_norm_en_casual',
    '40:16': '3100558_placement_vs_norm_en_casual',
    '44:50': '3100617_season_best_en_casual',
    '63:46': '3100937_season_best_en_casual',
    '65:30': '3100937_season_best_en_casual_v2',
  },
};

/** What a viewer with these settings shows at match time `t`. */
function screen(s: ViewerSettings, t: number) {
  const received = rows.map((r) => r.overlay).filter((o) => o.match_clock_ms <= t);
  const visible = personalize(applyOverlays(received), s, players);
  const card = pickCard(visible.filter((v) => v.overlay.template_id !== 'correction_banner'), s, players, t);
  const banner = visible.some((v) => v.overlay.template_id === 'correction_banner');
  const id = card ? `${card.retracted ? '!' : ''}${card.overlay.overlay_id.replace('ovl_evt_', '')}` : null;
  return { id, card, banner };
}

describe('golden: the card each viewer sees on the real demo match', () => {
  it('uses the shipped demo overlays', () => {
    expect(rows.length).toBe(88);
  });

  for (const [profile, settings] of Object.entries(PROFILES)) {
    it(profile, () => {
      for (const [moment, t] of Object.entries(MOMENTS) as [Moment, number][]) {
        expect(screen(settings, t).id, `${profile} at ${moment}`).toBe(EXPECTED[profile][moment]);
      }
    });
  }

  it('same moment, different insights: viewers disagree where settings say they should', () => {
    const at = (p: string, m: Moment) => EXPECTED[p][m];
    expect(at('casual, Reyner, my metric shot speed', '40:16')).not.toBe(at('casual, favorite Reyner', '40:16'));
    expect(at('casual, Reyner, my metric finishing', '63:46')).not.toBe(at('casual, favorite Reyner', '63:46'));
    expect(at('casual, favorite Reyner', '44:50')).not.toBe(at('analyst, no favorites', '44:50'));
  });

  it('every card shown is in the viewer language and mode, and verified', () => {
    for (const settings of Object.values(PROFILES)) {
      for (const t of Object.values(MOMENTS)) {
        const { card } = screen(settings, t);
        if (!card) continue;
        expect(card.overlay.lang).toBe(settings.lang);
        expect(card.overlay.audience_mode).toBe(settings.mode);
        expect(card.overlay.verified).toBe(true);
      }
    }
  });

  it('the correction banner appears for everyone after the VAR overturn, and not before', () => {
    for (const settings of Object.values(PROFILES)) {
      expect(screen(settings, MOMENTS['63:46']).banner).toBe(false);
      expect(screen(settings, MOMENTS['65:30']).banner).toBe(true);
    }
  });
});
