"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const REPLAY_SPEEDS = [1, 2, 4, 8] as const;
export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number];

/** Match clock in milliseconds, advanced by requestAnimationFrame at `speed`× real time. */
export function useReplayClock(range: { startMs: number; endMs: number }, initialSpeed: ReplaySpeed = 4) {
  const [clockMs, setClockMs] = useState(range.startMs);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(initialSpeed);
  const clockRef = useRef(range.startMs);

  const seek = useCallback(
    (ms: number) => {
      const clamped = Math.min(range.endMs, Math.max(range.startMs, ms));
      clockRef.current = clamped;
      setClockMs(clamped);
    },
    [range.startMs, range.endMs],
  );

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const next = Math.min(range.endMs, clockRef.current + (now - last) * speed);
      last = now;
      clockRef.current = next;
      setClockMs(next);
      if (next >= range.endMs) {
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, range.endMs]);

  const togglePlay = useCallback(() => {
    if (!playing && clockRef.current >= range.endMs) seek(range.startMs);
    setPlaying((p) => !p);
  }, [playing, range.endMs, range.startMs, seek]);

  return { clockMs, playing, speed, setSpeed, togglePlay, seek };
}
