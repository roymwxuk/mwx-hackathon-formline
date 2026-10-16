import type { Club, MetricChoice, Player, ViewerSettings } from '@/lib/types';

interface Props {
  id: string; // unique prefix for form ids when two panels are on screen
  settings: ViewerSettings;
  onChange: (s: ViewerSettings) => void;
  clubs: Club[];
  players: Player[];
}

const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

export function SettingsPanel({ id, settings: s, onChange, clubs, players }: Props) {
  const set = (patch: Partial<ViewerSettings>) => onChange({ ...s, ...patch });

  return (
    <div className="settings">
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
        <div className="chip-row" role="group" aria-labelledby={`${id}-players`}>
          {players.map((p) => (
            <button
              key={p.player_id}
              type="button"
              className="chip"
              aria-pressed={s.favoritePlayers.includes(p.player_id)}
              onClick={() => set({ favoritePlayers: toggle(s.favoritePlayers, p.player_id) })}
            >
              {s.favoritePlayers.includes(p.player_id) ? '✓ ' : ''}
              {p.display_name}
            </button>
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
          {players.map((p) => (
            <option key={p.player_id} value={p.player_id}>
              #{p.shirt_number} {p.display_name}
            </option>
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
