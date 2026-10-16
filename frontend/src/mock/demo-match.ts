// MOCK DATA ONLY. Stands in for the backend until the real pipeline streams over SSE.
// Clubs and players are fictional. Overlay texts here are fixed templates; in the real
// system they come from the narrator agent and are checked by the verifier.

import type {
  AudienceMode,
  Club,
  Lang,
  MatchEvent,
  Metric,
  Overlay,
  OverlaySlots,
  Player,
  StreamMessage,
  TemplateId,
} from '@/lib/types';

export const MATCH_ID = 'mtc_s26_md14_har_nor';

export const CLUBS: Club[] = [
  { club_id: 'clb_harbourside', name: 'Harbourside Athletic', short_name: 'HAR', color: '#0B3D91', text_color: '#FFFFFF' },
  { club_id: 'clb_northgate', name: 'Northgate Rovers', short_name: 'NOR', color: '#E8E3D9', text_color: '#111111' },
];

export const PLAYERS: Player[] = [
  { player_id: 'ply_0107', display_name: 'Tomas Reyner', display_name_ja: 'トマス・レイナー', club_id: 'clb_harbourside', shirt_number: 9, season_shot_speed_norm_kmh: 96 },
  { player_id: 'ply_0111', display_name: 'Kenji Ito', display_name_ja: '伊藤健二', club_id: 'clb_harbourside', shirt_number: 11, season_shot_speed_norm_kmh: 91 },
  { player_id: 'ply_0104', display_name: 'Marco Silvestri', display_name_ja: 'マルコ・シルヴェストリ', club_id: 'clb_harbourside', shirt_number: 7, season_shot_speed_norm_kmh: 88 },
  { player_id: 'ply_0210', display_name: 'Daniel Okafor', display_name_ja: 'ダニエル・オカフォー', club_id: 'clb_northgate', shirt_number: 10, season_shot_speed_norm_kmh: 90 },
  { player_id: 'ply_0208', display_name: 'Lukas Brandt', display_name_ja: 'ルーカス・ブラント', club_id: 'clb_northgate', shirt_number: 8, season_shot_speed_norm_kmh: 85 },
];

const HAR = 'clb_harbourside';
const NOR = 'clb_northgate';

const m = (min: number, sec = 0) => (min * 60 + sec) * 1000;

// ---------- Key events (shots, VAR, periods) ----------

