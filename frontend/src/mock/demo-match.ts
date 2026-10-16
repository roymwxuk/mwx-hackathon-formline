/**
 * Hand-written mock replay for building the viewer UI before the backend emits
 * overlays. Covers about nearly four minutes of the first half (38:00–41:42):
 *
 * 1. Harbourside build-up; Reyner's shot is saved (below his usual power).
 * 2. Northgate counter; Nakamura scores a top-end strike by his standards.
 * 3. Harbourside reply; Reyner heads in, then VAR disallows it. The shot
 *    arrives again as a v2 update, and dependent overlays are retracted.
 * 4. Northgate free kick; Osei fouls Nakamura and is booked.
 *
 * Overlays are pre-generated per viewer, the way the backend will deliver
 * them: the casual Japanese viewer gets fewer, favorite-led cards; the English
 * analyst following Reyner gets denser cards and a persistent player strip.
 * All names are fictional.
 */

import type {
  BallRecoveryEvent,
  CardEvent,
  Club,
  ClubId,
  DuelEvent,
  EventId,
  FeedMessage,
  FoulCommittedEvent,
  FreezeFramePlayer,
  HalfStartEvent,
  Match,
  MatchEvent,
  Overlay,
  PassEvent,
  Player,
  PlayerId,
  PlayPattern,
  PressureEvent,
  ShotEvent,
  VarReviewEndEvent,
  VarReviewStartEvent,
  ViewerProfile,
} from "@/contract";

const HAR: ClubId = "clb_harbourside";
const NOR: ClubId = "clb_northgate";

export const demoMatch: Match = {
  match_id: "mtc_s26_md14_har_nor",
  season: "2026-27",
  matchday: 14,
  kickoff_at: "2026-12-05T15:00:00.000Z",
  home_club_id: HAR,
  away_club_id: NOR,
  venue: "Quayside Park",
  is_live_demo: true,
};

export const demoClubs: Club[] = [
  {
    club_id: HAR,
    name: "Harbourside Athletic",
    short_name: "HAR",
    colors: { primary: "#1d4ed8", secondary: "#f8fafc" },
  },
  {
    club_id: NOR,
    name: "Northgate Rovers",
    short_name: "NOR",
    colors: { primary: "#dc2626", secondary: "#111827" },
  },
];

export const demoPlayers: Player[] = [
  { player_id: "ply_0101", display_name: "Hale", club_id: HAR, shirt_number: 1, position: "GK", position_group: "GK", preferred_foot: "right" },
  { player_id: "ply_0103", display_name: "Osei", club_id: HAR, shirt_number: 4, position: "CB", position_group: "DEF", preferred_foot: "right" },
  { player_id: "ply_0105", display_name: "Lindgren", club_id: HAR, shirt_number: 8, position: "CM", position_group: "MID", preferred_foot: "left" },
  { player_id: "ply_0106", display_name: "Petrov", club_id: HAR, shirt_number: 10, position: "CAM", position_group: "MID", preferred_foot: "right" },
  { player_id: "ply_0107", display_name: "Reyner", club_id: HAR, shirt_number: 9, position: "ST", position_group: "FWD", preferred_foot: "right" },
  { player_id: "ply_0109", display_name: "Achterberg", club_id: HAR, shirt_number: 11, position: "LW", position_group: "FWD", preferred_foot: "left" },
  { player_id: "ply_0201", display_name: "Brandt", club_id: NOR, shirt_number: 1, position: "GK", position_group: "GK", preferred_foot: "right" },
  { player_id: "ply_0203", display_name: "Ferraz", club_id: NOR, shirt_number: 3, position: "LB", position_group: "DEF", preferred_foot: "left" },
  { player_id: "ply_0205", display_name: "Kim", club_id: NOR, shirt_number: 6, position: "DM", position_group: "MID", preferred_foot: "right" },
  { player_id: "ply_0206", display_name: "Duarte", club_id: NOR, shirt_number: 8, position: "CM", position_group: "MID", preferred_foot: "right" },
  { player_id: "ply_0207", display_name: "Nakamura", club_id: NOR, shirt_number: 7, position: "RW", position_group: "FWD", preferred_foot: "left" },
];

