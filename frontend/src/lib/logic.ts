import type { AnalystComment, MatchEvent, Overlay, Player, StreamMessage, ViewerSettings } from '@/lib/types';

// ---------- Event store: idempotent, keeps the highest version per event_id ----------

export function applyEvents(events: MatchEvent[]): Map<string, MatchEvent> {
  const store = new Map<string, MatchEvent>();
  for (const e of events) {
    const prev = store.get(e.event_id);
    if (!prev || e.version > prev.version) store.set(e.event_id, e);
  }
  return store;
}

/**
 * Events in event-time order (not arrival order). The match clock restarts at 45:00
 * in the second half, so first-half stoppage time (e.g. 46:30) must sort before
 * second-half 45:10: order by period first, then clock.
 */
export function compareEvents(a: MatchEvent, b: MatchEvent): number {
  return (a.period ?? 1) - (b.period ?? 1)
    || a.match_clock_ms - b.match_clock_ms
    || a.event_id.localeCompare(b.event_id);
}

export function orderedEvents(store: Map<string, MatchEvent>): MatchEvent[] {
  return [...store.values()].sort(compareEvents);
}

// ---------- Match time on a live feed ----------

export interface MatchTime {
  period: number;
  clockMs: number;
}

/**
 * Advance the displayed match time with an incoming message. A new period resets the
 * clock (second half starts at 45:00 even after 46:30 of stoppage time); a late
 * message from an earlier period never moves it back.
 */
export function advanceTime(t: MatchTime, period: number | undefined, clockMs: number): MatchTime {
  const p = period ?? t.period;
  if (p > t.period) return { period: p, clockMs };
  if (p < t.period) return t;
  return { period: p, clockMs: Math.max(t.clockMs, clockMs) };
}

/** The match time after one stream message (clock messages tick it during gaps). */
export function timeAfter(t: MatchTime, msg: StreamMessage): MatchTime {
  if (msg.kind === 'event') return advanceTime(t, msg.event.period, msg.event.match_clock_ms);
  if (msg.kind === 'clock') return advanceTime(t, msg.period, msg.match_clock_ms);
  if (msg.kind === 'frame') return advanceTime(t, msg.p, msg.t);
  if (msg.kind === 'overlay') return advanceTime(t, undefined, msg.overlay.match_clock_ms);
  return t;
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
  /** The overlay that withdrew or replaced this one (a `retract` or a `correct`). */
  replacedBy?: Overlay;
  /** For a `correct`: the card it replaces. */
  corrects?: Overlay;
  /** Why it was withdrawn or corrected: the correction banner's headline for the same shot,
   *  in the same language and mode (e.g. "Goal disallowed after review"). */
  reason?: string;
}

export interface CommentState {
  comment: AnalystComment;
  retracted: boolean;
}

/** Analyst comments in arrival order; a retract (the VAR overturn) marks its comment withdrawn. */
export function applyComments(received: AnalystComment[]): CommentState[] {
  const byId = new Map<string, CommentState>();
  for (const c of received) {
    if (c.op === 'retract') {
      const target = c.supersedes_comment_id ? byId.get(c.supersedes_comment_id) : undefined;
      if (target) target.retracted = true;
    } else if (!byId.has(c.comment_id)) {
      byId.set(c.comment_id, { comment: c, retracted: false });
    }
  }
  return [...byId.values()];
}

/** Applies ops in arrival order. A retract marks its superseded overlay as withdrawn. */
export function applyOverlays(received: Overlay[]): OverlayState[] {
  const byId = new Map<string, OverlayState>();
  const order: string[] = [];
  for (const o of received) {
    if (o.op === 'retract') {
      const target = o.supersedes_overlay_id ? byId.get(o.supersedes_overlay_id) : undefined;
      if (target) Object.assign(target, { retracted: true, replacedBy: o });
      continue;
    }
    if (byId.has(o.overlay_id)) continue; // duplicate delivery
    let corrects: Overlay | undefined;
    if (o.op === 'correct' && o.supersedes_overlay_id) {
      const target = byId.get(o.supersedes_overlay_id);
      if (target) Object.assign(target, { retracted: true, replacedBy: o });
      corrects = target?.overlay;
    }
    byId.set(o.overlay_id, { overlay: o, retracted: false, ...(corrects ? { corrects } : {}) });
    order.push(o.overlay_id);
  }
  const states = order.map((id) => byId.get(id)!);
  // Link each withdrawn or corrected card to the banner that explains it (same shot, same
  // language and mode), so viewers see why, not just that it changed.
  const banners = states.filter((st) => st.overlay.template_id === 'correction_banner');
  for (const st of states) {
    if (!st.replacedBy && !st.corrects) continue;
    const shot = st.overlay.source_event_ids[0];
    const banner = [...banners].reverse().find((b) => b.overlay.lang === st.overlay.lang
      && b.overlay.audience_mode === st.overlay.audience_mode && b.overlay.source_event_ids.includes(shot));
    if (banner) st.reason = banner.overlay.slots.headline;
  }
  return states;
}

