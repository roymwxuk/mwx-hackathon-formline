import { useMemo, useState } from 'react';
import { FEATURES } from '@/lib/features';
import { t } from '@/lib/i18n';
import { isFavoriteOverlay, orderedEvents, personalize, pickCard, score, type OverlayState } from '@/lib/logic';
import type { Club, MatchEvent, Player, TrackingFrameMessage, ViewerSettings } from '@/lib/types';
import { CorrectionBanner, OverlayCard } from './OverlayCard';
import { commentsFor } from '@/lib/analyst';
import type { CommentState } from '@/lib/logic';
import { AnalystPanel, CommentBubble } from './Analyst';
import { asOfLatest } from '@/lib/analyst';
import { GoalFlash } from './GoalFlash';
import { RestartTag } from './RestartTag';
import { FocusStrip, OverlayLog, ScoreBug } from './Panels';
import { Pitch } from './Pitch';
import { SettingsPanel } from './SettingsPanel';

interface Props {
  id: string;
  title?: string;
  layout: 'full' | 'compact';
  clockMs: number;
  store: Map<string, MatchEvent>;
  overlayStates: OverlayState[];
  settings: ViewerSettings;
  onSettingsChange: (s: ViewerSettings) => void;
  clubs: Club[];
  players: Player[];
  /** Latest tracking frame, when the match has tracking data. */
  frame: TrackingFrameMessage | null;
  /** Match Analyst comments (all languages; filtered here). */
  commentStates: CommentState[];
  /** The stream is replaying the past at once (after a jump or reconnect): no pop-ups. */
  catchingUp: boolean;
  /** The Analyst's /ask endpoint for follow-up questions (live mode), else null. */
  askUrl: string | null;
}

const CORRECTION_HOLD_MS = 4 * 60_000;

export function Viewer(p: Props) {
  const { settings: s, clubs, players } = p;
  const events = useMemo(() => orderedEvents(p.store), [p.store]);
  const asOf = useMemo(() => asOfLatest(events), [events]); // typed questions: "as of now"
  const visible = useMemo(() => personalize(p.overlayStates, s, players), [p.overlayStates, s, players]);
  const cards = visible.filter((v) => v.overlay.template_id !== 'correction_banner');
  const [closed, setClosed] = useState<Set<string>>(() => new Set());
  const picked = pickCard(cards, s, players, p.clockMs);
  // A card the viewer closed stays hidden; the next card appears as usual.
  const current = picked && !closed.has(picked.overlay.overlay_id) ? picked : undefined;
  const close = (id: string) => setClosed((prev) => new Set(prev).add(id));
  const correction = [...visible].reverse().find((v) => v.overlay.template_id === 'correction_banner');
  const showCorrection = correction && p.clockMs - correction.overlay.match_clock_ms < CORRECTION_HOLD_MS;
  const focus = players.find((pl) => pl.player_id === s.focusPlayer);
  const str = t(s.lang);
  const comments = useMemo(() => commentsFor(p.commentStates, s.lang), [p.commentStates, s.lang]);

  const stage = (
    <div className="stage">
      <div className="pitch-wrap">
        <Pitch events={events} clockMs={p.clockMs} clubs={clubs} players={players} lang={s.lang}
          detailed={s.mode === 'analyst'} frame={p.frame} focusPlayer={s.focusPlayer}
          favoritePlayers={s.favoritePlayers}
          onPlayerClick={(id) => p.onSettingsChange({ ...s, focusPlayer: s.focusPlayer === id ? null : id })} />
        <GoalFlash events={events} clockMs={p.clockMs} clubs={clubs} players={players} lang={s.lang} paused={p.catchingUp} />
        <RestartTag events={events} clockMs={p.clockMs} lang={s.lang} paused={p.catchingUp} />
      </div>
      <ScoreBug clubs={clubs} score={score(p.store, [clubs[0].club_id, clubs[1].club_id])} clockMs={p.clockMs} />
      <div className="card-slot">
        {FEATURES.analystBubble && (
          <CommentBubble comments={comments} clockMs={p.clockMs} lang={s.lang} paused={p.catchingUp} />
        )}
        {current ? (
          <OverlayCard key={current.overlay.overlay_id} state={current} favorite={isFavoriteOverlay(current.overlay, s, players)}
            onClose={() => close(current.overlay.overlay_id)} />
        ) : picked ? null : (
          <div className="overlay-card waiting" lang={s.lang}>{str.waiting}</div>
        )}
      </div>
      {showCorrection && correction && <CorrectionBanner state={correction} />}
    </div>
  );

  if (p.layout === 'compact') {
    return (
      <section className="viewer compact" aria-label={p.title}>
        <div className="viewer-head">
          {p.title && <h2>{p.title}</h2>}
          <span className="pill">{s.mode === 'casual' ? 'Casual' : 'Analyst'}</span>
          <span className="pill">{s.lang === 'ja' ? '日本語' : 'English'}</span>
          {focus && <span className="pill">Focus: {focus.display_name}</span>}
          <span className="pill">Metric: {s.metric.replace('_', ' ')}</span>
        </div>
        {stage}
        {focus && <FocusStrip store={p.store} player={focus} lang={s.lang} />}
        <AnalystPanel comments={comments} lang={s.lang} limit={2} askUrl={p.askUrl} asOf={asOf} />
        <details className="panel">
          <summary>Change this viewer&rsquo;s settings</summary>
          <SettingsPanel id={p.id} settings={s} onChange={p.onSettingsChange} clubs={clubs} players={players} />
        </details>
      </section>
    );
  }

  return (
    <div className="viewer full">
      <main className="viewer-main">
        {stage}
        {focus && <FocusStrip store={p.store} player={focus} lang={s.lang} />}
        <OverlayLog states={visible} settings={s} players={players} />
      </main>
      <div className="side-column">
        <AnalystPanel comments={comments} lang={s.lang} askUrl={p.askUrl} asOf={asOf} />
        <aside className="panel side" aria-label="Viewer settings">
          <h2>Make it yours</h2>
          <SettingsPanel id={p.id} settings={s} onChange={p.onSettingsChange} clubs={clubs} players={players} showLangMode={false} />
        </aside>
      </div>
    </div>
  );
}