const playerById = new Map(demoPlayers.map((p) => [p.player_id, p]));

type CommonFields = Omit<HalfStartEvent, "type">;
type Step = [PlayerId, number, number];

/** Builds the feed in event-time order with consistent ids, clocks and possessions. */
class FeedBuilder {
  readonly messages: FeedMessage[] = [];
  clock: number;
  private eventSeq = 860;
  private sequence = 10200;
  private possession = 55;
  private possessionTeam: ClubId = HAR;
  private playPattern: PlayPattern = "regular_play";
  private readonly kickoffMs = Date.parse(demoMatch.kickoff_at);

  constructor(startClockMs: number) {
    this.clock = startClockMs;
  }

  newPossession(team: ClubId, pattern: PlayPattern = "regular_play"): void {
    this.possession += 1;
    this.possessionTeam = team;
    this.playPattern = pattern;
  }

  advance(ms: number): void {
    this.clock += ms;
  }

  common(
    team: ClubId,
    playerId: PlayerId | null,
    x: number,
    y: number,
    opts: { underPressure?: boolean; durationMs?: number; related?: EventId[] } = {},
  ): CommonFields {
    this.eventSeq += 1;
    return {
      event_id: `evt_${String(this.eventSeq).padStart(6, "0")}`,
      match_id: demoMatch.match_id,
      period: 1,
      match_clock_ms: this.clock,
      event_time: this.iso(this.clock),
      team_id: team,
      player_id: playerId,
      position: playerId ? (playerById.get(playerId)?.position ?? null) : null,
      possession: this.possession,
      possession_team_id: this.possessionTeam,
      play_pattern: this.playPattern,
      x,
      y,
      under_pressure: opts.underPressure ?? false,
      duration_ms: opts.durationMs ?? null,
      related_event_ids: opts.related ?? [],
    };
  }

  emit<E extends MatchEvent>(event: E): E {
    this.push("create", event, 1, this.clock + 700);
    return event;
  }

  /** Re-send an event with a corrected full payload at the current clock. */
  update<E extends MatchEvent>(event: E, version: number): E {
    this.push("update", event, version, this.clock + 700);
    return event;
  }

  /** Emit a chain of passes; each step's player receives the previous pass. */
  passes(team: ClubId, steps: Step[], gapMs = 2200, last: Partial<PassEvent> = {}): PassEvent[] {
    const out: PassEvent[] = [];
    for (let i = 0; i < steps.length - 1; i++) {
      const [from, x, y] = steps[i];
      const [to, endX, endY] = steps[i + 1];
      const lengthM = Math.hypot((endX - x) * 1.05, (endY - y) * 0.68);
      const pass: PassEvent = {
        ...this.common(team, from, x, y, { durationMs: Math.round(lengthM * 60) }),
        type: "pass",
        recipient_id: to,
        end_x: endX,
        end_y: endY,
        length_m: Math.round(lengthM * 10) / 10,
        height: "ground",
        pass_type: "open_play",
        cross: false,
        through_ball: false,
        outcome: "complete",
        tracking: { ball_speed_kmh: Math.round(35 + lengthM * 1.1) },
        ...(i === steps.length - 2 ? last : {}),
      };
      out.push(this.emit(pass));
      this.advance(gapMs);
    }
    return out;
  }

  private push(op: "create" | "update", event: MatchEvent, version: number, emittedClock: number) {
    this.sequence += 1;
    this.messages.push({
      message_id: `msg_${this.sequence}`,
      op,
      event_id: event.event_id,
      version,
      emitted_at: this.iso(emittedClock),
      sequence: this.sequence,
      event,
    });
  }

  private iso(clockMs: number): string {
    return new Date(this.kickoffMs + clockMs).toISOString();
  }
}

const b = new FeedBuilder(38 * 60_000);

