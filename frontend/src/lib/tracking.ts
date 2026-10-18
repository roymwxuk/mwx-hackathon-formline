import type { Club, MatchEvent, Player, TrackingFrameMessage } from '@/lib/types';

/** One player drawn from a tracking frame, in pitch percentages (shared frame). */
export interface TrackedMarker {
  key: string; // 'h7', 'a1': stable across frames, so markers glide instead of re-mounting
  x: number;
  y: number;
  club: Club;
  player: Player | undefined;
}

/** Markers for every player in a frame. Tracking already uses the shared frame (home
 *  attacks toward x = 100), so no flipping is needed, unlike event coordinates. */
export function trackedMarkers(frame: TrackingFrameMessage, clubs: Club[], players: Player[]): TrackedMarker[] {
  const [home, away] = clubs;
  const byShirt = (club: Club) => new Map(players.filter((p) => p.club_id === club.club_id).map((p) => [p.shirt_number, p]));
  const out: TrackedMarker[] = [];
  for (const [side, club, rows] of [['h', home, frame.h], ['a', away, frame.a]] as const) {
    const shirts = byShirt(club);
    for (const [shirt, x, y] of rows) out.push({ key: `${side}${shirt}`, x, y, club, player: shirts.get(shirt) });
  }
  return out;
}

const LABEL_HOLD_MS = 8_000;

/** Who gets a name label: the focus player and the viewer's favorite players always; the
 *  passer and receiver of the latest pass, or the shooter, for a few seconds after the action. */
export function labelledPlayers(events: MatchEvent[], clockMs: number, focusPlayer: string | null,
  favorites: string[] = []): Set<string> {
  const ids = new Set<string>(favorites);
  if (focusPlayer) ids.add(focusPlayer);
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type !== 'pass' && e.type !== 'shot') continue;
    if (clockMs - e.match_clock_ms > LABEL_HOLD_MS) break;
    if (e.player_id) ids.add(e.player_id);
    if (e.type === 'pass' && e.recipient_id) ids.add(e.recipient_id);
    break;
  }
  return ids;
}
