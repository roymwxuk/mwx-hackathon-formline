import type { TrackingFrameMessage } from '@/lib/types';

/** A drawn position in pitch percentages; `z` is the ball's height in meters. */
export interface Pos {
  x: number;
  y: number;
  z?: number;
}

const MIN_MS = 100;
const MAX_MS = 500;
const DEFAULT_MS = 250; // frames arrive about every 0.25 s

/**
 * Smooth motion between tracking frames, computed in JavaScript rather than with CSS
 * transitions (which Firefox restarts from a stale position on SVG elements, so every
 * marker stuttered backwards). Each new frame starts a blend from where everything is
 * *drawn now* to the new frame, over the time since the previous frame arrived, so motion
 * stays continuous even when frames come early or late.
 */
export class FrameInterpolator {
  private from = new Map<string, Pos>();
  private to = new Map<string, Pos>();
  private start = 0;
  private duration = DEFAULT_MS;
  private lastArrival: number | null = null;

  constructor(private readonly instant = false) {}

  set(frame: TrackingFrameMessage, now: number): void {
    const target = framePositions(frame);
    this.from = this.lastArrival === null ? target : this.at(now);
    this.to = target;
    this.duration = this.lastArrival === null ? DEFAULT_MS
      : Math.min(MAX_MS, Math.max(MIN_MS, now - this.lastArrival));
    this.start = now;
    this.lastArrival = now;
  }

  /** Every marker's position at `now` (players by 'h7'/'a1', the ball as 'ball'). */
  at(now: number): Map<string, Pos> {
    const u = this.instant ? 1 : Math.min(1, Math.max(0, (now - this.start) / this.duration));
    const out = new Map<string, Pos>();
    for (const [key, b] of this.to) {
      const a = this.from.get(key) ?? b; // a player who just came on starts at his spot
      out.set(key, {
        x: a.x + (b.x - a.x) * u,
        y: a.y + (b.y - a.y) * u,
        ...(b.z !== undefined ? { z: (a.z ?? 0) + (b.z - (a.z ?? 0)) * u } : {}),
      });
    }
    return out;
  }

  /** Movement of one marker in the current blend, in pitch percentages per second (the
   *  direction and speed it is moving now); zero when it is not moving. */
  velocity(key: string): { vx: number; vy: number } {
    const a = this.from.get(key);
    const b = this.to.get(key);
    if (!a || !b || this.instant) return { vx: 0, vy: 0 };
    const secs = this.duration / 1000;
    return { vx: (b.x - a.x) / secs, vy: (b.y - a.y) / secs };
  }

  reset(): void {
    this.from = new Map();
    this.to = new Map();
    this.lastArrival = null;
  }
}

export function framePositions(frame: TrackingFrameMessage): Map<string, Pos> {
  const out = new Map<string, Pos>();
  for (const [shirt, x, y] of frame.h) out.set(`h${shirt}`, { x, y });
  for (const [shirt, x, y] of frame.a) out.set(`a${shirt}`, { x, y });
  out.set('ball', { x: frame.b[0], y: frame.b[1], z: frame.b[2] });
  return out;
}
