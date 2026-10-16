import type { ReactNode } from "react";

import { PITCH_LENGTH_M as L, PITCH_WIDTH_M as W } from "@/replay/pitch";

const BOX_DEPTH = 16.5;
const BOX_HALF = 20.16;
const SIX_DEPTH = 5.5;
const SIX_HALF = 9.16;
const GOAL_HALF = 3.66;
const CIRCLE_R = 9.15;
const SPOT = 11;
// Where the penalty arc meets the box edge: sqrt(9.15² - 5.5²).
const ARC_DY = Math.sqrt(CIRCLE_R ** 2 - (BOX_DEPTH - SPOT) ** 2);

/** A 105 × 68 m pitch in SVG; children are drawn in pitch meters. */
export function Pitch({ children }: { children?: ReactNode }) {
  const cy = W / 2;
  return (
    <svg
      viewBox={`-3 -3 ${L + 6} ${W + 6}`}
      className="w-full h-auto rounded-xl bg-emerald-800"
      role="img"
      aria-label="Pitch replay"
    >
      {Array.from({ length: 10 }, (_, i) => (
        <rect key={i} x={(i * L) / 10} y={0} width={L / 10} height={W} className={i % 2 ? "fill-emerald-700/40" : "fill-transparent"} />
      ))}
      <g className="fill-none stroke-white/70" strokeWidth={0.3}>
        <rect x={0} y={0} width={L} height={W} />
        <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
        <circle cx={L / 2} cy={cy} r={CIRCLE_R} />
        <rect x={0} y={cy - BOX_HALF} width={BOX_DEPTH} height={BOX_HALF * 2} />
        <rect x={L - BOX_DEPTH} y={cy - BOX_HALF} width={BOX_DEPTH} height={BOX_HALF * 2} />
        <rect x={0} y={cy - SIX_HALF} width={SIX_DEPTH} height={SIX_HALF * 2} />
        <rect x={L - SIX_DEPTH} y={cy - SIX_HALF} width={SIX_DEPTH} height={SIX_HALF * 2} />
        <path d={`M${BOX_DEPTH},${cy - ARC_DY} A${CIRCLE_R},${CIRCLE_R} 0 0 1 ${BOX_DEPTH},${cy + ARC_DY}`} />
        <path d={`M${L - BOX_DEPTH},${cy - ARC_DY} A${CIRCLE_R},${CIRCLE_R} 0 0 0 ${L - BOX_DEPTH},${cy + ARC_DY}`} />
        <rect x={-2} y={cy - GOAL_HALF} width={2} height={GOAL_HALF * 2} />
        <rect x={L} y={cy - GOAL_HALF} width={2} height={GOAL_HALF * 2} />
      </g>
      <g className="fill-white/70">
        <circle cx={L / 2} cy={cy} r={0.35} />
        <circle cx={SPOT} cy={cy} r={0.3} />
        <circle cx={L - SPOT} cy={cy} r={0.3} />
      </g>
      {children}
    </svg>
  );
}
