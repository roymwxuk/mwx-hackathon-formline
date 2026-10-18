"""Event anchors: where the event feed says a player was, and when (ADR-010, D6).

Each anchor pins one player to one spot at one match time, in the shared tracking frame
(home attacks toward x = 100). Tracking must pass through every anchor, so the pitch never
contradicts the events or the cards built from them:

- pass: the passer at the start; the receiver at the end, when the ball arrives
- shot: the shooter at the shot spot; the freeze frame's players at their spots, matched
  to the nearest real players of the right side (the goalkeeper to the keeper)
- duel, interception, ball recovery, pressure, foul: the player at the event spot

Lineups follow substitution events, so anchors always name a player on the pitch.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import pairwise

from formline.pitch import to_m
from formline.tracking.shape import Slot, assign_roles, team_shape, to_shared

ACTOR_EVENTS = {"duel", "interception", "ball_recovery", "pressure", "foul_committed"}


@dataclass(frozen=True)
class Anchor:
    period: int
    t_ms: int
    home: bool
    shirt: int
    x: float  # shared frame
    y: float
    kind: str  # passer, receiver, shooter, actor, freeze_frame, keeper
    event_id: str


@dataclass
class Lineup:
    """Who is on the pitch for one side, by role (substitutes take the role of the player
    they replace)."""

    slots: list[Slot]
    by_player: dict[str, int]  # player_id -> shirt, for players on the pitch

    def substitute(self, off: str, on: str, shirt_on: int) -> None:
        shirt_off = self.by_player.pop(off)
        self.slots = [Slot(shirt_on, s.role) if s.shirt == shirt_off else s for s in self.slots]
        self.by_player[on] = shirt_on

    def keeper(self) -> int:
        return next(s.shirt for s in self.slots if s.role == "GK")


def starting_lineup(starters: Iterable[str], players: Mapping[str, object]) -> Lineup:
    xi = [players[pid] for pid in starters]
    slots = assign_roles((p.shirt_number, p.position) for p in xi)
    return Lineup(slots, {p.player_id: p.shirt_number for p in xi})


def event_anchors(events: Iterable, home_club_id: str, players: Mapping[str, object],
                  starters: Mapping[str, list[str]]) -> list[Anchor]:
    """Anchors for one match from its current events (event-time order)."""
    lineups = {club: starting_lineup(xi, players) for club, xi in starters.items()}
    out: list[Anchor] = []
    for e in events:
        if e.type == "substitution":
            on = players[e.player_on_id]
            lineups[e.team_id].substitute(e.player_off_id, on.player_id, on.shirt_number)
            continue
        if e.team_id is None or e.player_id is None or e.x is None:
            continue
        home = e.team_id == home_club_id
        lineup = lineups[e.team_id]
        if e.player_id not in lineup.by_player:
            # A player not on the pitch (the generator once credits a restart to a player
            # already substituted off): no anchor rather than a wrong one.
            continue
        shirt = lineup.by_player[e.player_id]
        if e.type == "pass":
            out.append(_pin(e, home, shirt, e.x, e.y, "passer"))
            if e.recipient_id in lineup.by_player and e.end_x is not None:
                out.append(_pin(e, home, lineup.by_player[e.recipient_id], e.end_x, e.end_y,
                                "receiver", t=e.match_clock_ms + (e.duration_ms or 0)))
        elif e.type == "shot":
            out.append(_pin(e, home, shirt, e.x, e.y, "shooter"))
            opp = next(c for c in lineups if c != e.team_id)
            out += _freeze_frame(e, home, shirt, lineup, lineups[opp])
        elif e.type in ACTOR_EVENTS:
            out.append(_pin(e, home, shirt, e.x, e.y, "actor"))
    return out


def _pin(e, home: bool, shirt: int, x: float, y: float, kind: str,
         t: int | None = None) -> Anchor:
    sx, sy = to_shared((x, y), home)  # event spots are in the actor's own frame
    return Anchor(e.period, e.match_clock_ms if t is None else t, home, shirt, sx, sy, kind,
                  e.event_id)


def _freeze_frame(shot, home: bool, shooter: int, own: Lineup, opp: Lineup) -> list[Anchor]:
    """Match the freeze frame's anonymous spots to real players: each spot goes to the
    nearest unused player of that side, judged by where the team shape puts them at the
    moment of the shot (shooting team in possession, ball at the shot spot)."""
    ball_own = (shot.x, shot.y)
    attack = team_shape(own.slots, ball_own, True)
    defend = team_shape(opp.slots, (100 - shot.x, 100 - shot.y), False)  # their own frame
    used = {shooter}
    anchors = []
    for p in shot.freeze_frame or []:
        if p.goalkeeper and not p.teammate:
            shirt, side_home = opp.keeper(), not home
        else:
            if p.teammate:
                shape, side_home, spot = attack, home, (p.x, p.y)
            else:
                shape, side_home, spot = defend, not home, (100 - p.x, 100 - p.y)
            free = [(s, xy) for s, xy in shape.items() if s not in used
                    and (s != (own.keeper() if p.teammate else opp.keeper()))]
            if not free:
                continue
            shirt = min(free, key=lambda kv: to_m(kv[1][0] - spot[0], kv[1][1] - spot[1]))[0]
        used.add(shirt)
        # Freeze-frame spots are in the shooter's frame.
        sx, sy = to_shared((p.x, p.y), home)
        anchors.append(Anchor(shot.period, shot.match_clock_ms, side_home, shirt, sx, sy,
                              "keeper" if p.goalkeeper else "freeze_frame", shot.event_id))
    return anchors


def anchor_speeds(anchors: Iterable[Anchor]) -> list[float]:
    """Straight-line speed (m/s) a player needs between his consecutive anchors in a period;
    a feasibility check for the motion model."""
    by_player: dict[tuple[bool, int, int], list[Anchor]] = {}
    for a in anchors:
        by_player.setdefault((a.home, a.shirt, a.period), []).append(a)
    speeds = []
    for seq in by_player.values():
        seq.sort(key=lambda a: a.t_ms)
        for a, b in pairwise(seq):
            dt = (b.t_ms - a.t_ms) / 1000
            if dt > 0:
                speeds.append(to_m(b.x - a.x, b.y - a.y) / dt)
    return speeds
