'use client';

import { useEffect, useMemo, useState } from 'react';
import { Viewer } from './Viewer';
import { applyEvents, applyOverlays, formatClock } from '@/lib/logic';
import { useLeague } from '@/lib/league';
import type { ViewerSettings } from '@/lib/types';
import { MOMENTS, useMatchStream } from '@/lib/useMatchStream';

type View = 'single' | 'two';

const SINGLE_DEFAULT: ViewerSettings = {
  lang: 'en',
  mode: 'casual',
  favoriteClubs: [],
  favoritePlayers: ['ply_0107', 'ply_0210'],
  focusPlayer: 'ply_0107',
  metric: 'all',
};

const VIEWER_A: ViewerSettings = {
  lang: 'ja',
  mode: 'casual',
  favoriteClubs: [],
  favoritePlayers: ['ply_0107'],
  focusPlayer: 'ply_0107',
  metric: 'all',
};

const VIEWER_B: ViewerSettings = {
  lang: 'en',
  mode: 'analyst',
  favoriteClubs: [],
  favoritePlayers: [],
  focusPlayer: null,
  metric: 'all',
};

export default function App() {
  const stream = useMatchStream();
  const league = useLeague();
  const [view, setView] = useState<View>('single');

  // `?view=two` opens the two-viewer page directly (screenshots, demo recording).
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('view') === 'two') setView('two');
  }, []);
  const [single, setSingle] = useState(SINGLE_DEFAULT);
  const [a, setA] = useState(VIEWER_A);
  const [b, setB] = useState(VIEWER_B);

  const store = useMemo(() => applyEvents(stream.events), [stream.events]);
  const overlayStates = useMemo(() => applyOverlays(stream.overlays), [stream.overlays]);

  const shared = { clockMs: stream.clockMs, store, overlayStates, clubs: league.clubs, players: league.players, frame: stream.frame };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="wordmark">formline</span>
          <span className="muted">Live personal-baseline insights · synthetic data</span>
        </div>

        <nav className="tabs" aria-label="Views">
          <button type="button" aria-pressed={view === 'single'} onClick={() => setView('single')}>Live viewer</button>
          <button type="button" aria-pressed={view === 'two'} onClick={() => setView('two')}>Two viewers</button>
        </nav>

        <div className="controls">
          {league.status !== 'ready' && (
            <span className={`source ${league.status === 'error' ? 'off' : ''}`}>
              {league.status === 'loading' ? 'Loading squads…' : 'Squads unavailable'}
            </span>
          )}
          <span className={`source ${stream.connected ? 'on' : 'off'}`}>
            {stream.source === 'mock' ? 'Mock replay' : stream.ended ? 'Full time' : stream.connected ? 'Live feed' : 'Reconnecting…'}
          </span>
          <span className="clock-big">{formatClock(stream.clockMs)}</span>
          <button type="button" className="ctl" onClick={() => stream.setPlaying(!stream.playing)}>
            {stream.playing ? 'Pause' : 'Play'}
          </button>
          <button type="button" className="ctl" onClick={stream.restart}>Restart</button>
          {stream.source === 'sse' && (
            <label className="speed">
              <span>Jump to</span>
              <select value="" onChange={(e) => { const m = MOMENTS[Number(e.target.value)]; if (m) stream.jumpTo(m.at); }}>
                <option value="" disabled>Key moment…</option>
                {MOMENTS.map((m, i) => (
                  <option key={m.label} value={i}>{m.label}</option>
                ))}
              </select>
            </label>
          )}
          <label className="speed">
            <span>Speed</span>
            <select value={stream.speed} onChange={(e) => stream.setSpeed(Number(e.target.value))}>
              {stream.speedOptions.map((v) => (
                <option key={v} value={v}>{v}×</option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {view === 'single' ? (
        <Viewer id="single" layout="full" settings={single} onSettingsChange={setSingle} {...shared} />
      ) : (
        <div className="two-up">
          <p className="two-up-intro muted">
            Same match, same engine output. Each viewer&rsquo;s settings decide which insights appear and how they read.
          </p>
          <div className="two-up-grid">
            <Viewer id="viewer-a" title="Viewer A" layout="compact" settings={a} onSettingsChange={setA} {...shared} />
            <Viewer id="viewer-b" title="Viewer B" layout="compact" settings={b} onSettingsChange={setB} {...shared} />
          </div>
        </div>
      )}
    </div>
  );
}
