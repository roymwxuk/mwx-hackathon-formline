"""Motion: 10 Hz tracking frames for one match from team shape plus event anchors.

For every frame (ADR-010):
1. the ball follows the event path, looking ahead (this runs offline): along each pass and
   shot over its duration, carried from where it arrived to the next action, with height
   for lofted passes and shots;
2. each player heads for his team-shape spot (shape.py) for that ball and possession,
   smoothed so the team reacts like people rather than jumping, with a little personal
   drift so nobody moves in lockstep;
3. offsets bend each player's path through his anchors (anchors.py), exactly at the anchor
   time and fading out a few seconds either side;
4. speed is capped at a sprint, which softens the rare anchors that are out of reach.
"""

import random
from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import pairwise
from math import pi, sin

from formline.pitch import PITCH_LENGTH_M, PITCH_WIDTH_M, clamp
from formline.schema.tracking import FRAME_MS, Ball, TrackedPlayer, TrackingFrame
from formline.tracking.anchors import Anchor, Lineup, event_anchors, starting_lineup
from formline.tracking.shape import team_shape, to_shared

DT = FRAME_MS / 1000
MAX_SPEED = 9.5  # m/s, a sprint
BASE_SPEED = 6.0  # m/s, how fast players drift with the team shape
REACTION_S = 1.2  # smoothing time constant for the team shape
ANCHOR_WINDOW_S = 8.0  # an anchor bends the path this long before and after (4 s forced sprints)
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
    keys: list[BallKey] = []
    for e in events:
        if e.period != period or e.type not in ON_BALL or e.x is None:
            continue
        home = e.team_id == home_club_id
        sx, sy = to_shared((e.x, e.y), home)
        t = e.match_clock_ms
        if e.type in ("pass", "shot") and e.end_x is not None:
            ex, ey = to_shared((e.end_x, e.end_y), home)
            loft = LOFT_M.get(getattr(e, "height", "ground") or "ground", 0.0)
            keys.append(BallKey(t, sx, sy, 0.0, loft))
            end_z = (getattr(e, "end_z", None) or 0.0) if e.type == "shot" else 0.0
            keys.append(BallKey(t + max(1, e.duration_ms or 1000), ex, ey, end_z))
        else:
            keys.append(BallKey(t, sx, sy, 0.0))
    keys.sort(key=lambda k: k.t)
    return keys


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
        for n, t in enumerate(ticks):
            for s in subs:
                if (s.period, s.match_clock_ms) <= (period, t) and s.event_id not in applied:
                    _apply_sub(s, lineups, players, home_club_id, smooth)
                    applied.add(s.event_id)
            ball = ball_at(keys, key_times, t)
            balls.append(ball)
            owner = _possession_at(events, ev_times, period, t)
            kickoff = any(p == period and 0 <= kt - t <= KICKOFF_LEAD_MS for p, kt in kickoffs) \
                or (keys and t < keys[0].t)
            present = {}
            for club, home in ((home_club_id, True), (away_club_id, False)):
                own_ball = to_shared((ball.x, ball.y), home)
                has = None if owner is None else owner == club
                if kickoff:
                    kicking = _kicking_team(events, ev_times, period, t, kickoffs) == club
                    has = kicking
                shape = team_shape(lineups[club].slots, own_ball, has, kickoff=kickoff)
                for shirt, spot in shape.items():
                    key = (home, shirt)
                    target = to_shared(spot, home)
                    if key not in drift:
                        drift[key] = (rng.uniform(0, 2 * pi), rng.uniform(0, 2 * pi),
                                      rng.uniform(7, 13), rng.uniform(7, 13))
                    px, py, tx, ty = drift[key]
                    secs = t / 1000
                    target = (target[0] + DRIFT_M * 100 / PITCH_LENGTH_M * sin(2 * pi * secs / tx + px),
                              target[1] + DRIFT_M * 100 / PITCH_WIDTH_M * sin(2 * pi * secs / ty + py))
                    prev = smooth.get(key)
                    if prev is None:
                        cur = target
                    else:
                        a = DT / (REACTION_S + DT)
                        cur = _cap(prev, (prev[0] + (target[0] - prev[0]) * a,
                                          prev[1] + (target[1] - prev[1]) * a), BASE_SPEED * DT)
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
        first, last = merged[0], merged[-1]
        for n in range(max(0, first[0] - win), first[0]):
            k = _smoothstep(1 - (first[0] - n) / win)
            offs[n] = (first[1] * k, first[2] * k)
        for (na, ax, ay), (nb, bx, by) in pairwise(merged):
            span = nb - na
            for n in range(na, nb):
                if span <= 2 * win:
                    u = _smoothstep((n - na) / span)
                    offs[n] = (ax + (bx - ax) * u, ay + (by - ay) * u)
                else:
                    ka = _smoothstep(1 - (n - na) / win) if n - na < win else 0.0
                    kb = _smoothstep(1 - (nb - n) / win) if nb - n < win else 0.0
                    offs[n] = (ax * ka + bx * kb, ay * ka + by * kb)
        for n in range(last[0], min(len(ticks), last[0] + win)):
            k = _smoothstep(1 - (n - last[0]) / win)
            offs[n] = (last[1] * k, last[2] * k)
        out[key] = offs
    return out
