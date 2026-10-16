import type { ClubId, MatchEvent, PassEvent, PlayerId, ShotEvent } from "@/contract";
import { ballState, PITCH_LENGTH_M, toPitch } from "@/replay/pitch";

const TRAIL_LENGTH = 4;
const TAG_HALF_WIDTH = 6;

interface Props {
  events: MatchEvent[];
  clockMs: number;
  homeClubId: ClubId;
  overturned: Set<string>;
  colorOf: (clubId: ClubId) => string;
  nameOf: (id: PlayerId | null) => string;
}

/** Everything that moves: pass trails, shot markers, the ball and its name tag. */
export function PitchLayer({ events, clockMs, homeClubId, overturned, colorOf, nameOf }: Props) {
  const past = events.filter((e) => e.match_clock_ms <= clockMs);
  const trail = past.filter((e): e is PassEvent => e.type === "pass").slice(-TRAIL_LENGTH);
  const shots = past.filter((e): e is ShotEvent => e.type === "shot");
  const ball = ballState(events, clockMs, homeClubId);
  const pt = (e: MatchEvent, x: number, y: number) => toPitch(e.team_id, homeClubId, x, y);
  // Keep the name tag on the pitch when the ball is at a goal line.
  const tagX = ball
    ? Math.min(PITCH_LENGTH_M - TAG_HALF_WIDTH, Math.max(TAG_HALF_WIDTH, ball.position.x))
    : 0;

  return (
    <g>
      {trail.map((p, i) => {
        const a = pt(p, p.x, p.y);
        const b = pt(p, p.end_x, p.end_y);
        return (
          <line
            key={p.event_id}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke={colorOf(p.team_id)}
            strokeWidth={0.5}
            strokeLinecap="round"
            opacity={(i + 1) / (TRAIL_LENGTH + 1)}
          />
        );
      })}

      {shots.map((s) => {
        const a = pt(s, s.x, s.y);
        const b = pt(s, s.end_x, s.end_y);
        const color = colorOf(s.team_id);
        return (
          <g key={s.event_id}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={color} strokeWidth={0.25} strokeDasharray="0.8 0.6" opacity={0.7} />
            <ShotMarker x={a.x} y={a.y} color={color} outcome={s.outcome} overturned={overturned.has(s.event_id)} />
          </g>
        );
      })}

      {ball && (
        <g>
          {ball.playerId && (
            <g opacity={ball.inFlight ? 0.55 : 1}>
              <rect x={tagX - TAG_HALF_WIDTH} y={ball.position.y - 5.6} width={TAG_HALF_WIDTH * 2} height={3.2} rx={0.8} fill={colorOf(ball.teamId)} />
              <text x={tagX} y={ball.position.y - 3.4} textAnchor="middle" fontSize={2.1} fontWeight={600} className="fill-white">
                {nameOf(ball.playerId)}
              </text>
            </g>
          )}
          <circle cx={ball.position.x} cy={ball.position.y} r={0.9} className="fill-white stroke-slate-900" strokeWidth={0.25} />
        </g>
      )}
    </g>
  );
}

function ShotMarker({
  x,
  y,
  color,
  outcome,
  overturned,
}: {
  x: number;
  y: number;
  color: string;
  outcome: ShotEvent["outcome"];
  overturned: boolean;
}) {
  if (overturned) {
    return (
      <g>
        <circle cx={x} cy={y} r={1.6} fill="none" stroke="#facc15" strokeWidth={0.35} strokeDasharray="0.6 0.4" />
        <text x={x} y={y + 0.7} textAnchor="middle" fontSize={1.6} fontWeight={700} fill="#facc15">VAR</text>
      </g>
    );
  }
  if (outcome === "goal") {
    return (
      <g>
        <circle cx={x} cy={y} r={1.6} fill="none" stroke="white" strokeWidth={0.3} />
        <circle cx={x} cy={y} r={1.1} fill={color} stroke="white" strokeWidth={0.2} />
      </g>
    );
  }
  if (outcome === "off_target" || outcome === "blocked") {
    const d = 0.9;
    return (
      <g stroke={color} strokeWidth={0.45} strokeLinecap="round">
        <line x1={x - d} y1={y - d} x2={x + d} y2={y + d} />
        <line x1={x - d} y1={y + d} x2={x + d} y2={y - d} />
      </g>
    );
  }
  return <circle cx={x} cy={y} r={1.1} fill="white" stroke={color} strokeWidth={0.4} />;
}
