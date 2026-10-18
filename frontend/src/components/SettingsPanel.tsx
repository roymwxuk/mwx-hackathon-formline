import type { Club, MetricChoice, Player, ViewerSettings } from '@/lib/types';

interface Props {
  id: string; // unique prefix for form ids when two panels are on screen
  settings: ViewerSettings;
  onChange: (s: ViewerSettings) => void;
  clubs: Club[];
  players: Player[];
  /** False when the language and mode switches sit in the page header instead. */
  showLangMode?: boolean;
}

const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

export function SettingsPanel({ id, settings: s, onChange, clubs, players, showLangMode = true }: Props) {
  const set = (patch: Partial<ViewerSettings>) => onChange({ ...s, ...patch });

  return (
    <div className="settings">
      {showLangMode && (
        <>
          <div className="field">
            <span className="field-label" id={`${id}-lang`}>Language</span>
            <div className="segmented" role="group" aria-labelledby={`${id}-lang`}>
              <button type="button" aria-pressed={s.lang === 'en'} onClick={() => set({ lang: 'en' })}>English</button>
              <button type="button" aria-pressed={s.lang === 'ja'} onClick={() => set({ lang: 'ja' })} lang="ja">日本語</button>
            </div>
          </div>

          <div className="field">
            <span className="field-label" id={`${id}-mode`}>Mode</span>
            <div className="segmented" role="group" aria-labelledby={`${id}-mode`}>
              <button type="button" aria-pressed={s.mode === 'casual'} onClick={() => set({ mode: 'casual' })}>Casual</button>
              <button type="button" aria-pressed={s.mode === 'analyst'} onClick={() => set({ mode: 'analyst' })}>Analyst</button>
            </div>
            <span className="field-hint">Casual: fewer cards, only your favorites. Analyst: every insight with full numbers.</span>
          </div>
        </>
      )}

      <div className="field">
        <span className="field-label" id={`${id}-clubs`}>Favorite clubs</span>
        <div className="chip-row" role="group" aria-labelledby={`${id}-clubs`}>
          {clubs.map((c) => (
            <button
              key={c.club_id}
              type="button"
              className="chip"
              aria-pressed={s.favoriteClubs.includes(c.club_id)}
              onClick={() => set({ favoriteClubs: toggle(s.favoriteClubs, c.club_id) })}
            >
              {s.favoriteClubs.includes(c.club_id) ? '✓ ' : ''}
              {c.name}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <span className="field-label" id={`${id}-players`}>Favorite players</span>
        <div role="group" aria-labelledby={`${id}-players`} className="club-groups">
          {clubs.map((c) => (
            <div key={c.club_id} className="club-group">
              <span className="club-group-label">{c.name}</span>
              <div className="chip-row">
                {players
                  .filter((p) => p.club_id === c.club_id)
                  .map((p) => (
                    <button
                      key={p.player_id}
                      type="button"
                      className="chip"
                      aria-pressed={s.favoritePlayers.includes(p.player_id)}
                      onClick={() => set({ favoritePlayers: toggle(s.favoritePlayers, p.player_id) })}
                    >
                      {s.favoritePlayers.includes(p.player_id) ? '✓ ' : ''}
                      <span className="chip-number">{p.shirt_number}</span>
                      {p.display_name}
                    </button>
                  ))}
              </div>
            </div>
          ))}
        </div>
        <span className="field-hint">Favorites get first claim on overlay slots.</span>
      </div>

      <div className="field">
        <label className="field-label" htmlFor={`${id}-focus`}>Player focus mode</label>
        <select
          id={`${id}-focus`}
          value={s.focusPlayer ?? ''}
          onChange={(e) => set({ focusPlayer: e.target.value || null })}
        >
          <option value="">Off</option>
          {clubs.map((c) => (
            <optgroup key={c.club_id} label={c.name}>
              {players
                .filter((p) => p.club_id === c.club_id && p.season_shot_speed_norm_kmh !== null)
                .map((p) => (
                  <option key={p.player_id} value={p.player_id}>
                    #{p.shirt_number} {p.display_name}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </div>

      <fieldset className="field">
        <legend className="field-label">My metric</legend>
        {(
          [
            ['shot_speed', 'Shot speed vs his norm'],
            ['finishing', 'Finishing quality vs his norm'],
            ['all', 'All insights'],
          ] as [MetricChoice, string][]
        ).map(([value, label]) => (
          <label key={value} className="radio">
            <input type="radio" name={`${id}-metric`} checked={s.metric === value} onChange={() => set({ metric: value })} />
            {label}
          </label>
        ))}
      </fieldset>
    </div>
  );
}

/** Language and mode as compact header switches (the single viewer's top bar). */
export function LangModeSwitch({ settings: s, onChange }: { settings: ViewerSettings; onChange: (s: ViewerSettings) => void }) {
  const set = (patch: Partial<ViewerSettings>) => onChange({ ...s, ...patch });
  return (
    <>
      <div className="tabs" role="group" aria-label="Language">
        <button type="button" aria-pressed={s.lang === 'en'} onClick={() => set({ lang: 'en' })}>English</button>
        <button type="button" aria-pressed={s.lang === 'ja'} onClick={() => set({ lang: 'ja' })} lang="ja">日本語</button>
      </div>
      <div className="tabs" role="group" aria-label="Mode">
        <button type="button" aria-pressed={s.mode === 'casual'} onClick={() => set({ mode: 'casual' })}
          title="Fewer cards, only your favorites">Casual</button>
        <button type="button" aria-pressed={s.mode === 'analyst'} onClick={() => set({ mode: 'analyst' })}
          title="Every insight with full numbers">Analyst</button>
      </div>
    </>
  );
}