// 1. Harbourside build-up ending in Reyner's saved shot.
b.newPossession(HAR);
const buildUp = b.passes(HAR, [
  ["ply_0101", 8, 50],
  ["ply_0103", 22, 30],
  ["ply_0105", 40, 38],
  ["ply_0106", 58, 52],
  ["ply_0109", 72, 22],
  ["ply_0107", 84.2, 41.0],
]);
const keyPass1 = buildUp[buildUp.length - 1];
b.advance(-1400);
const pressureOnReyner = b.emit<PressureEvent>({
  ...b.common(NOR, "ply_0205", 100 - 86.0, 100 - 43.5, { durationMs: 900 }),
  type: "pressure",
  counterpress: false,
});
b.advance(1400);
const reynerFreeze: FreezeFramePlayer[] = [
  { x: 98.1, y: 49.0, teammate: false, goalkeeper: true },
  { x: 86.0, y: 43.5, teammate: false, goalkeeper: false },
  { x: 90.2, y: 46.8, teammate: false, goalkeeper: false },
  { x: 88.7, y: 55.1, teammate: true, goalkeeper: false },
];
const shot1 = b.emit<ShotEvent>({
  ...b.common(HAR, "ply_0107", 84.2, 41.0, {
    underPressure: true,
    durationMs: 420,
    related: [keyPass1.event_id, pressureOnReyner.event_id],
  }),
  type: "shot",
  body_part: "right_foot",
  technique: "normal",
  shot_type: "open_play",
  first_time: false,
  deflected: false,
  end_x: 100,
  end_y: 47.2,
  end_z: 0.6,
  outcome: "saved",
  key_pass_event_id: keyPass1.event_id,
  freeze_frame: reynerFreeze,
  tracking: { shot_speed_kmh: 84.1 },
});
b.advance(1800);

// 2. Brandt claims it; Northgate counter, Nakamura scores.
b.newPossession(NOR, "from_counter");
b.emit<BallRecoveryEvent>({
  ...b.common(NOR, "ply_0201", 2.5, 52.8),
  type: "ball_recovery",
  recovery_failure: false,
});
b.advance(3000);
const counter = b.passes(
  NOR,
  [
    ["ply_0201", 6, 50],
    ["ply_0203", 20, 68],
    ["ply_0205", 38, 55],
    ["ply_0206", 55, 40],
    ["ply_0207", 80, 46],
  ],
  2000,
  { through_ball: true },
);
const keyPass2 = counter[counter.length - 1];
b.advance(-800);
const shot2 = b.emit<ShotEvent>({
  ...b.common(NOR, "ply_0207", 80, 46, { durationMs: 310, related: [keyPass2.event_id] }),
  type: "shot",
  body_part: "left_foot",
  technique: "normal",
  shot_type: "open_play",
  first_time: false,
  deflected: false,
  end_x: 100,
  end_y: 45.5,
  end_z: 1.9,
  outcome: "goal",
  key_pass_event_id: keyPass2.event_id,
  freeze_frame: [
    { x: 95.4, y: 51.2, teammate: false, goalkeeper: true },
    { x: 86.5, y: 50.3, teammate: false, goalkeeper: false },
    { x: 84.0, y: 38.2, teammate: true, goalkeeper: false },
  ],
  tracking: { shot_speed_kmh: 112.4 },
});
b.advance(55_000);

