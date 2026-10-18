import { useEffect, useRef, useState } from 'react';
import { freshRestart, type RestartType } from '@/lib/goal';
import { t } from '@/lib/i18n';
import type { Lang, MatchEvent } from '@/lib/types';

const SHOW_MS = 1_800; // real time, whatever the playback speed

/** A small label at the top of the pitch when play restarts: throw-in, corner, goal kick… */
export function RestartTag({ events, clockMs, lang, paused = false }: { events: MatchEvent[]; clockMs: number; lang: Lang; paused?: boolean }) {
  const shown = useRef(new Set<string>());
  const [restart, setRestart] = useState<MatchEvent | null>(null);

  const fresh = paused ? undefined : freshRestart(events, clockMs, shown.current);
  useEffect(() => {
    if (!fresh) return;
    shown.current.add(fresh.event_id);
    setRestart(fresh);
  }, [fresh]);
  useEffect(() => { // hide after SHOW_MS; separate, so the next render does not cancel it
    if (!restart) return;
    const timer = setTimeout(() => setRestart(null), SHOW_MS);
    return () => clearTimeout(timer);
  }, [restart]);

  if (!restart?.pass_type) return null;
  return (
    <div key={restart.event_id} className="restart-tag" role="status" lang={lang}>
      {t(lang).restart[restart.pass_type as RestartType]}
    </div>
  );
}
