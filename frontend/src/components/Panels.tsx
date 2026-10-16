import { t } from '@/lib/i18n';
import { focusStats, formatClock, isFavoriteOverlay, type OverlayState } from '@/lib/logic';
import type { Club, Lang, MatchEvent, Player, ViewerSettings } from '@/lib/types';

export function ScoreBug({ clubs, score, clockMs }: { clubs: Club[]; score: [number, number]; clockMs: number }) {
  return (
    <div className="scorebug" aria-label={`${clubs[0].short_name} ${score[0]}, ${clubs[1].short_name} ${score[1]}, ${formatClock(clockMs)}`}>
      <span style={{ background: clubs[0].color, color: clubs[0].text_color }}>{clubs[0].short_name}</span>
      <span className="score">{score[0]} – {score[1]}</span>
      <span style={{ background: clubs[1].color, color: clubs[1].text_color }}>{clubs[1].short_name}</span>
      <span className="clock">{formatClock(clockMs)}</span>
    </div>
  );
}

export function FocusStrip({ store, player, lang }: { store: Map<string, MatchEvent>; player: Player; lang: Lang }) {
  const str = t(lang);
  const f = focusStats(store, player);
  const delta = f.avgSpeed !== null && f.norm !== null ? f.avgSpeed - f.norm : null;
  const norm = f.norm !== null ? Math.round(f.norm) : null;
  const name = lang === 'ja' ? player.display_name_ja : player.display_name;
  return (
    <section className="panel" lang={lang}>
      <div className="panel-head">
        <h2>{str.focusTitle} · #{player.shirt_number} {name}</h2>
        <span className="muted">{str.focusSub}</span>
      </div>
      <div className="tiles">
        <div className="tile">
          <span className="tile-label">{str.shotsTonight}</span>
          <span className="tile-value">{f.shots}</span>
          <span className="tile-note">{str.goals}: {f.goals}</span>
        </div>
        <div className="tile">
          <span className="tile-label">{str.avgSpeed}</span>
          <span className="tile-value">{f.avgSpeed !== null ? `${Math.round(f.avgSpeed)} km/h` : '—'}</span>
          <span className={`tile-note ${delta !== null && delta < 0 ? 'warn' : ''}`}>
            {delta === null ? str.noShots : `${Math.abs(Math.round(delta))} km/h ${delta < 0 ? str.below : str.above} (${str.norm} ${norm})`}
          </span>
        </div>
        <div className="tile">
          <span className="tile-label">{str.lastShot}</span>
          <span className="tile-value">{f.lastSpeed !== null ? `${Math.round(f.lastSpeed)} km/h` : '—'}</span>
          <span className="tile-note">{norm !== null ? `${str.norm} ${norm} km/h` : '—'}</span>
        </div>
      </div>
    </section>
  );
}

export function OverlayLog({ states, settings, players }: { states: OverlayState[]; settings: ViewerSettings; players: Player[] }) {
  const str = t(settings.lang);
  return (
    <section className="panel" lang={settings.lang}>
      <div className="panel-head">
        <h2>{str.log}</h2>
      </div>
      {states.length === 0 && <p className="muted">{str.logEmpty}</p>}
      <ul className="log">
        {[...states].reverse().map((st) => (
          <li key={st.overlay.overlay_id} className={st.retracted ? 'retracted' : ''}>
            <span className="log-clock">{formatClock(st.overlay.match_clock_ms)}</span>
            <span className="log-text">
              {isFavoriteOverlay(st.overlay, settings, players) ? '★ ' : ''}
              {st.overlay.slots.headline}
            </span>
            <span className={st.retracted ? 'log-status danger-text' : 'log-status ok-text'}>
              {st.retracted ? str.withdrawn : `✓ ${str.verified}`}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