// 3. Harbourside restart; Reyner heads in from Achterberg's cross, then VAR.
b.newPossession(HAR, "from_kick_off");
const restart = b.passes(
  HAR,
  [
    ["ply_0107", 50, 50],
    ["ply_0105", 42, 48],
    ["ply_0106", 60, 60],
    ["ply_0109", 78, 85],
    ["ply_0107", 93, 52],
  ],
  2600,
  { cross: true, height: "high" },
);
const cross = restart[restart.length - 1];
b.advance(-1200);
const aerial = b.emit<DuelEvent>({
  ...b.common(HAR, "ply_0107", 93, 52, { related: [cross.event_id] }),
  type: "duel",
  duel_type: "aerial",
  outcome: "won",
});
const shot3 = b.emit<ShotEvent>({
  ...b.common(HAR, "ply_0107", 93, 52, {
    underPressure: true,
    durationMs: 250,
    related: [cross.event_id, aerial.event_id],
  }),
  type: "shot",
  body_part: "head",
  technique: "normal",
  shot_type: "open_play",
  first_time: true,
  deflected: false,
  end_x: 100,
  end_y: 53.0,
  end_z: 1.1,
  outcome: "goal",
  key_pass_event_id: cross.event_id,
  freeze_frame: [
    { x: 98.6, y: 47.5, teammate: false, goalkeeper: true },
    { x: 93.8, y: 50.9, teammate: false, goalkeeper: false },
    { x: 91.0, y: 58.4, teammate: true, goalkeeper: false },
  ],
  tracking: { shot_speed_kmh: 61.0 },
});
b.advance(30_000);
const varStart = b.emit<VarReviewStartEvent>({
  ...b.common(HAR, null, 93, 52, { related: [shot3.event_id] }),
  type: "var_review_start",
  review_subject: "goal",
});
b.advance(65_000);
const varEnd = b.emit<VarReviewEndEvent>({
  ...b.common(HAR, null, 93, 52, { related: [shot3.event_id] }),
  type: "var_review_end",
  outcome: "no_goal",
});
// The provider re-sends the shot with the corrected outcome (full payload, v2).
b.update<ShotEvent>({ ...shot3, outcome: "off_target" }, 2);
b.advance(20_000);

// 4. Northgate free kick for offside; Osei fouls Nakamura and is booked.
b.newPossession(NOR, "from_free_kick");
b.passes(
  NOR,
  [
    ["ply_0201", 15, 50],
    ["ply_0206", 45, 45],
    ["ply_0207", 62, 70],
  ],
  2400,
);
const foul = b.emit<FoulCommittedEvent>({
  ...b.common(HAR, "ply_0103", 100 - 62, 100 - 70, { related: [] }),
  type: "foul_committed",
  card: "yellow",
  penalty: false,
});
b.advance(15_000);
b.emit<CardEvent>({
  ...b.common(HAR, "ply_0103", 100 - 62, 100 - 70, { related: [foul.event_id] }),
  type: "card",
  card: "yellow",
});

export const demoFeed: FeedMessage[] = b.messages;

/** First and last match clock covered by the replay. */
export const demoClockRange = {
  startMs: 38 * 60_000,
  endMs: b.clock,
};

export const demoViewers: ViewerProfile[] = [
  {
    viewer_id: "casual_ja",
    label: "Casual fan (日本語) · Northgate",
    mode: "casual",
    lang: "ja",
    favorite_club_ids: [NOR],
    favorite_player_ids: ["ply_0207"],
    focus_player_id: null,
    my_metric: null,
  },
  {
    viewer_id: "analyst_en",
    label: "Analyst (English) · following Reyner",
    mode: "analyst",
    lang: "en",
    favorite_club_ids: [HAR],
    favorite_player_ids: ["ply_0107"],
    focus_player_id: "ply_0107",
    my_metric: null,
  },
];

// Overlays appear ~1.5 s after the event they explain (engine + agent latency).
const LATENCY = 1500;
const at = (e: MatchEvent, extra = 0) => e.match_clock_ms + LATENCY + extra;
const MATCH_TTL = 60 * 60_000;

