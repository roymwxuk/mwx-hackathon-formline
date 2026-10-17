import { describe, expect, it } from 'vitest';
import examples from '../../../backend/data/sample/overlays.example.json';
import { applyOverlays, personalize } from '@/lib/logic';
import type { Overlay, ViewerSettings } from '@/lib/types';

// The backend writes these with `uv run formline-gen contracts`. If the backend's
// overlay shape drifts from types.ts, typecheck or these tests fail.
const overlays: Overlay[] = examples as Overlay[];

const analystEn: ViewerSettings = {
  lang: 'en', mode: 'analyst', favoriteClubs: [], favoritePlayers: [], focusPlayer: null, metric: 'all',
};

describe('backend overlay contract', () => {
  it('has every field the viewer reads', () => {
    for (const o of overlays) {
      expect(o.overlay_id).toBeTruthy();
      expect(['show', 'correct', 'retract']).toContain(o.op);
      expect(o).toHaveProperty('supersedes_overlay_id');
      expect(o).toHaveProperty('player_id');
      expect(o).toHaveProperty('metric');
      expect(o.source_event_ids.length).toBeGreaterThan(0);
      expect(typeof o.slots.headline).toBe('string');
    }
  });

  it('a backend retract withdraws the overlay it supersedes', () => {
    const states = applyOverlays(overlays);
    const retract = overlays.find((o) => o.op === 'retract')!;
    const target = states.find((s) => s.overlay.overlay_id === retract.supersedes_overlay_id)!;
    expect(target.retracted).toBe(true);
  });

  it('casual cards carry bars and analyst cards carry rows', () => {
    for (const o of overlays.filter((x) => x.op !== 'retract' && x.template_id !== 'correction_banner')) {
      if (o.audience_mode === 'casual') expect(o.slots.bars?.length).toBe(2);
      else expect(o.slots.rows?.length).toBe(5);
    }
  });

  it('personalization picks the matching language and mode', () => {
    const visible = personalize(applyOverlays(overlays), analystEn, []);
    expect(visible.length).toBeGreaterThan(0);
    expect(visible.every((v) => v.overlay.lang === 'en' && v.overlay.audience_mode === 'analyst')).toBe(true);
  });
});
