/**
 * Reference data (DATA_SCHEMA.md §2). Clubs, players and venues are fictional.
 */

export type ClubId = string;
export type PlayerId = string;
export type MatchId = string;

export interface Club {
  club_id: ClubId;
  name: string;
  short_name: string;
  colors: { primary: string; secondary: string };
}

/** Derived from `position`; used as the shrinkage prior group. */
export type PositionGroup = "GK" | "DEF" | "MID" | "FWD";

export interface Player {
  player_id: PlayerId;
  display_name: string;
  club_id: ClubId;
  shirt_number: number;
  position: string;
  position_group: PositionGroup;
  preferred_foot: "left" | "right" | "both";
}

export interface Match {
  match_id: MatchId;
  season: string;
  matchday: number;
  kickoff_at: string;
  home_club_id: ClubId;
  away_club_id: ClubId;
  venue: string;
  is_live_demo: boolean;
}
