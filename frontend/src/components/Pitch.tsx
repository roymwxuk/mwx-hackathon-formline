import { useCallback, useEffect, useRef, type KeyboardEvent, type SVGProps } from 'react';
import { ballAt } from '@/lib/ball';
import { canFocus } from '@/lib/logic';
import { FrameInterpolator } from '@/lib/interpolate';
import { eventsReached, labelledPlayers, trackedMarkers } from '@/lib/tracking';
import type { Club, Lang, MatchEvent, Player, TrackingFrameMessage } from '@/lib/types';

interface Props {
  events: MatchEvent[]; // event-time order, latest versions only
  clockMs: number;
  clubs: Club[];
  players: Player[];
  lang: Lang;
  /** Analyst view adds the shot cone and the nearest-defender distance. */
  detailed: boolean;
  /** Latest tracking frame: all 22 players and the ball. Without it, the pitch shows the
   *  event actors and a ball path reconstructed from events. */
  frame?: TrackingFrameMessage | null;
  focusPlayer?: string | null;
  /** The viewer's favorite players: always named on the tracked pitch. */
  favoritePlayers?: string[];
  /** Clicking a player who can be followed (see canFocus) passes his id here. */
  onPlayerClick?: (playerId: string) => void;
}

const W = 1050;
const H = 680;
const SHOT_HOLD_MS = 25_000; // keep a shot on screen for 25 match seconds
const ARROW_MIN_MS = 0.8; // m/s: below this the focus player's running arrow is hidden

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/** Each team's coordinates attack left→right; flip the away side so both share one pitch. */
function toScreen(x: number, y: number, flip: boolean): [number, number] {
  const dx = flip ? 100 - x : x;
  const dy = flip ? 100 - y : y;
  return [dx * (W / 100), dy * (H / 100)];
}

