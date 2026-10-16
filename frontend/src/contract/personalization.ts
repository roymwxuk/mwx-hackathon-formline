/**
 * Viewer settings (CLAUDE.md "Personalize"). The backend uses these to decide
 * which insights reach a viewer, so two profiles get different overlay streams,
 * not the same stream with different wording.
 */

import type { ClubId, PlayerId } from "./reference";

export type AudienceMode = "casual" | "analyst";
export type Lang = "en" | "ja";

/** The one performance metric a viewer can pin ("my metric"). */
export type MyMetric = "shot_speed_kmh" | "finish_quality" | "placement";

export interface ViewerProfile {
  viewer_id: string;
  label: string;
  mode: AudienceMode;
  lang: Lang;
  favorite_club_ids: ClubId[];
  /** Favorite players get priority for overlay slots. */
  favorite_player_ids: PlayerId[];
  /** Follow one player all match; shows a persistent player strip. */
  focus_player_id: PlayerId | null;
  /** When set, overlays are filtered to this metric. */
  my_metric: MyMetric | null;
}
