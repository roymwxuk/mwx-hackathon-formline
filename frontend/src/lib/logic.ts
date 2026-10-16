import type { MatchEvent, Overlay, Player, ViewerSettings } from '@/lib/types';

// ---------- Event store: idempotent, keeps the highest version per event_id ----------

export function applyEvents(events: MatchEvent[]): Map<string, MatchEvent> {
  const store = new Map<string, MatchEvent>();
  for (const e of events) {
    const prev = store.get(e.event_id);
    if (!prev || e.version > prev.version) store.set(e.event_id, e);
  }
  return store;
}

/** Events in event-time order (not arrival order). */
export function orderedEvents(store: Map<string, MatchEvent>): MatchEvent[] {
  return [...store.values()].sort((a, b) => a.match_clock_ms - b.match_clock_ms);
}

export function score(store: Map<string, MatchEvent>, clubIds: [string, string]): [number, number] {
  let a = 0;
  let b = 0;
  for (const e of store.values()) {
    if (e.type !== 'shot' || e.outcome !== 'goal') continue;
    if (e.team_id === clubIds[0]) a += 1;
    if (e.team_id === clubIds[1]) b += 1;
  }
  return [a, b];
}

// ---------- Overlays: apply show/retract, then personalize ----------

export interface OverlayState {
  overlay: Overlay;
  retracted: boolean;
}

/** Applies ops in arrival order. A retract marks its superseded overlay as withdrawn. */
export function applyOverlays(received: Overlay[]): OverlayState[] {
  const byId = new Map<string, OverlayState>();
  const order: string[] = [];
  for (const o of received) {
    if (o.op === 'retract') {
      const target = o.supersedes_overlay_id ? byId.get(o.supersedes_overlay_id) : undefined;
      if (target) target.retracted = true;
      continue;
    }
    if (byId.has(o.overlay_id)) continue; // duplicate delivery
    if (o.op === 'correct' && o.supersedes_overlay_id) {
      const target = byId.get(o.supersedes_overlay_id);
      if (target) target.retracted = true;
    }
    byId.set(o.overlay_id, { overlay: o, retracted: false });
    order.push(o.overlay_id);
  }
  return order.map((id) => byId.get(id)!);
}

/**
 * Personalization changes WHICH overlays appear, not only their wording:
 * - language and mode pick the variant;
 * - "my metric" keeps only that metric (corrections always pass);
 * - casual viewers with favorites see only their favorites (players or clubs);
 * - analysts see everything, with favorites ranked first.
 */
export function personalize(states: OverlayState[], s: ViewerSettings, players: Player[]): OverlayState[] {
  const clubOf = new Map(players.map((p) => [p.player_id, p.club_id]));
  const isFavorite = (o: Overlay) =>
    o.player_id !== null &&
    (s.favoritePlayers.includes(o.player_id) || s.favoriteClubs.includes(clubOf.get(o.player_id) ?? ''));
  const hasFavorites = s.favoritePlayers.length > 0 || s.favoriteClubs.length > 0;

  return states.filter(({ overlay: o }) => {
    if (o.lang !== s.lang || o.audience_mode !== s.mode) return false;
    if (o.template_id === 'correction_banner') return true;
    if (s.metric !== 'all' && o.metric !== s.metric) return false;
    if (s.mode === 'casual' && hasFavorites && !isFavorite(o)) return false;
    return true;
  });
}

export function isFavoriteOverlay(o: Overlay, s: ViewerSettings, players: Player[]): boolean {
  if (!o.player_id) return false;
  const club = players.find((p) => p.player_id === o.player_id)?.club_id ?? '';
  return s.favoritePlayers.includes(o.player_id) || s.favoriteClubs.includes(club);
}

// ---------- Player focus: tonight vs his own norm ----------

export interface FocusStats {
  shots: number;
  avgSpeed: number | null;
  norm: number;
  lastSpeed: number | null;
  goals: number;
}

export function focusStats(store: Map<string, MatchEvent>, player: Player): FocusStats {
  const shots = orderedEvents(store).filter((e) => e.type === 'shot' && e.player_id === player.player_id);
  const speeds = shots.map((e) => e.tracking?.shot_speed_kmh).filter((v): v is number => typeof v === 'number');
  return {
    shots: shots.length,
    avgSpeed: speeds.length ? speeds.reduce((a, b) => a + b, 0) / speeds.length : null,
    norm: player.season_shot_speed_norm_kmh,
    lastSpeed: speeds.length ? speeds[speeds.length - 1] : null,
    goals: shots.filter((e) => e.outcome === 'goal').length,
  };
}

export function formatClock(ms: number): string {
  const total = Math.floor(ms / 1000);
  const mm = Math.floor(total / 60);
  const ss = total % 60;
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
}
