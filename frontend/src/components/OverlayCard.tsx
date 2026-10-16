import { t } from '@/lib/i18n';
import type { OverlayState } from '@/lib/logic';

interface Props {
  state: OverlayState;
  favorite: boolean;
}

export function OverlayCard({ state, favorite }: Props) {
  const { overlay: o, retracted } = state;
  const s = o.slots;
  const str = t(o.lang);
  const max = Math.max(...(s.bars ?? []).map((b) => b.value), 1) * 1.15;

  return (
    <article
      className={`overlay-card ${o.audience_mode} ${retracted ? 'retracted' : ''}`}
      lang={o.lang}
      aria-live="polite"
    >
      <div className="overlay-tagline">
        {retracted ? <span className="badge danger">{str.withdrawn}</span> : <span className="overlay-tag">{s.tag}</span>}
        {favorite && !retracted && <span className="badge fav">★ {str.favorite}</span>}
      </div>
      <h3 className="overlay-headline">{s.headline}</h3>

      {!retracted && s.bars && (
        <div className="bars">
          {s.bars.map((b) => (
            <div className="bar-row" key={b.label}>
              <span className="bar-label">{b.label}</span>
              <div className="bar-track">
                <div className={`bar-fill ${b.highlight ? 'hi' : ''}`} style={{ width: `${(b.value / max) * 100}%` }} />
              </div>
              <span className="bar-value">{b.display}</span>
            </div>
          ))}
        </div>
      )}

      {!retracted && s.rows && (
        <dl className="rows">
          {s.rows.map((r) => (
            <div className="row" key={r.label}>
              <dt>{r.label}</dt>
              <dd>{r.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {retracted ? <p className="overlay-sub">{str.withdrawnNote}</p> : s.sub && <p className="overlay-sub">{s.sub}</p>}

      <div className="chips">
        {o.verified && !retracted && <span className="badge ok">✓ {str.verified}</span>}
        <span className="badge plain">
          {str.source}: {o.source_event_ids.join(', ')}
        </span>
      </div>
    </article>
  );
}

export function CorrectionBanner({ state }: { state: OverlayState }) {
  const s = state.overlay.slots;
  return (
    <div className="correction" role="status" lang={state.overlay.lang}>
      <span className="correction-tag">{s.tag}</span>
      <span className="correction-headline">{s.headline}</span>
      {s.sub && <span className="correction-sub">{s.sub}</span>}
    </div>
  );
}
