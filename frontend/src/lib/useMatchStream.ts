import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildDemoStream, MATCH_END_MS } from '@/mock/demo-match';
import { formatClock, timeAfter, type MatchTime } from '@/lib/logic';
import type { MatchEvent, Overlay, StreamMessage } from '@/lib/types';

export type StreamSource = 'mock' | 'sse';

export interface MatchStream {
  source: StreamSource;
  clockMs: number;
  events: MatchEvent[];
  overlays: Overlay[];
  playing: boolean;
  speed: number;
  /** Speed choices for the header (live and mock replay differ). */
  speedOptions: number[];
  connected: boolean;
  /** Live mode: the backend sent its final message (full time). */
  ended: boolean;
  setPlaying: (p: boolean) => void;
  setSpeed: (s: number) => void;
  restart: () => void;
}

const SSE_URL: string | undefined = process.env.NEXT_PUBLIC_STREAM_URL;
const LIVE_SPEEDS = [10, 20, 60, 120];
const MOCK_SPEEDS = [30, 60, 120];
const HALF_MS = 45 * 60_000;

/**
 * The backend stream URL for a speed and a resume point. `start` asks the backend to send
 * everything before that match time at once and play on from there. The backend reads
 * minutes above 45 as the second half, so first-half stoppage time is capped at 45:00 and
 * second-half times are kept above it.
 */
export function liveStreamUrl(base: string, speed: number, start: MatchTime | null): string {
  const url = new URL(base);
  url.searchParams.set('speed', String(speed));
  url.searchParams.delete('start');
  if (start && (start.period > 1 || start.clockMs > 0)) {
    const ms = start.period === 1 ? Math.min(start.clockMs, HALF_MS) : Math.max(start.clockMs, HALF_MS + 1000);
    url.searchParams.set('start', formatClock(ms));
  }
  return url.toString();
}

/** Default live speed: the stream URL's own `speed`, else 20. */
export function initialLiveSpeed(base: string): number {
  const speed = Number(new URL(base).searchParams.get('speed'));
  return Number.isFinite(speed) && speed > 0 ? speed : 20;
}

/** Identity of a message, to ignore what a reconnect sends again. */
function messageKey(msg: StreamMessage): string {
  if (msg.kind === 'event') return `e:${msg.event.event_id}:${msg.event.version}`;
  if (msg.kind === 'overlay') return `o:${msg.overlay.overlay_id}`;
  return 'end';
}
const TICK_MS = 100;
const SLOW_SPEED = 2;

/**
 * One shared live stream for every viewer on the page.
 * - With NEXT_PUBLIC_STREAM_URL set, it listens to the backend over Server-Sent Events.
 *   Each SSE `data:` line is one StreamMessage as JSON.
 * - Without it, it replays the built-in mock match at an accelerated speed.
 */
