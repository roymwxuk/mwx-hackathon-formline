import { useEffect, useState } from 'react';
import { CLUBS, PLAYERS } from '@/mock/demo-match';
import type { Club, Player } from './types';

const SSE_URL: string | undefined = process.env.NEXT_PUBLIC_STREAM_URL;

/** `/matches/{id}/stream?speed=20` → `/matches/{id}/league` on the same server. */
export function leagueUrlFromStream(streamUrl: string): string {
  const url = new URL(streamUrl);
  url.pathname = url.pathname.replace(/\/stream\/?$/, '/league');
  url.search = '';
  return url.toString();
}

export interface League {
  clubs: Club[]; // home first
  players: Player[];
  status: 'ready' | 'loading' | 'error';
}

const MOCK: League = { clubs: CLUBS, players: PLAYERS, status: 'ready' };

/** Clubs and squads: the mock in mock mode, the backend's league endpoint in live mode. */
export function useLeague(): League {
  const [league, setLeague] = useState<League>(
    SSE_URL ? { clubs: CLUBS, players: PLAYERS, status: 'loading' } : MOCK,
  );

  useEffect(() => {
    if (!SSE_URL) return;
    let cancelled = false;
    fetch(leagueUrlFromStream(SSE_URL))
      .then((r) => {
        if (!r.ok) throw new Error(`league ${r.status}`);
        return r.json() as Promise<{ clubs: Club[]; players: Player[] }>;
      })
      .then((body) => {
        if (!cancelled) setLeague({ clubs: body.clubs, players: body.players, status: 'ready' });
      })
      .catch(() => {
        // Keep the mock squads so the viewer still renders; the header shows the error.
        if (!cancelled) setLeague((l) => ({ ...l, status: 'error' }));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return league;
}
