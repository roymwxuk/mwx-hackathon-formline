"""Motion: 10 Hz tracking frames for one match from team shape plus event anchors.

For every frame (ADR-010):
1. the ball follows the event path, looking ahead (this runs offline): along each pass and
   shot over its duration, carried from where it arrived to the next action, with height
   for lofted passes and shots;
2. each player heads for his team-shape spot (shape.py) for that ball and possession,
   smoothed so the team reacts like people rather than jumping, with a little personal
   drift so nobody moves in lockstep;
3. offsets bend each player's path through his anchors (anchors.py), exactly at the anchor
   time: he heads there over a few seconds, goes straight on to his next anchor when it is
   close, and otherwise drifts back to his shape spot slowly rather than snapping back;
4. speed is capped at a sprint, which softens the rare anchors that are out of reach.
"""

import random
from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import pairwise
from math import exp, pi, sin

from formline.pitch import PITCH_LENGTH_M, PITCH_WIDTH_M, clamp
from formline.schema.tracking import FRAME_MS, Ball, TrackedPlayer, TrackingFrame
from formline.tracking.anchors import Anchor, Lineup, event_anchors, starting_lineup
from formline.tracking.shape import team_shape, to_shared

DT = FRAME_MS / 1000
MAX_SPEED = 9.5  # m/s, a sprint
BASE_SPEED = 6.0  # m/s, how fast players drift with the team shape
REACTION_S = 1.2  # smoothing time constant for each player's movement
BALL_SMOOTH_S = 2.0  # the team shape follows the ball smoothed over this long (area of play)
TRANSITION_S = 4.0  # after a turnover, a team eases from one shape to the other this slowly
ANCHOR_WINDOW_S = 8.0  # a player starts heading for his anchor this long before it (4 s forced sprints)
RETURN_S = 20.0  # after an anchor, the pull decays with this time constant (back to shape slowly)
CHAIN_S = 30.0  # anchors closer than this: go straight from one to the next, no detour back
DRIFT_M = 0.5  # personal drift amplitude (more inflates distance covered)
KICKOFF_LEAD_MS = 4_000  # kick-off shape this long before a kick-off pass
ON_BALL = {"pass", "shot", "duel", "interception", "ball_recovery"}
LOFT_M = {"ground": 0.0, "low": 1.5, "high": 7.0}


@dataclass(frozen=True)
class BallKey:
    t: int  # match ms
    x: float  # shared frame
    y: float
    z: float
    loft: float = 0.0  # peak height of the flight that starts here


def _to_m(dx: float, dy: float) -> tuple[float, float]:
    return dx * PITCH_LENGTH_M / 100, dy * PITCH_WIDTH_M / 100


def _cap(prev: tuple[float, float], nxt: tuple[float, float], max_m: float) -> tuple[float, float]:
    """Move from prev toward nxt by at most max_m meters."""
    mx, my = _to_m(nxt[0] - prev[0], nxt[1] - prev[1])
    d = (mx * mx + my * my) ** 0.5
    if d <= max_m:
        return nxt
    k = max_m / d
    return prev[0] + (nxt[0] - prev[0]) * k, prev[1] + (nxt[1] - prev[1]) * k


