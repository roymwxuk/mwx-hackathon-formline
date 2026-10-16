/**
 * Overlay output contract (DATA_SCHEMA.md §6.5). The backend fills one template
 * from a fixed catalog; the frontend only renders it. Every overlay cites the
 * events it was derived from (`source_event_ids`) for explainability and so
 * feed corrections can find and retract dependent overlays.
 *
 * Op semantics:
 * - show:    display a new overlay. With `supersedes_overlay_id`, it replaces
 *            an earlier one because state moved on (e.g. a refreshed player strip).
 * - correct: replace an earlier overlay because its source data was corrected.
 * - retract: remove an earlier overlay whose source data no longer holds.
 */

import type { EventId } from "./feed";
import type { AudienceMode, Lang } from "./personalization";
import type { PlayerId } from "./reference";

/** Extra label/value rows shown in analyst mode only. */
export interface DetailRow {
  label: string;
  value: string;
}

export interface TemplateSlots {
  /** Shot speed vs the shooter's own norm. */
  shot_speed_card: {
    headline: string;
    stat: string;
    sub: string;
    details?: DetailRow[];
  };
  /** Where this attempt ranks among the player's own comparable attempts. */
  baseline_percentile_card: {
    headline: string;
    metric_label: string;
    /** 0–100. */
    percentile: number;
    /** E.g. "Based on 14 similar shots, blended with forward-group prior". */
    sample_note: string;
    details?: DetailRow[];
  };
  /** This chance vs the player's typical good finish from this spot. */
  chance_vs_norm_card: {
    headline: string;
    chance_pct: number;
    norm_pct: number;
    sub: string;
    details?: DetailRow[];
  };
  /** Shown when a feed correction (e.g. VAR) invalidates earlier overlays. */
  correction_banner: {
    headline: string;
    sub: string;
  };
  /** Persistent strip for player focus mode. */
  player_focus_strip: {
    player_id: PlayerId;
    player_name: string;
    shots: number;
    on_target: number;
    /** Foot shots only; headers are excluded. */
    avg_shot_speed_kmh: number | null;
    /** Signed difference vs his own baseline, e.g. -6.2. */
    speed_vs_baseline_kmh: number | null;
  };
}

export type TemplateId = keyof TemplateSlots;

interface OverlayBase {
  overlay_id: string;
  match_clock_ms: number;
  ttl_ms: number;
  /** Lower number = higher priority. */
  priority: number;
  audience_mode: AudienceMode;
  lang: Lang;
  insight_id: string | null;
  source_event_ids: EventId[];
  /** True once the verifier has checked every number against engine output. */
  verified: boolean;
}

type TemplatedOverlay = {
  [K in TemplateId]: OverlayBase & { template_id: K; slots: TemplateSlots[K] };
}[TemplateId];

export type ShowOverlay = TemplatedOverlay & {
  op: "show";
  supersedes_overlay_id: string | null;
};

export type CorrectOverlay = TemplatedOverlay & {
  op: "correct";
  supersedes_overlay_id: string;
};

export type RetractOverlay = OverlayBase & {
  op: "retract";
  supersedes_overlay_id: string;
  template_id: null;
  slots: null;
};

export type Overlay = ShowOverlay | CorrectOverlay | RetractOverlay;