const keyEvents: MatchEvent[] = [
  { event_id: 'evt_000001', version: 1, type: 'half_start', match_clock_ms: 0, team_id: null, player_id: null, x: null, y: null },
  {
    event_id: 'evt_000311', version: 1, type: 'shot', match_clock_ms: m(12, 5), team_id: HAR, player_id: 'ply_0107',
    x: 82.5, y: 58.0, end_x: 100, end_y: 53.4, outcome: 'saved', tracking: { shot_speed_kmh: 101.2 },
    freeze_frame: [
      { x: 98.4, y: 50.5, teammate: false, goalkeeper: true },
      { x: 88.0, y: 55.0, teammate: false, goalkeeper: false },
      { x: 90.5, y: 61.0, teammate: false, goalkeeper: false },
    ],
  },
  {
    event_id: 'evt_000540', version: 1, type: 'shot', match_clock_ms: m(22, 30), team_id: HAR, player_id: 'ply_0111',
    x: 88.0, y: 44.0, end_x: 100, end_y: 46.0, outcome: 'goal', tracking: { shot_speed_kmh: 94.0 },
    freeze_frame: [
      { x: 97.8, y: 52.0, teammate: false, goalkeeper: true },
      { x: 91.0, y: 47.5, teammate: false, goalkeeper: false },
    ],
  },
  {
    event_id: 'evt_000655', version: 1, type: 'shot', match_clock_ms: m(27, 52), team_id: NOR, player_id: 'ply_0210',
    x: 93.0, y: 52.0, end_x: 100, end_y: 50.2, outcome: 'saved', tracking: { shot_speed_kmh: 62.0 },
    freeze_frame: [
      { x: 98.9, y: 49.0, teammate: false, goalkeeper: true },
      { x: 92.5, y: 48.0, teammate: false, goalkeeper: false },
    ],
  },
  {
    event_id: 'evt_000873', version: 1, type: 'shot', match_clock_ms: m(40, 12) + 300, team_id: HAR, player_id: 'ply_0107',
    x: 84.2, y: 41.0, end_x: 100, end_y: 47.2, outcome: 'saved', tracking: { shot_speed_kmh: 84.1 },
    related_event_ids: ['evt_000871'],
    freeze_frame: [
      { x: 98.1, y: 49.0, teammate: false, goalkeeper: true },
      { x: 86.0, y: 43.5, teammate: false, goalkeeper: false },
      { x: 90.2, y: 46.8, teammate: false, goalkeeper: false },
      { x: 88.7, y: 55.1, teammate: true, goalkeeper: false },
    ],
  },
  { event_id: 'evt_000990', version: 1, type: 'half_end', match_clock_ms: m(45), team_id: null, player_id: null, x: null, y: null },
  { event_id: 'evt_000991', version: 1, type: 'half_start', match_clock_ms: m(45) + 1, team_id: null, player_id: null, x: null, y: null },
  {
    event_id: 'evt_001204', version: 1, type: 'shot', match_clock_ms: m(63, 42), team_id: HAR, player_id: 'ply_0107',
    x: 87.0, y: 61.0, end_x: 100, end_y: 52.5, outcome: 'goal', tracking: { shot_speed_kmh: 118.3 },
    freeze_frame: [
      { x: 97.5, y: 47.0, teammate: false, goalkeeper: true },
      { x: 90.0, y: 57.0, teammate: false, goalkeeper: false },
    ],
  },
  { event_id: 'evt_001217', version: 1, type: 'var_review_start', match_clock_ms: m(64, 10), team_id: null, player_id: null, x: null, y: null, related_event_ids: ['evt_001204'] },
  { event_id: 'evt_001219', version: 1, type: 'var_review_end', match_clock_ms: m(65, 27), team_id: null, player_id: null, x: null, y: null, outcome: 'no_goal', related_event_ids: ['evt_001204'] },
  {
    event_id: 'evt_001289', version: 1, type: 'shot', match_clock_ms: m(78, 20), team_id: NOR, player_id: 'ply_0208',
    x: 76.0, y: 35.0, end_x: 100, end_y: 30.0, outcome: 'off_target', tracking: { shot_speed_kmh: 79.0 },
    freeze_frame: [
      { x: 98.0, y: 47.0, teammate: false, goalkeeper: true },
      { x: 82.0, y: 38.0, teammate: false, goalkeeper: false },
    ],
  },
  { event_id: 'evt_001500', version: 1, type: 'half_end', match_clock_ms: m(90), team_id: null, player_id: null, x: null, y: null },
];

// VAR outcome: the provider re-sends the shot as version 2 with a changed outcome.
const varUpdate: MatchEvent = { ...keyEvents.find((e) => e.event_id === 'evt_001204')!, version: 2, outcome: 'off_target', match_clock_ms: m(63, 42) };
const VAR_UPDATE_AT = m(65, 28);

// ---------- Filler passes so the pitch moves (seeded, reproducible) ----------