/**
 * Personalization changes WHICH overlays appear, not only their wording:
 * - language and mode pick the variant;
 * - "my metric" keeps only that metric (corrections always pass), and reveals the
 *   secondary cards of that metric, which no other viewer sees;
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
    if (o.secondary && s.metric === 'all') return false;
    if (s.mode === 'casual' && hasFavorites && !isFavorite(o)) return false;
    return true;
  });
}

/**
 * Which card the slot shows (frontend gap 5): among cards still within their display
 * window, favorites first, then priority (1 = most important), then the newest. When no
 * card is active, the most recent one stays up, so the stage never goes blank.
 */
export function pickCard(
  cards: OverlayState[],
  s: ViewerSettings,
  players: Player[],
  clockMs: number,
): OverlayState | undefined {
  const active = cards.filter(({ overlay: o }) =>
    clockMs >= o.match_clock_ms && clockMs < o.match_clock_ms + o.ttl_ms);
  if (active.length === 0) return cards[cards.length - 1];
  const index = new Map(cards.map((c, i) => [c.overlay.overlay_id, i]));
  return [...active].sort((a, b) => {
    const fav = Number(isFavoriteOverlay(b.overlay, s, players)) - Number(isFavoriteOverlay(a.overlay, s, players));
    if (fav !== 0) return fav;
    if (a.overlay.priority !== b.overlay.priority) return a.overlay.priority - b.overlay.priority;
    return index.get(b.overlay.overlay_id)! - index.get(a.overlay.overlay_id)!;
  })[0];
}

export function isFavoriteOverlay(o: Overlay, s: ViewerSettings, players: Player[]): boolean {
  if (!o.player_id) return false;
  const club = players.find((p) => p.player_id === o.player_id)?.club_id ?? '';
  return s.favoritePlayers.includes(o.player_id) || s.favoriteClubs.includes(club);
}

// ---------- Player focus: tonight vs his own norm ----------

/** Players the viewer can follow in focus mode: those with a season shot norm to compare with. */
export function canFocus(p: Player): boolean {
  return p.season_shot_speed_norm_kmh !== null;
}

export interface FocusStats {
  shots: number;
  avgSpeed: number | null;
  norm: number | null;
  lastSpeed: number | null;
  goals: number;
}

export function focusStats(store: Map<string, MatchEvent>, player: Player): FocusStats {
  const shots = orderedEvents(store).filter((e) => e.type === 'shot' && e.player_id === player.player_id);
  // Speed comparisons use foot shots only: headers would drag the average down.
  const speeds = shots
    .filter((e) => e.body_part !== 'head' && e.body_part !== 'other')
    .map((e) => e.tracking?.shot_speed_kmh)
    .filter((v): v is number => typeof v === 'number');
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

export interface FeedStatus {
  label: string;
  /** on: data is flowing; idle: nothing expected (paused, full time); off: trying to connect. */
  tone: 'on' | 'idle' | 'off';
  title: string;
}

/** The header badge: where the viewer's data comes from and whether it is arriving. */
export function feedStatus(s: { source: 'mock' | 'sse'; playing: boolean; connected: boolean; ended: boolean }): FeedStatus {
  if (s.ended) return { label: 'Full time', tone: 'idle', title: 'The replay reached the end of the match' };
  if (!s.playing) return { label: 'Paused', tone: 'idle', title: 'Playback paused; press Play to resume' };
  if (s.source === 'mock') return { label: 'Mock replay', tone: 'on', title: 'Built-in demo match, no backend' };
  if (s.connected) return { label: 'Live stream', tone: 'on', title: 'Connected: the backend streams the synthetic match through the pipeline' };
  return { label: 'Connecting…', tone: 'off', title: 'Waiting for the backend stream; retrying automatically' };
}
