import { useEffect, useRef, useState } from 'react';
import { freshGoal } from '@/lib/goal';
import { t } from '@/lib/i18n';
import type { Club, Lang, MatchEvent, Player } from '@/lib/types';

const SHOW_MS = 2_500; // real time, whatever the playback speed

interface Props {
  events: MatchEvent[]; // event-time order, latest versions
  clockMs: number;
  clubs: Club[];
  players: Player[];
  lang: Lang;
  /** No flash while the stream replays the past at once (a jump or reconnect). */
  paused?: boolean;
}

/** A short "GOAL!" over the pitch when a goal is scored, in the scoring club's colours. */
export function GoalFlash({ events, clockMs, clubs, players, lang, paused = false }: Props) {
  const flashed = useRef(new Set<string>());
  const [goal, setGoal] = useState<MatchEvent | null>(null);

  const fresh = paused ? undefined : freshGoal(events, clockMs, flashed.current);
  useEffect(() => {
    if (!fresh) return;
    flashed.current.add(fresh.event_id);
    setGoal(fresh);
  }, [fresh]);
  useEffect(() => { // hide after SHOW_MS; separate, so the next render does not cancel it
    if (!goal) return;
    const timer = setTimeout(() => setGoal(null), SHOW_MS);
    return () => clearTimeout(timer);
  }, [goal]);

  if (!goal) return null;
  const club = clubs.find((c) => c.club_id === goal.team_id);
  const scorer = players.find((p) => p.player_id === goal.player_id);
  const name = scorer ? (lang === 'ja' ? scorer.display_name_ja : scorer.display_name.split(' ').slice(-1)[0]) : '';
  const minute = Math.floor(goal.match_clock_ms / 60_000) + 1;
  return (
    <div className="goal-flash" role="status" aria-live="assertive" lang={lang}>
      <div className="goal-word" style={{ background: club?.color, color: club?.text_color }}>{t(lang).goal}</div>
      {name && <div className="goal-scorer">{name} · {minute}&prime;</div>}
    </div>
  );
}
