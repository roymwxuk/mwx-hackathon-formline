import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildDemoStream, MATCH_END_MS } from '@/mock/demo-match';
import { advanceTime, type MatchTime } from '@/lib/logic';
import type { MatchEvent, Overlay, StreamMessage } from '@/lib/types';

export type StreamSource = 'mock' | 'sse';

export interface MatchStream {
  source: StreamSource;
  clockMs: number;
  events: MatchEvent[];
  overlays: Overlay[];
  playing: boolean;
  speed: number;
  connected: boolean;
  /** Live mode: the backend sent its final message (full time). */
  ended: boolean;
  setPlaying: (p: boolean) => void;
  setSpeed: (s: number) => void;
  restart: () => void;
}

const SSE_URL: string | undefined = process.env.NEXT_PUBLIC_STREAM_URL;
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
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(60);
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
      if (next >= MATCH_END_MS) setPlaying(false);
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [source, playing, speed, demo, keyClocks]);

  // ----- Live SSE -----
  useEffect(() => {
    if (source !== 'sse' || !SSE_URL) return;
    let time: MatchTime = { period: 1, clockMs: 0 };
    const es = new EventSource(SSE_URL);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource reconnects by itself
    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as StreamMessage;
        if (msg.kind === 'end') {
          es.close(); // full time: don't let EventSource reconnect and replay the match
          setEnded(true);
          return;
        }
        setReceived((r) => [...r, msg]);
        time = msg.kind === 'event'
          ? advanceTime(time, msg.event.period, msg.event.match_clock_ms)
          : advanceTime(time, undefined, msg.overlay.match_clock_ms);
        setClockMs(time.clockMs);
      } catch {
        // Ignore malformed messages rather than breaking the viewer.
      }
    };
    return () => es.close();
  }, [source]);

  /** Mock only: jump to a match time, delivering everything up to it at once. */
  const seek = useCallback(
    (ms: number) => {
      let i = 0;
      while (i < demo.length && demo[i].clock <= ms) i += 1;
      cursor.current = i;
      clockRef.current = ms;
      setReceived(demo.slice(0, i).map((d) => d.msg));
      setClockMs(ms);
      setPlaying(true);
    },
    [demo],
  );

  const restart = useCallback(() => seek(0), [seek]);

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

  return { source, clockMs, events, overlays, playing, speed, connected, ended, setPlaying, setSpeed, restart };
}