def _smoothstep(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


# ---------- ball ----------

def ball_keys(events: Iterable, home_club_id: str, period: int) -> list[BallKey]:
    events = [e for e in events if e.period == period]
    keys: list[BallKey] = []
    for i, e in enumerate(events):
        if e.type not in ON_BALL or e.x is None:
            continue
        home = e.team_id == home_club_id
        sx, sy = to_shared((e.x, e.y), home)
        t = e.match_clock_ms
        if e.type in ("pass", "shot") and e.end_x is not None:
            ex, ey = to_shared((e.end_x, e.end_y), home)
            if e.type == "pass" and getattr(e, "outcome", None) == "out":
                ex, ey = _out_of_play_spot(events[i + 1:], home_club_id, (ex, ey))
            loft = LOFT_M.get(getattr(e, "height", "ground") or "ground", 0.0)
            keys.append(BallKey(t, sx, sy, 0.0, loft))
            end_z = (getattr(e, "end_z", None) or 0.0) if e.type == "shot" else 0.0
            keys.append(BallKey(t + max(1, e.duration_ms or 1000), ex, ey, end_z))
        else:
            keys.append(BallKey(t, sx, sy, 0.0))
    keys.sort(key=lambda k: k.t)
    return keys


RESTARTS = {"throw_in", "corner", "goal_kick"}


def _out_of_play_spot(after: list, home_club_id: str,
                      end: tuple[float, float]) -> tuple[float, float]:
    """Where a pass that went out crossed the line (shared frame).

    The feed often records an out pass ending inside the pitch, so the ball would stop in
    midfield and then jump to the restart. The next on-ball event tells which line it crossed:
    a throw-in is taken where the ball crossed the side line; for a corner or a goal kick it
    crossed the goal line at the pass's width."""
    nxt = next((e for e in after if e.type in ON_BALL and e.x is not None), None)
    if nxt is None or nxt.type != "pass" or getattr(nxt, "pass_type", None) not in RESTARTS:
        return end
    rx, ry = to_shared((nxt.x, nxt.y), nxt.team_id == home_club_id)
    if nxt.pass_type == "throw_in":
        return rx, ry
    goal_line = 0.0 if rx < 50 else 100.0
    return goal_line, min(100.0, max(0.0, end[1]))


def ball_at(keys: list[BallKey], times: list[int], t: int) -> Ball:
    if not keys:
        return Ball(x=50, y=50, z=0)
    i = bisect_right(times, t)
    if i == 0:
        return Ball(x=50, y=50, z=0)  # centre spot until the first touch
    a = keys[i - 1]
    if i == len(keys):
        return Ball(x=a.x, y=a.y, z=0)
    b = keys[i]
    u = (t - a.t) / max(1, b.t - a.t)
    z = a.loft * 4 * u * (1 - u) + (b.z * u if b.z else 0.0)
    return Ball(x=a.x + (b.x - a.x) * u, y=a.y + (b.y - a.y) * u, z=max(0.0, z))


# ---------- players ----------

def _possession_at(events: list, times: list[tuple[int, int]], period: int, t: int):
    i = bisect_right(times, (period, t))
    while i > 0:
        e = events[i - 1]
        if e.period != period:
            return None
        if e.type in ON_BALL:
            return getattr(e, "possession_team_id", None) or e.team_id
        i -= 1
    return None


def build_frames(events: list, home_club_id: str, players: Mapping[str, object],
                 starters: Mapping[str, list[str]], seed: int = 2026,
                 limit_ms: int | None = None) -> list[TrackingFrame]:
    """All tracking frames for one match, both periods, from its current events.
    `limit_ms` keeps only the first part of each period (tests, previews)."""
    events = sorted(events, key=lambda e: (e.period, e.match_clock_ms))
    away_club_id = next(c for c in starters if c != home_club_id)
    anchors = event_anchors(events, home_club_id, players, starters)
    rng = random.Random(seed)
    drift: dict[tuple[bool, int], tuple[float, float, float, float]] = {}
    ev_times = [(e.period, e.match_clock_ms) for e in events]
    kickoffs = [(e.period, e.match_clock_ms) for e in events
                if e.type == "pass" and getattr(e, "play_pattern", "") == "from_kick_off"]
    frames: list[TrackingFrame] = []
    lineups = {club: starting_lineup(xi, players) for club, xi in starters.items()}
    subs = [e for e in events if e.type == "substitution"]
    applied: set[str] = set()

    for period in (1, 2):
        bounds = [e.match_clock_ms for e in events if e.period == period
                  and e.type in ("half_start", "half_end")]
        start, end = min(bounds), max(bounds)
        if limit_ms is not None:
            end = min(end, start + limit_ms)
        keys = ball_keys(events, home_club_id, period)
        key_times = [k.t for k in keys]
        ticks = list(range(start, end + 1, FRAME_MS))
        base: dict[tuple[bool, int], list[tuple[float, float] | None]] = {}
        on_pitch: list[dict[tuple[bool, int], bool]] = []
        balls: list[Ball] = []
        smooth: dict[tuple[bool, int], tuple[float, float]] = {}
        area: tuple[float, float] | None = None  # the smoothed ball the team shape follows
        roles: dict[str, list[tuple[bool, int]]] = {}  # who presses / covers / supports
        released: dict[tuple[bool, int], int] = {}  # player -> time he lost his role (ms)
        had_role: set[tuple[bool, int]] = set()
        attack = {home_club_id: 0.5, away_club_id: 0.5}  # eased possession level per team
        for n, t in enumerate(ticks):
            for s in subs:
                if (s.period, s.match_clock_ms) <= (period, t) and s.event_id not in applied:
                    _apply_sub(s, lineups, players, home_club_id, smooth)
                    applied.add(s.event_id)
            ball = ball_at(keys, key_times, t)
            balls.append(ball)
            if area is None or BALL_SMOOTH_S <= 0:
                area = (ball.x, ball.y)
            else:
                k = DT / (BALL_SMOOTH_S + DT)
                area = (area[0] + (ball.x - area[0]) * k, area[1] + (ball.y - area[1]) * k)
            owner = _possession_at(events, ev_times, period, t)
            kickoff = any(p == period and 0 <= kt - t <= KICKOFF_LEAD_MS for p, kt in kickoffs) \
                or (keys and t < keys[0].t)
            present = {}
            targets: dict[tuple[bool, int], tuple[float, float]] = {}
            keepers: set[tuple[bool, int]] = set()
            for club, home in ((home_club_id, True), (away_club_id, False)):
                own_ball = to_shared(area, home)
                target_level = 0.5 if owner is None else 1.0 if owner == club else 0.0
                if kickoff:
                    target_level = 1.0 if _kicking_team(events, ev_times, period, t,
                                                        kickoffs) == club else 0.0
                    attack[club] = target_level  # a restart: no easing
                else:
                    attack[club] += (target_level - attack[club]) * DT / (TRANSITION_S + DT)
                shape = team_shape(lineups[club].slots, own_ball, attack[club], kickoff=kickoff)
                keepers |= {(home, sl.shirt) for sl in lineups[club].slots if sl.role == "GK"}
                for shirt, spot in shape.items():
                    key = (home, shirt)
                    target = to_shared(spot, home)
                    if key not in drift:
                        drift[key] = (rng.uniform(0, 2 * pi), rng.uniform(0, 2 * pi),
                                      rng.uniform(7, 13), rng.uniform(7, 13))
                    px, py, tx, ty = drift[key]
                    secs = t / 1000
                    targets[key] = (target[0] + DRIFT_M * 100 / PITCH_LENGTH_M * sin(2 * pi * secs / tx + px),
                                    target[1] + DRIFT_M * 100 / PITCH_WIDTH_M * sin(2 * pi * secs / ty + py))
            # Near the ball, players act rather than hold shape: pressing, cover, support runs.
            pace = {} if kickoff else _ball_roles(targets, smooth, keepers, (ball.x, ball.y),
                                                  owner, home_club_id, roles, area)
            for key in had_role - set(pace):
                released[key] = t
            had_role = set(pace)
            for key, target in targets.items():
                if key in pace:
                    reaction, top = pace[key]
                elif t - released.get(key, -10**9) < RELEASE_S * 1000:
                    reaction, top = RELEASE_PACE
                else:
                    reaction, top = REACTION_S, BASE_SPEED
                prev = smooth.get(key)
                if prev is None:
                    cur = target
                else:
                    a = DT / (reaction + DT)
                    cur = _cap(prev, (prev[0] + (target[0] - prev[0]) * a,
                                      prev[1] + (target[1] - prev[1]) * a), top * DT)
                smooth[key] = cur
                base.setdefault(key, [None] * len(ticks))[n] = cur
                present[key] = True
            on_pitch.append(present)

        offsets = _anchor_offsets(anchors, period, ticks, base)
        positions: dict[tuple[bool, int], tuple[float, float]] = {}
        for n, t in enumerate(ticks):
            home_ps, away_ps = [], []
            for key in on_pitch[n]:
                bx, by = base[key][n]
                ox, oy = offsets.get(key, {}).get(n, (0.0, 0.0))
                want = (clamp(bx + ox, 0.0, 100.0), clamp(by + oy, 0.0, 100.0))
                prev = positions.get(key)
                cur = want if prev is None else _cap(prev, want, MAX_SPEED * DT)
                positions[key] = cur
                (home_ps if key[0] else away_ps).append(
                    TrackedPlayer(shirt=key[1], x=cur[0], y=cur[1]))
            frames.append(TrackingFrame(period=period, match_clock_ms=t, ball=balls[n],
                                        home=sorted(home_ps, key=lambda p: p.shirt),
                                        away=sorted(away_ps, key=lambda p: p.shirt)))
    return frames


PRESS_PACE = (0.6, 7.0)  # reaction (s), top speed (m/s) for the player closing the ball
COVER_PACE = (0.9, 6.0)  # the second defender, and attackers making support runs
PRESS_RANGE_M = 25.0  # beyond this a defender holds his position instead of pressing
SUPPORT_RANGE_M = 30.0
STICKY_M = 3.0  # a role changes hands only when another player is this much closer
RELEASE_S = 5.0  # after losing a role, a player jogs back to shape for this long...
RELEASE_PACE = (3.0, 4.0)  # ...with this reaction (s) and top speed (m/s), not snapping back


def _offset_m(point: tuple[float, float], dx_m: float, dy_m: float) -> tuple[float, float]:
    return (clamp(point[0] + dx_m * 100 / PITCH_LENGTH_M, 1.0, 99.0),
            clamp(point[1] + dy_m * 100 / PITCH_WIDTH_M, 1.0, 99.0))


def _ball_roles(targets: dict, smooth: dict, keepers: set, ball: tuple[float, float], owner,
                home_club_id: str, roles: dict, area: tuple[float, float] | None = None) -> dict:
    """Override targets near the ball and return per-player pace (reaction, top speed).

    - defending side: the nearest outfield player within range presses (about 1.5 m goal-side
      of the ball), the next covers (about 6 m goal-side);
    - side in possession: the two nearest teammates (after the ball carrier) offer passing
      lanes about 10 m ahead and 8 m wide.
    Role holders are sticky (STICKY_M) so roles do not flicker between equal candidates.
    A loose ball (no owner) is chased by the nearest player of each side.
    """
    from formline.pitch import to_m

    def dist(key) -> float:
        p = smooth.get(key, targets[key])
        return to_m(p[0] - ball[0], p[1] - ball[1])

    def pick(name: str, side_home: bool, count: int, skip: int, limit: float) -> list:
        pool = sorted((k for k in targets if k[0] == side_home and k not in keepers), key=dist)
        pool = [k for k in pool[skip:] if dist(k) <= limit]
        held = [k for k in roles.get(name, []) if k in pool]
        chosen = []
        for k in held:  # keep current holders unless someone is clearly closer
            better = [c for c in pool if c not in held and c not in chosen
                      and dist(c) < dist(k) - STICKY_M]
            if not better and len(chosen) < count:
                chosen.append(k)
        for k in pool:
            if len(chosen) >= count:
                break
            if k not in chosen:
                chosen.append(k)
        roles[name] = chosen
        return chosen

    pace: dict = {}
    attack_home = None if owner is None else owner == home_club_id
    sides = [True, False] if attack_home is None else [not attack_home]
    for side in sides:  # defending side(s)
        goal_x = 0.0 if side else 100.0  # own goal in the shared frame
        toward = -1.0 if goal_x < ball[0] else 1.0
        chasers = pick(f"press{side}", side, 1 if attack_home is None else 2, 0, PRESS_RANGE_M)
        for i, key in enumerate(chasers):
            back = 1.5 if i == 0 else 6.0
            targets[key] = _offset_m(ball, toward * back, (50 - ball[1]) * 0.03 * back)
            pace[key] = PRESS_PACE if i == 0 else COVER_PACE
    if attack_home is not None:
        forward = 1.0 if attack_home else -1.0
        for i, key in enumerate(pick(f"support{attack_home}", attack_home, 2, 1, SUPPORT_RANGE_M)):
            here = smooth.get(key, targets[key])
            side_y = 1.0 if here[1] >= ball[1] else -1.0
            # support runs follow the area of play (smoothed ball), not every pass
            targets[key] = _offset_m(area or ball, forward * (10.0 if i == 0 else 4.0), side_y * 8.0)
            pace[key] = COVER_PACE
    return pace


def _apply_sub(e, lineups: dict[str, Lineup], players, home_club_id: str, smooth) -> None:
    on = players[e.player_on_id]
    lineup = lineups[e.team_id]
    if e.player_off_id not in lineup.by_player:
        return
    off_shirt = lineup.by_player[e.player_off_id]
    lineup.substitute(e.player_off_id, on.player_id, on.shirt_number)
    home = e.team_id == home_club_id
    if (home, off_shirt) in smooth:  # the substitute starts where the player left
        smooth[(home, on.shirt_number)] = smooth.pop((home, off_shirt))


def _kicking_team(events, ev_times, period, t, kickoffs):
    nxt = next(((p, kt) for p, kt in kickoffs if p == period and kt >= t), None)
    if nxt is None:
        return None
    i = bisect_right(ev_times, nxt) - 1
    return events[i].team_id if i >= 0 else None


def _anchor_offsets(anchors: list[Anchor], period: int, ticks: list[int],
                    base) -> dict[tuple[bool, int], dict[int, tuple[float, float]]]:
    """Per player and frame index, the offset that bends his path through his anchors:
    exact at each anchor frame, interpolated between close anchors, fading out after
    ANCHOR_WINDOW_S otherwise."""
    start = ticks[0]
    win = int(ANCHOR_WINDOW_S * 1000 / FRAME_MS)
    by_player: dict[tuple[bool, int], list[tuple[int, float, float]]] = {}
    for a in anchors:
        if a.period != period:
            continue
        key = (a.home, a.shirt)
        n = round((a.t_ms - start) / FRAME_MS)
        if key not in base or not 0 <= n < len(ticks) or base[key][n] is None:
            continue
        bx, by = base[key][n]
        by_player.setdefault(key, []).append((n, a.x - bx, a.y - by))
    out: dict[tuple[bool, int], dict[int, tuple[float, float]]] = {}
    for key, deltas in by_player.items():
        deltas.sort()
        merged: list[tuple[int, float, float]] = []
        for d in deltas:  # two anchors on one frame: keep the later one
            if merged and merged[-1][0] == d[0]:
                merged[-1] = d
            else:
                merged.append(d)
        offs: dict[int, tuple[float, float]] = {}
        chain = int(CHAIN_S * 1000 / FRAME_MS)
        decay = DT / RETURN_S
        first, last = merged[0], merged[-1]
        for n in range(max(0, first[0] - win), first[0]):
            k = _smoothstep(1 - (first[0] - n) / win)
            offs[n] = (first[1] * k, first[2] * k)
        for (na, ax, ay), (nb, bx, by) in pairwise(merged):
            span = nb - na
            for n in range(na, nb):
                if span <= chain:  # straight on to the next anchor
                    u = _smoothstep((n - na) / span)
                    offs[n] = (ax + (bx - ax) * u, ay + (by - ay) * u)
                else:  # drift back slowly, then head for the next anchor
                    fade = exp(-(n - na) * decay)
                    kb = _smoothstep(1 - (nb - n) / win) if nb - n < win else 0.0
                    offs[n] = (ax * fade * (1 - kb) + bx * kb, ay * fade * (1 - kb) + by * kb)
        for n in range(last[0], len(ticks)):
            fade = exp(-(n - last[0]) * decay)
            if fade < 0.02:
                break
            offs[n] = (last[1] * fade, last[2] * fade)
        out[key] = offs
    return out
