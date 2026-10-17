// Contracts shared with the backend. Mirrors DATA_SCHEMA.md (v0.2).

export type Lang = 'en' | 'ja';
export type AudienceMode = 'casual' | 'analyst';
export type Metric = 'shot_speed' | 'finishing';
export type MetricChoice = Metric | 'all';

export interface Club {
  club_id: string;
  name: string;
  short_name: string;
  color: string;
  text_color: string;
}

export interface Player {
  player_id: string;
  display_name: string;
  display_name_ja: string;
  club_id: string;
  shirt_number: number;
  position?: string;
  /** Season strong-foot shot-speed baseline (shrunk mean) from the engine; null for keepers. */
  season_shot_speed_norm_kmh: number | null;
}

export interface FreezeFramePlayer {
  x: number;
  y: number;
  teammate: boolean;
  goalkeeper: boolean;
}

/** Subset of the raw event (DATA_SCHEMA.md §4–5) the viewer needs to draw the pitch. */
export interface MatchEvent {
  event_id: string;
  version: number;
  type: 'pass' | 'shot' | 'var_review_start' | 'var_review_end' | 'half_start' | 'half_end';
  /** 1 or 2. The clock restarts at 45:00 in period 2, so order by (period, clock). */
  period?: number;
  match_clock_ms: number;
  team_id: string | null;
  player_id: string | null;
  x: number | null;
  y: number | null;
  end_x?: number;
  end_y?: number;
  outcome?: string;
  body_part?: string;
  freeze_frame?: FreezeFramePlayer[];
  tracking?: { shot_speed_kmh?: number };
  related_event_ids?: string[];
}

export type TemplateId =
  | 'shot_speed_card'
  | 'placement_card'
  | 'finish_quality_card'
  | 'correction_banner';

/** Overlay output contract (DATA_SCHEMA.md §6.5). */
export interface Overlay {
  overlay_id: string;
  op: 'show' | 'correct' | 'retract';
  supersedes_overlay_id: string | null;
  match_clock_ms: number;
  ttl_ms: number;
  template_id: TemplateId;
  priority: number;
  audience_mode: AudienceMode;
  lang: Lang;
  slots: OverlaySlots;
  insight_id: string;
  player_id: string | null;
  metric: Metric | null;
  source_event_ids: string[];
  verified: boolean;
  /** Runner-up insight of another metric: shown only when the viewer's "my metric" matches. */
  secondary?: boolean;
}

export interface OverlaySlots {
  tag: string;
  headline: string;
  stat?: string;
  sub?: string;
  /** Bar comparison: this value vs the player's own norm. */
  bars?: { label: string; value: number; display: string; highlight: boolean }[];
  /** Analyst detail rows. */
  rows?: { label: string; value: string }[];
}

/** One message on the live stream (SSE `data:` payload). */
export type StreamMessage =
  | { kind: 'event'; event: MatchEvent }
  | { kind: 'overlay'; overlay: Overlay }
  | { kind: 'clock'; period: number; match_clock_ms: number } // running match time during gaps
  | { kind: 'end' }; // the match feed is over

export interface ViewerSettings {
  lang: Lang;
  mode: AudienceMode;
  favoriteClubs: string[];
  favoritePlayers: string[];
  focusPlayer: string | null;
  metric: MetricChoice;
}