const casualJa: Overlay[] = [
  {
    overlay_id: "ovl_ja_0001",
    op: "show",
    supersedes_overlay_id: null,
    match_clock_ms: at(shot2),
    ttl_ms: 8000,
    template_id: "shot_speed_card",
    priority: 1,
    audience_mode: "casual",
    lang: "ja",
    slots: {
      headline: "ナカムラ、自己最速クラスの一撃！",
      stat: "112 km/h",
      sub: "今季の自身の左足シュートで上位4%の速さ（推定）",
    },
    insight_id: "ins_0043",
    source_event_ids: [shot2.event_id, keyPass2.event_id],
    verified: true,
  },
  {
    overlay_id: "ovl_ja_0002",
    op: "show",
    supersedes_overlay_id: null,
    match_clock_ms: at(shot3),
    ttl_ms: 8000,
    template_id: "baseline_percentile_card",
    priority: 2,
    audience_mode: "casual",
    lang: "ja",
    slots: {
      headline: "レイナー、珍しいヘディング弾",
      metric_label: "コースの精度（本人比）",
      percentile: 91,
      sample_note: "ヘディングのデータが少ないため参考値（推定）",
    },
    insight_id: "ins_0044",
    source_event_ids: [shot3.event_id, cross.event_id],
    verified: true,
  },
  {
    overlay_id: "ovl_ja_0003",
    op: "retract",
    supersedes_overlay_id: "ovl_ja_0002",
    match_clock_ms: at(varEnd),
    ttl_ms: 0,
    template_id: null,
    slots: null,
    priority: 1,
    audience_mode: "casual",
    lang: "ja",
    insight_id: "ins_0044",
    source_event_ids: [shot3.event_id, varEnd.event_id],
    verified: true,
  },
  {
    overlay_id: "ovl_ja_0004",
    op: "show",
    supersedes_overlay_id: null,
    match_clock_ms: at(varEnd),
    ttl_ms: 10_000,
    template_id: "correction_banner",
    priority: 1,
    audience_mode: "casual",
    lang: "ja",
    slots: {
      headline: "VAR：レイナーのゴールは取り消し",
      sub: "先ほどのヘディングの分析を取り消しました",
    },
    insight_id: null,
    source_event_ids: [shot3.event_id, varStart.event_id, varEnd.event_id],
    verified: true,
  },
];

const reynerStrip = (
  overlayId: string,
  op: "show" | "correct",
  supersedes: string | null,
  clockMs: number,
  sources: EventId[],
  stats: { shots: number; on_target: number; avg: number; vs: number },
): Overlay => {
  const base = {
    overlay_id: overlayId,
    match_clock_ms: clockMs,
    ttl_ms: MATCH_TTL,
    template_id: "player_focus_strip" as const,
    priority: 0,
    audience_mode: "analyst" as const,
    lang: "en" as const,
    slots: {
      player_id: "ply_0107",
      player_name: "Reyner",
      shots: stats.shots,
      on_target: stats.on_target,
      avg_shot_speed_kmh: stats.avg,
      speed_vs_baseline_kmh: stats.vs,
    },
    insight_id: null,
    source_event_ids: sources,
    verified: true,
  };
  if (op === "show") return { ...base, op, supersedes_overlay_id: supersedes };
  if (!supersedes) throw new Error(`${overlayId}: a correction must supersede an overlay`);
  return { ...base, op, supersedes_overlay_id: supersedes };
};