export function Pitch({ events: received, clockMs, clubs, players, lang, detailed, frame, focusPlayer = null, favoritePlayers = [], onPlayerClick }: Props) {
  // Only what the clock has reached: the ball travels first, then its pass line appears.
  const period = frame?.p ?? received[received.length - 1]?.period ?? 1;
  const events = frame ? eventsReached(received, period, clockMs) : received;
  const tracked = frame ? trackedMarkers(frame, clubs, players) : null;
  const named = tracked ? labelledPlayers(events, clockMs, focusPlayer, favoritePlayers) : null;

  // Tracked markers move by JavaScript interpolation in an animation loop, not CSS
  // transitions (Firefox restarts interrupted SVG transitions from a stale position, so
  // every player stuttered backwards). React only adds and removes markers.
  const interp = useRef<FrameInterpolator | null>(null);
  interp.current ??= new FrameInterpolator(prefersReducedMotion());
  const lastFrame = useRef<TrackingFrameMessage | null | undefined>(undefined);
  if (frame !== lastFrame.current) { // a new frame: blend from what is drawn now
    if (frame) interp.current.set(frame, performance.now());
    else interp.current.reset();
    lastFrame.current = frame;
  }
  const nodes = useRef(new Map<string, SVGGElement>());
  const ballNode = useRef<{ g: SVGGElement | null; shadow: SVGEllipseElement | null; ball: SVGCircleElement | null }>(
    { g: null, shadow: null, ball: null });
  const arrowNode = useRef<{ g: SVGGElement | null; line: SVGLineElement | null; head: SVGPathElement | null }>(
    { g: null, line: null, head: null });
  const focusKeyRef = useRef<string | null>(null);
  focusKeyRef.current = tracked?.find((m) => m.player?.player_id === focusPlayer)?.key ?? null;
  const place = useCallback((now: number) => {
    const pos = interp.current!.at(now);
    for (const [key, node] of nodes.current) {
      const isLabel = key.startsWith('label-');
      const p = pos.get(isLabel ? key.slice(6) : key);
      if (!p) continue;
      const [sx, y] = toScreen(p.x, p.y, false);
      const x = isLabel ? Math.min(Math.max(sx, 60), W - 60) : sx; // keep names inside the pitch
      node.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)})`);
    }
    // Running direction of the focus player: an arrow along his current movement, longer when
    // faster, hidden when he is (nearly) standing.
    const { g: ag, line, head } = arrowNode.current;
    const fk = focusKeyRef.current;
    if (ag && line && head) {
      const p = fk ? pos.get(fk) : undefined;
      const v = fk ? interp.current!.velocity(fk) : { vx: 0, vy: 0 };
      const ms = Math.hypot(v.vx * 1.05, v.vy * 0.68); // pitch % per second -> m/s
      if (!p || ms < ARROW_MIN_MS) {
        ag.setAttribute('visibility', 'hidden');
      } else {
        const [x, y] = toScreen(p.x, p.y, false);
        const angle = (Math.atan2(v.vy * (H / 100), v.vx * (W / 100)) * 180) / Math.PI;
        const len = 20 + Math.min(ms, 9) * 6; // from the marker's edge outwards
        ag.setAttribute('visibility', 'visible');
        ag.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${angle.toFixed(1)})`);
        line.setAttribute('x2', len.toFixed(1));
        head.setAttribute('d', `M ${len} -6 L ${len + 10} 0 L ${len} 6 Z`);
      }
    }
    const b = pos.get('ball');
    const { g, shadow, ball: circle } = ballNode.current;
    if (b && g && shadow && circle) {
      const [x, y] = toScreen(b.x, b.y, false);
      const lift = (b.z ?? 0) * 4; // height in meters, drawn as a lift above its shadow
      g.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)})`);
      shadow.setAttribute('visibility', lift > 1 ? 'visible' : 'hidden');
      circle.setAttribute('cy', (-lift).toFixed(1));
      circle.setAttribute('r', (7 + lift / 12).toFixed(1));
    }
  }, []);
  const hasFrame = frame != null;
  useEffect(() => {
    if (!hasFrame) return;
    let raf = 0;
    const tick = () => {
      place(performance.now());
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [hasFrame, place]);
  const track = (key: string) => (el: SVGGElement | null) => {
    if (el) {
      nodes.current.set(key, el);
      place(performance.now()); // a new marker starts at its spot, not at the corner
    } else {
      nodes.current.delete(key);
    }
  };
  const away = clubs[1].club_id;
  const clubById = new Map(clubs.map((c) => [c.club_id, c]));
  const playerById = new Map(players.map((p) => [p.player_id, p]));

  const onBall = events.filter((e) => (e.type === 'pass' || e.type === 'shot') && e.x !== null && e.y !== null);
  const last = onBall[onBall.length - 1];
  const lastShot = [...onBall].reverse().find((e) => e.type === 'shot');
  const showShot = lastShot && clockMs - lastShot.match_clock_ms < SHOT_HOLD_MS && lastShot === last;
  const trail = onBall.filter((e) => e.type === 'pass').slice(-4);

  // The ball: from tracking when there is a frame, else reconstructed from events (lib/ball.ts).
  const ballPoint = ballAt(events, clockMs, away);
  const ball = toScreen(ballPoint.x, ballPoint.y, false);

  const label = (id: string | null) => {
    const p = id ? playerById.get(id) : undefined;
    if (!p) return '';
    return lang === 'ja' ? p.display_name_ja : p.display_name.split(' ').slice(-1)[0].toUpperCase();
  };

  // A player marker the viewer can click (or press Enter on) to follow that player.
  const clickable = (id: string | null | undefined): SVGProps<SVGGElement> => {
    const p = id ? playerById.get(id) : undefined;
    if (!p || !onPlayerClick || !canFocus(p)) return {};
    const name = lang === 'ja' ? p.display_name_ja : p.display_name;
    return {
      role: 'button', tabIndex: 0, className: 'pitch-pick',
      'aria-label': p.player_id === focusPlayer ? `Stop following ${name}` : `Follow ${name}`,
      onClick: () => onPlayerClick(p.player_id),
      onKeyDown: (e: KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPlayerClick(p.player_id); }
      },
    };
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="pitch" role="img" aria-label="Live 2D pitch">
      <rect width={W} height={H} fill="var(--pitch)" />
      {[105, 315, 525, 735, 945].map((x) => (
        <rect key={x} x={x} y={0} width={105} height={H} fill="var(--pitch-stripe)" />
      ))}
      <g fill="none" stroke="var(--pitch-line)" strokeWidth={2}>
        <rect x={2} y={2} width={W - 4} height={H - 4} />
        <line x1={525} y1={2} x2={525} y2={H - 2} />
        <circle cx={525} cy={340} r={91.5} />
        <rect x={2} y={138.5} width={163} height={403} />
        <rect x={2} y={248.4} width={53} height={183.2} />
        <rect x={885} y={138.5} width={163} height={403} />
        <rect x={995} y={248.4} width={53} height={183.2} />
      </g>
      <line x1={1045} y1={303.4} x2={1045} y2={376.6} stroke="#fff" strokeWidth={8} />
      <line x1={5} y1={303.4} x2={5} y2={376.6} stroke="#fff" strokeWidth={8} />

      {/* Recent passes */}
      {!showShot &&
        trail.map((e, i) => {
          const flip = e.team_id === away;
          const [x1, y1] = toScreen(e.x!, e.y!, flip);
          const [x2, y2] = toScreen(e.end_x ?? e.x!, e.end_y ?? e.y!, flip);
          const club = clubById.get(e.team_id ?? '');
          const isLast = i === trail.length - 1;
          return (
            <g key={e.event_id} opacity={isLast ? 1 : 0.35}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--accent-soft)" strokeWidth={3} strokeDasharray="10 8" />
              {isLast && club && !tracked && (
                <g {...clickable(e.player_id)}>
                  <circle cx={x1} cy={y1} r={14} fill={club.color} stroke="#fff" strokeWidth={2} />
                  <text x={x1} y={y1 - 22} textAnchor="middle" className="pitch-label">{label(e.player_id)}</text>
                </g>
              )}
            </g>
          );
        })}

      {/* Shot view: shot line, freeze frame, shooter */}
      {showShot && lastShot && (() => {
        const flip = lastShot.team_id === away;
        const [sx, sy] = toScreen(lastShot.x!, lastShot.y!, flip);
        const [ex, ey] = toScreen(lastShot.end_x ?? 100, lastShot.end_y ?? 50, flip);
        const shooterClub = clubById.get(lastShot.team_id ?? '');
        const opponent = clubs.find((c) => c.club_id !== lastShot.team_id);
        const goalX = flip ? 5 : 1045;
        const nearest = (lastShot.freeze_frame ?? [])
          .filter((p) => !p.teammate && !p.goalkeeper)
          .map((p) => ({ p, d: Math.hypot((p.x - lastShot.x!) * 1.05, (p.y - lastShot.y!) * 0.68) }))
          .sort((a, b) => a.d - b.d)[0];
        const disallowed = lastShot.version > 1 && lastShot.outcome !== 'goal';
        return (
          <g>
            {detailed && (
              <g stroke="rgba(255,255,255,0.35)" strokeWidth={1.5}>
                <line x1={sx} y1={sy} x2={goalX} y2={303.4} />
                <line x1={sx} y1={sy} x2={goalX} y2={376.6} />
              </g>
            )}
            <line
              x1={sx} y1={sy} x2={ex} y2={ey}
              stroke={disallowed ? 'var(--muted)' : 'var(--accent)'}
              strokeWidth={5}
              strokeDasharray={disallowed ? '12 8' : undefined}
            />
            {!tracked && (lastShot.freeze_frame ?? []).map((p, i) => {
              const [px, py] = toScreen(p.x, p.y, flip);
              const fill = p.goalkeeper ? 'var(--keeper)' : p.teammate ? shooterClub?.color : opponent?.color;
              return (
                <g key={i}>
                  <circle cx={px} cy={py} r={p.goalkeeper ? 14 : 13} fill={fill} stroke={p.goalkeeper ? '#111' : (p.teammate ? shooterClub : opponent)?.text_color} strokeWidth={2} />
                  {p.goalkeeper && <text x={px} y={py + 4} textAnchor="middle" className="pitch-gk">GK</text>}
                </g>
              );
            })}
            {detailed && nearest && (() => {
              const [nx, ny] = toScreen(nearest.p.x, nearest.p.y, flip);
              return <text x={nx} y={ny + 32} textAnchor="middle" className="pitch-metric">{nearest.d.toFixed(1)} m</text>;
            })()}
            {!tracked && (
              <g {...clickable(lastShot.player_id)}>
                <circle cx={sx} cy={sy} r={17} fill={shooterClub?.color} stroke="var(--accent)" strokeWidth={4} />
                <text x={sx} y={sy + 6} textAnchor="middle" className="pitch-number" fill={shooterClub?.text_color}>
                  {playerById.get(lastShot.player_id ?? '')?.shirt_number}
                </text>
                <text x={sx} y={sy - 28} textAnchor="middle" className="pitch-label">{label(lastShot.player_id)}</text>
              </g>
            )}
          </g>
        );
      })()}

      {/* Tracking: every player, keyed by side and shirt; positioned by the animation loop. */}
      {tracked?.map((m) => {
        const focus = m.player && m.player.player_id === focusPlayer;
        const pick = clickable(m.player?.player_id);
        return (
          <g key={m.key} ref={track(m.key)} {...pick} className={`track-player ${pick.className ?? ''}`}>
            {pick.onClick && <circle r={24} className="pitch-hit" />}
            <circle r={focus ? 15 : 13} fill={m.club.color} stroke={focus ? 'var(--accent)' : m.club.text_color}
              strokeWidth={focus ? 4 : 2} />
            <text y={5} textAnchor="middle" className="pitch-number" fill={m.club.text_color}>{m.player?.shirt_number}</text>
          </g>
        );
      })}
      {tracked && focusPlayer && (
        <g ref={(el) => { arrowNode.current.g = el; }} className="run-arrow" visibility="hidden" pointerEvents="none">
          <line ref={(el) => { arrowNode.current.line = el; }} x1={18} y1={0} x2={30} y2={0} />
          <path ref={(el) => { arrowNode.current.head = el; }} d="M 30 -6 L 40 0 L 30 6 Z" />
        </g>
      )}
      {/* Names in their own layer, so no marker drawn later can cover them. */}
      {tracked?.filter((m) => m.player && named?.has(m.player.player_id)).map((m) => (
        <g key={`label-${m.key}`} ref={track(`label-${m.key}`)} className="track-label" pointerEvents="none">
          <text y={-22} textAnchor="middle" className="pitch-label">{label(m.player!.player_id)}</text>
        </g>
      ))}

      {tracked ? (
        <g ref={(el) => { ballNode.current.g = el; }} pointerEvents="none">
          <ellipse ref={(el) => { ballNode.current.shadow = el; }} rx={7} ry={3} fill="rgba(0,0,0,0.35)" visibility="hidden" />
          <circle ref={(el) => { ballNode.current.ball = el; }} r={7} fill="#fff" stroke="#111" strokeWidth={2} />
        </g>
      ) : (
        /* Event-only mode: positioned by transform so CSS can glide between clock ticks. */
        <g className="ball" style={{ transform: `translate(${ball[0]}px, ${ball[1]}px)` }} pointerEvents="none">
          <circle r={7} fill="#fff" stroke="#111" strokeWidth={2} />
        </g>
      )}
    </svg>
  );
}