export function useMatchStream(): MatchStream {
  const source: StreamSource = SSE_URL ? 'sse' : 'mock';
  const demo = useMemo(() => (source === 'mock' ? buildDemoStream() : []), [source]);
  const keyClocks = useMemo(
    () => demo.filter((d) => d.msg.kind === 'overlay' || (d.msg.kind === 'event' && (d.msg.event.type === 'shot' || d.msg.event.type.startsWith('var')))).map((d) => d.clock),
    [demo],
  );

  const [clockMs, setClockMs] = useState(0);
  const [playing, setPlayingState] = useState(true);
  const [speed, setSpeedState] = useState(() => (SSE_URL ? initialLiveSpeed(SSE_URL) : 60));
  const [connectKey, setConnectKey] = useState(0);
  const timeRef = useRef<MatchTime>({ period: 1, clockMs: 0 });
  const startRef = useRef<MatchTime | null>(null);
  const seenRef = useRef<Set<string>>(new Set());
  const [received, setReceived] = useState<StreamMessage[]>([]);
  const [connected, setConnected] = useState(source === 'mock');
  const [ended, setEnded] = useState(false);
  const cursor = useRef(0);
  const clockRef = useRef(0);

  // ----- Mock replay -----
  useEffect(() => {
    if (source !== 'mock' || !playing) return;
    const id = window.setInterval(() => {
      // Broadcast pacing: slow down around key moments so viewers can read the overlays.
      const nearKey = keyClocks.some((k) => clockRef.current > k - 4000 && clockRef.current < k + 14000);
      const effective = nearKey ? Math.min(speed, SLOW_SPEED) : speed;
      const next = Math.min(clockRef.current + TICK_MS * effective, MATCH_END_MS);
      clockRef.current = next;
      const batch: StreamMessage[] = [];
      while (cursor.current < demo.length && demo[cursor.current].clock <= next) {
        batch.push(demo[cursor.current].msg);
        cursor.current += 1;
      }
      if (batch.length) setReceived((r) => [...r, ...batch]);
      setClockMs(next);
      if (next >= MATCH_END_MS) setPlayingState(false);
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [source, playing, speed, demo, keyClocks]);

  // ----- Live SSE -----
  // Speed, pause/play and restart reconnect with `speed=` and `start=` (the current match
  // time). Messages already received are ignored, so a reconnect never duplicates cards.
  useEffect(() => {
    if (source !== 'sse' || !SSE_URL || !playing) return;
    const es = new EventSource(liveStreamUrl(SSE_URL, speed, startRef.current));
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource reconnects and resumes after its last id
    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as StreamMessage;
        if (msg.kind === 'end') {
          es.close(); // full time: don't let EventSource reconnect and replay the match
          setEnded(true);
          setPlayingState(false);
          return;
        }
        if (msg.kind !== 'clock' && msg.kind !== 'frame') {  // these only move the time here
          const key = messageKey(msg);
          if (seenRef.current.has(key)) return;
          seenRef.current.add(key);
          setReceived((r) => [...r, msg]);
        }
        timeRef.current = timeAfter(timeRef.current, msg);
        setClockMs(timeRef.current.clockMs);
      } catch {
        // Ignore malformed messages rather than breaking the viewer.
      }
    };
    return () => es.close();
  }, [source, playing, speed, connectKey]);

  const liveRestart = useCallback(() => {
    timeRef.current = { period: 1, clockMs: 0 };
    startRef.current = null;
    seenRef.current = new Set();
    setReceived([]);
    setClockMs(0);
    setEnded(false);
    setPlayingState(true);
    setConnectKey((k) => k + 1);
  }, []);

  /** Mock only: jump to a match time, delivering everything up to it at once. */
  const seek = useCallback(
    (ms: number) => {
      let i = 0;
      while (i < demo.length && demo[i].clock <= ms) i += 1;
      cursor.current = i;
      clockRef.current = ms;
      setReceived(demo.slice(0, i).map((d) => d.msg));
      setClockMs(ms);
      setPlayingState(true);
    },
    [demo],
  );

  const restart = useCallback(() => (source === 'sse' ? liveRestart() : seek(0)), [source, liveRestart, seek]);

  const setSpeed = useCallback((value: number) => {
    if (source === 'sse') startRef.current = timeRef.current; // resume from here at the new speed
    setSpeedState(value);
  }, [source]);

  const setPlaying = useCallback((value: boolean) => {
    if (source === 'sse' && value) {
      if (ended) return liveRestart(); // after full time, Play starts the match again
      startRef.current = timeRef.current; // resume where we paused
    }
    setPlayingState(value);
  }, [source, ended, liveRestart]);

  // `?t=mm:ss` opens the mock replay at that moment, for screenshots and the demo video.
  useEffect(() => {
    if (source !== 'mock') return;
    const t = new URLSearchParams(window.location.search).get('t')?.match(/^(\d+):(\d{2})$/);
    if (t) seek(Math.min((Number(t[1]) * 60 + Number(t[2])) * 1000, MATCH_END_MS));
  }, [source, seek]);

  const events = useMemo(
    () => received.flatMap((m) => (m.kind === 'event' ? [m.event] : [])),
    [received],
  );
  const overlays = useMemo(
    () => received.flatMap((m) => (m.kind === 'overlay' ? [m.overlay] : [])),
    [received],
  );

  const speedOptions = source === 'sse' ? LIVE_SPEEDS : MOCK_SPEEDS;

  return { source, clockMs, events, overlays, playing, speed, speedOptions, connected, ended, setPlaying, setSpeed, restart };
}