const analystEn: Overlay[] = [
  // Two earlier foot shots this match (outside the replay window) averaged 97.0 km/h
  // against a season baseline of 96.0 km/h.
  reynerStrip("ovl_en_0001", "show", null, demoClockRange.startMs, [], {
    shots: 2,
    on_target: 1,
    avg: 97.0,
    vs: 1.0,
  }),
  {
    overlay_id: "ovl_en_0002",
    op: "show",
    supersedes_overlay_id: null,
    match_clock_ms: at(shot1),
    ttl_ms: 9000,
    template_id: "shot_speed_card",
    priority: 1,
    audience_mode: "analyst",
    lang: "en",
    slots: {
      headline: "Reyner — well below his usual power",
      stat: "84.1 km/h",
      sub: "15.2 km/h below his baseline for right-foot shots from this zone (estimate)",
      details: [
        { label: "Zone", value: "Central, 16–20 m" },
        { label: "His baseline (shrunk)", value: "99.3 km/h" },
        { label: "Sample", value: "n = 11 · weight 0.62 vs FWD prior" },
        { label: "Under pressure", value: "Yes · nearest defender 2.3 m" },
      ],
    },
    insight_id: "ins_0041",
    source_event_ids: [shot1.event_id, keyPass1.event_id, pressureOnReyner.event_id],
    verified: true,
  },
  reynerStrip("ovl_en_0003", "show", "ovl_en_0001", at(shot1, 500), [shot1.event_id], {
    shots: 3,
    on_target: 2,
    avg: 92.7,
    vs: -3.3,
  }),
  {
    overlay_id: "ovl_en_0004",
    op: "show",
    supersedes_overlay_id: null,
    match_clock_ms: at(shot1, 4000),
    ttl_ms: 9000,
    template_id: "chance_vs_norm_card",
    priority: 2,
    audience_mode: "analyst",
    lang: "en",
    slots: {
      headline: "Saved — a low-quality finish by his standards",
      chance_pct: 7,
      norm_pct: 31,
      sub: "Post-shot chance ~7% vs ~31% for his typical good finish from here (model estimates)",
      details: [
        { label: "xG (pre-shot)", value: "0.14" },
        { label: "PSxG", value: "0.07" },
        { label: "Placement", value: "Central, 0.6 m high" },
      ],
    },
    insight_id: "ins_0042",
    source_event_ids: [shot1.event_id],
    verified: true,
  },
  {
    overlay_id: "ovl_en_0005",
    op: "show",
    supersedes_overlay_id: null,
    match_clock_ms: at(shot2),
    ttl_ms: 9000,
    template_id: "baseline_percentile_card",
    priority: 2,
    audience_mode: "analyst",
    lang: "en",
    slots: {
      headline: "Nakamura — a top-end strike by his standards",
      metric_label: "Shot speed vs his own left-foot shots",
      percentile: 96,
      sample_note: "Based on 23 similar shots; light shrinkage, weight 0.81 (estimate)",
      details: [
        { label: "Shot speed", value: "112.4 km/h" },
        { label: "His baseline (shrunk)", value: "94.8 km/h" },
        { label: "Play pattern", value: "Counter, through ball from Duarte" },
      ],
    },
    insight_id: "ins_0043",
    source_event_ids: [shot2.event_id, keyPass2.event_id],
    verified: true,
  },
  {
    overlay_id: "ovl_en_0006",
    op: "show",
    supersedes_overlay_id: null,
    match_clock_ms: at(shot3),
    ttl_ms: 9000,
    template_id: "baseline_percentile_card",
    priority: 1,
    audience_mode: "analyst",
    lang: "en",
    slots: {
      headline: "Reyner — placement in his top 10% of headers",
      metric_label: "Header placement vs his own headers",
      percentile: 91,
      sample_note: "Only 6 headers, so heavily blended with the FWD prior, weight 0.27 (estimate)",
      details: [
        { label: "Goal-mouth point", value: "1.1 m high, 0.4 m inside post" },
        { label: "Delivery", value: "Cross from Achterberg" },
      ],
    },
    insight_id: "ins_0044",
    source_event_ids: [shot3.event_id, cross.event_id],
    verified: true,
  },
  reynerStrip("ovl_en_0007", "show", "ovl_en_0003", at(shot3, 500), [shot1.event_id, shot3.event_id], {
    shots: 4,
    on_target: 3,
    avg: 92.7,
    vs: -3.3,
  }),
  {
    overlay_id: "ovl_en_0008",
    op: "retract",
    supersedes_overlay_id: "ovl_en_0006",
    match_clock_ms: at(varEnd),
    ttl_ms: 0,
    template_id: null,
    slots: null,
    priority: 1,
    audience_mode: "analyst",
    lang: "en",
    insight_id: "ins_0044",
    source_event_ids: [shot3.event_id, varEnd.event_id],
    verified: true,
  },
  reynerStrip(
    "ovl_en_0009",
    "correct",
    "ovl_en_0007",
    at(varEnd),
    [shot1.event_id, shot3.event_id, varEnd.event_id],
    { shots: 4, on_target: 2, avg: 92.7, vs: -3.3 },
  ),
  {
    overlay_id: "ovl_en_0010",
    op: "show",
    supersedes_overlay_id: null,
    match_clock_ms: at(varEnd),
    ttl_ms: 10_000,
    template_id: "correction_banner",
    priority: 1,
    audience_mode: "analyst",
    lang: "en",
    slots: {
      headline: "VAR: Reyner goal disallowed",
      sub: "Header placement insight withdrawn; his header baseline rolled back to before this shot",
    },
    insight_id: null,
    source_event_ids: [shot3.event_id, varStart.event_id, varEnd.event_id],
    verified: true,
  },
];

export const demoOverlays: Record<string, Overlay[]> = {
  casual_ja: casualJa,
  analyst_en: analystEn,
};