function seededRandom(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function fillerPasses(): MatchEvent[] {
  const rand = seededRandom(20261016);
  const harIds = ['ply_0107', 'ply_0111', 'ply_0104'];
  const norIds = ['ply_0210', 'ply_0208'];
  const out: MatchEvent[] = [];
  let clock = 4000;
  let team = HAR;
  let x = 50;
  let y = 50;
  let n = 2;
  while (clock < m(90) - 4000) {
    // Leave quiet windows around key moments so the shot stays on screen.
    const isKey = keyEvents.some((e) => clock > e.match_clock_ms - 6000 && clock < e.match_clock_ms + 25000);
    if (!isKey) {
      const ids = team === HAR ? harIds : norIds;
      const endX = Math.min(95, Math.max(5, x + (rand() * 30 - 8)));
      const endY = Math.min(95, Math.max(5, y + (rand() * 40 - 20)));
      out.push({
        event_id: `evt_p${String(n).padStart(5, '0')}`,
        version: 1,
        type: 'pass',
        match_clock_ms: clock,
        team_id: team,
        player_id: ids[Math.floor(rand() * ids.length)],
        x,
        y,
        end_x: endX,
        end_y: endY,
        outcome: rand() < 0.83 ? 'complete' : 'incomplete',
      });
      n += 1;
      x = endX;
      y = endY;
      if (rand() < 0.15) {
        team = team === HAR ? NOR : HAR;
        x = 100 - x;
        y = 100 - y;
      }
    }
    clock += 9000 + Math.floor(rand() * 9000);
  }
  return out;
}

// ---------- Overlays (4 variants per insight: en/ja × casual/analyst) ----------

type Variants = Record<Lang, Record<AudienceMode, OverlaySlots>>;

interface Insight {
  no: number;
  player_id: string | null;
  metric: Metric | null;
  template: TemplateId;
  clock: number;
  priority: number;
  source: string[];
  variants: Variants;
}

interface SpeedArgs {
  name: string;
  nameJa: string;
  value: number;
  norm: number;
  pct: string;
  pctJa: string;
  n: number;
  w: number;
  bucket: string;
  bucketJa: string;
  xg: string;
  psxg: string;
  headline: string;
  headlineJa: string;
}

function speedVariants(a: SpeedArgs): Variants {
  const d = +(a.value - a.norm).toFixed(1);
  const abs = Math.abs(Math.round(d));
  const below = d < 0;
  const bars = (thisLabel: string, normLabel: string) => [
    { label: thisLabel, value: a.value, display: `${Math.round(a.value)} km/h`, highlight: true },
    { label: normLabel, value: a.norm, display: `${Math.round(a.norm)} km/h`, highlight: false },
  ];
  const sign = d > 0 ? `+${d}` : `${d}`;
  return {
    en: {
      casual: {
        tag: 'SHOT SPEED · VS HIS OWN NORM',
        headline: a.headline,
        bars: bars('This shot', 'His norm'),
        sub: `About ${abs} km/h ${below ? 'below' : 'above'} his typical shot from this range (estimate).`,
      },
      analyst: {
        tag: 'SHOT SPEED · PERSONAL BASELINE',
        headline: `${a.name} ${a.value} km/h · Δ ${sign} vs baseline`,
        rows: [
          { label: 'Baseline (shrunk)', value: `${a.norm} km/h` },
          { label: 'Sample · weight', value: `n=${a.n} · ${a.w}` },
          { label: 'Comparison group', value: a.bucket },
          { label: 'Percentile', value: a.pct },
          { label: 'xG · PSxG', value: `${a.xg} · ${a.psxg}` },
        ],
        sub: 'All figures are model estimates.',
      },
    },
    ja: {
      casual: {
        tag: 'シュートスピード・本人比',
        headline: a.headlineJa,
        bars: bars('今回', '本人の平均'),
        sub: `この距離からの普段のシュートより約${abs} km/h${below ? '遅い' : '速い'}（推定）`,
      },
      analyst: {
        tag: 'シュートスピード・本人ベースライン',
        headline: `${a.nameJa} ${a.value} km/h・基準比 ${sign}`,
        rows: [
          { label: '基準値（縮小推定）', value: `${a.norm} km/h` },
          { label: 'サンプル数・重み', value: `n=${a.n}・${a.w}` },
          { label: '比較グループ', value: a.bucketJa },
          { label: 'パーセンタイル', value: a.pctJa },
          { label: 'xG・PSxG', value: `${a.xg}・${a.psxg}` },
        ],
        sub: '数値はすべてモデルによる推定値です。',
      },
    },
  };
}

const insights: Insight[] = [
  {
    no: 1, player_id: 'ply_0107', metric: 'finishing', template: 'placement_card', clock: m(12, 7), priority: 3, source: ['evt_000311'],
    variants: {
      en: {
        casual: { tag: 'FINISHING · VS HIS OWN NORM', headline: 'Reyner picks his corner', sub: 'Placement in the top 20% of his finishes from the edge of the box (estimate).' },
        analyst: {
          tag: 'FINISHING · PERSONAL BASELINE', headline: 'Reyner placement: 80th percentile',
          rows: [
            { label: 'Comparison group', value: 'Edge of box · R foot' },
            { label: 'Sample · weight', value: 'n=24 · 0.83' },
            { label: 'xG · PSxG', value: '0.07 · 0.21' },
          ],
          sub: 'All figures are model estimates.',
        },
      },
      ja: {
        casual: { tag: 'フィニッシュ・本人比', headline: 'レイナー、コースを突いた', sub: 'ペナルティエリア手前からの本人のシュートの中で、上位20%のコース（推定）' },
        analyst: {
          tag: 'フィニッシュ・本人ベースライン', headline: 'レイナーのコース：80パーセンタイル',
          rows: [
            { label: '比較グループ', value: 'エリア手前・右足' },
            { label: 'サンプル数・重み', value: 'n=24・0.83' },
            { label: 'xG・PSxG', value: '0.07・0.21' },
          ],
          sub: '数値はすべてモデルによる推定値です。',
        },
      },
    },
  },
  {
    no: 2, player_id: 'ply_0210', metric: 'shot_speed', template: 'shot_speed_card', clock: m(27, 54), priority: 3, source: ['evt_000655'],
    variants: speedVariants({
      name: 'Okafor', nameJa: 'オカフォー', value: 62.0, norm: 51.5, pct: '96th', pctJa: '96パーセンタイル', n: 14, w: 0.74,
      bucket: 'Six-yard area · header', bucketJa: 'ゴールエリア・ヘディング', xg: '0.31', psxg: '0.44',
      headline: "Okafor's fastest header of the season", headlineJa: 'オカフォー、今季最速のヘディング',
    }),
  },
  {
    no: 3, player_id: 'ply_0107', metric: 'shot_speed', template: 'shot_speed_card', clock: m(40, 14), priority: 2, source: ['evt_000873'],
    variants: speedVariants({
      name: 'Reyner', nameJa: 'レイナー', value: 84.1, norm: 99.4, pct: '12th', pctJa: '12パーセンタイル', n: 31, w: 0.86,
      bucket: 'Edge of box · R foot · pressured', bucketJa: 'エリア手前・右足・プレッシャー下', xg: '0.06', psxg: '0.09',
      headline: 'Reyner — not his usual strike', headlineJa: 'レイナー、いつもの威力がない',
    }),
  },
  {
    no: 4, player_id: 'ply_0107', metric: 'shot_speed', template: 'shot_speed_card', clock: m(63, 44), priority: 1, source: ['evt_001204'],
    variants: speedVariants({
      name: 'Reyner', nameJa: 'レイナー', value: 118.3, norm: 99.4, pct: '100th (season max)', pctJa: '今季最高', n: 32, w: 0.86,
      bucket: 'Box · R foot', bucketJa: 'エリア内・右足', xg: '0.14', psxg: '0.52',
      headline: "Reyner's fastest goal of the season", headlineJa: 'レイナー、今季最速のゴール',
    }),
  },
  {
    no: 5, player_id: null, metric: null, template: 'correction_banner', clock: m(65, 29), priority: 1, source: ['evt_001219', 'evt_001204'],
    variants: {
      en: {
        casual: { tag: 'CORRECTION · VAR', headline: 'Goal disallowed (offside in the build-up)', sub: 'The earlier stat has been withdrawn.' },
        analyst: { tag: 'CORRECTION · VAR', headline: 'Goal disallowed (offside in the build-up)', sub: 'Overlay withdrawn; finishing baseline rebuilt from the event log (season goals 7 → 6).' },
      },
      ja: {
        casual: { tag: '訂正・VAR', headline: 'ゴール取り消し（ビルドアップでオフサイド）', sub: '先ほどの表示を取り消しました。' },
        analyst: { tag: '訂正・VAR', headline: 'ゴール取り消し（ビルドアップでオフサイド）', sub: '表示を取り消し、イベントログからフィニッシュの基準値を再計算しました（今季ゴール 7 → 6）。' },
      },
    },
  },
  {
    no: 6, player_id: 'ply_0208', metric: 'finishing', template: 'finish_quality_card', clock: m(78, 22), priority: 4, source: ['evt_001289'],
    variants: {
      en: {
        casual: { tag: 'FINISHING · VS HIS OWN NORM', headline: 'Brandt snatches at it', sub: 'One of his least accurate attempts from distance this season (estimate).' },
        analyst: {
          tag: 'FINISHING · PERSONAL BASELINE', headline: 'Brandt miss: 9th percentile placement',
          rows: [
            { label: 'Comparison group', value: 'Long range · R foot' },
            { label: 'Sample · weight', value: 'n=19 · 0.79' },
            { label: 'xG', value: '0.03' },
          ],
          sub: 'All figures are model estimates.',
        },
      },
      ja: {
        casual: { tag: 'フィニッシュ・本人比', headline: 'ブラント、焦ったシュート', sub: '今季のミドルシュートの中でも特に精度の低い一本（推定）' },
        analyst: {
          tag: 'フィニッシュ・本人ベースライン', headline: 'ブラントのミス：コース9パーセンタイル',
          rows: [
            { label: '比較グループ', value: 'ロングレンジ・右足' },
            { label: 'サンプル数・重み', value: 'n=19・0.79' },
            { label: 'xG', value: '0.03' },
          ],
          sub: '数値はすべてモデルによる推定値です。',
        },
      },
    },
  },
];

const LANGS: Lang[] = ['en', 'ja'];
const MODES: AudienceMode[] = ['casual', 'analyst'];
const overlayId = (no: number, lang: Lang, mode: AudienceMode) => `ovl_${String(no).padStart(4, '0')}_${lang}_${mode}`;

function buildOverlays(): Overlay[] {
  const out: Overlay[] = [];
  for (const ins of insights) {
    for (const lang of LANGS) {
      for (const mode of MODES) {
        out.push({
          overlay_id: overlayId(ins.no, lang, mode),
          op: 'show',
          supersedes_overlay_id: null,
          match_clock_ms: ins.clock,
          ttl_ms: 12000,
          template_id: ins.template,
          priority: ins.priority,
          audience_mode: mode,
          lang,
          slots: ins.variants[lang][mode],
          insight_id: `ins_${String(ins.no).padStart(4, '0')}`,
          player_id: ins.player_id,
          metric: ins.metric,
          source_event_ids: ins.source,
          verified: true,
        });
      }
    }
  }
  // VAR: retract every variant of insight 4 (the overturned goal).
  for (const lang of LANGS) {
    for (const mode of MODES) {
      out.push({
        overlay_id: `ovl_0004r_${lang}_${mode}`,
        op: 'retract',
        supersedes_overlay_id: overlayId(4, lang, mode),
        match_clock_ms: m(65, 28),
        ttl_ms: 0,
        template_id: 'shot_speed_card',
        priority: 1,
        audience_mode: mode,
        lang,
        slots: { tag: '', headline: '' },
        insight_id: 'ins_0004',
        player_id: 'ply_0107',
        metric: 'shot_speed',
        source_event_ids: ['evt_001204'],
        verified: true,
      });
    }
  }
  return out;
}

/** The full demo stream, sorted by match clock, as the backend would send it over SSE. */
export function buildDemoStream(): { clock: number; msg: StreamMessage }[] {
  const items: { clock: number; msg: StreamMessage }[] = [];
  for (const e of [...keyEvents, ...fillerPasses()]) items.push({ clock: e.match_clock_ms, msg: { kind: 'event', event: e } });
  items.push({ clock: VAR_UPDATE_AT, msg: { kind: 'event', event: varUpdate } });
  for (const o of buildOverlays()) items.push({ clock: o.match_clock_ms, msg: { kind: 'overlay', overlay: o } });
  return items.sort((a, b) => a.clock - b.clock);
}

export const MATCH_END_MS = m(90);
