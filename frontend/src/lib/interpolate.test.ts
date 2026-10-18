import { describe, expect, it } from 'vitest';
import { FrameInterpolator } from '@/lib/interpolate';
import type { TrackingFrameMessage } from '@/lib/types';

const frame = (t: number, x: number, ballZ = 0): TrackingFrameMessage =>
  ({ kind: 'frame', p: 1, t, b: [x, 50, ballZ], h: [[9, x, 40]], a: [[4, 100 - x, 60]] });

describe('FrameInterpolator', () => {
  it('shows the first frame as is', () => {
    const f = new FrameInterpolator();
    f.set(frame(0, 10), 1000);
    expect(f.at(1000).get('h9')).toEqual({ x: 10, y: 40 });
  });

  it('blends to each new frame over the time since the last one', () => {
    const f = new FrameInterpolator();
    f.set(frame(0, 10), 1000);
    f.set(frame(1000, 20), 1250); // arrived 250 ms later: blend over 250 ms
    expect(f.at(1250).get('h9')!.x).toBeCloseTo(10);
    expect(f.at(1375).get('h9')!.x).toBeCloseTo(15);
    expect(f.at(1500).get('h9')!.x).toBeCloseTo(20);
    expect(f.at(2000).get('h9')!.x).toBeCloseTo(20); // then holds
    expect(f.at(1375).get('a4')!.x).toBeCloseTo(85);
  });

  it('never jumps back when a frame comes early: it starts from where things are drawn', () => {
    const f = new FrameInterpolator();
    f.set(frame(0, 10), 1000);
    f.set(frame(1000, 20), 1250);
    const drawn = f.at(1350).get('h9')!.x; // 40% of the way: 14
    f.set(frame(2000, 30), 1350); // early frame interrupts the blend
    expect(f.at(1350).get('h9')!.x).toBeCloseTo(drawn);
    expect(f.at(1400).get('h9')!.x).toBeGreaterThan(drawn);
  });

  it('interpolates the ball height and can be instant (reduced motion)', () => {
    const f = new FrameInterpolator();
    f.set(frame(0, 10, 0), 0);
    f.set(frame(1000, 20, 4), 250);
    expect(f.at(375).get('ball')!.z).toBeCloseTo(2);
    const instant = new FrameInterpolator(true);
    instant.set(frame(0, 10), 0);
    instant.set(frame(1000, 20), 250);
    expect(instant.at(250).get('h9')!.x).toBe(20);
  });

  it('reports the current movement for the direction arrow', () => {
    const f = new FrameInterpolator();
    f.set(frame(0, 10), 0);
    f.set(frame(1000, 20), 250); // 10 units in 0.25 s
    expect(f.velocity('h9').vx).toBeCloseTo(40);
    expect(f.velocity('h9').vy).toBeCloseTo(0);
    expect(f.velocity('nobody')).toEqual({ vx: 0, vy: 0 });
  });

  it('a substitute appears at his own spot rather than flying in', () => {
    const f = new FrameInterpolator();
    f.set(frame(0, 10), 0);
    f.set({ ...frame(1000, 20), h: [[9, 20, 40], [15, 30, 30]] }, 250);
    expect(f.at(300).get('h15')).toEqual({ x: 30, y: 30 });
  });
});
