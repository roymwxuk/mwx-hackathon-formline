"""Possession-chain match simulator.

A possession starts from a kickoff, restart or turnover and runs pass by pass until
it ends in a turnover, a foul-free restart for the other side, or a shot. Shot
speed, placement and outcome come from the shooter's hidden profile, so every
player has a stable "true" style that the engine's baselines can later recover.

All locations are in the acting team's frame (attacking toward x = 100).
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import exp

from formline.generator.league import LatentProfile, League
from formline.generator.pitch import (
    GOAL_HEIGHT_M,
    GOAL_WIDTH_M,
    PITCH_WIDTH_M,
    POST_HIGH_Y,
    POST_LOW_Y,
    clamp,
    goal_distance_m,
    in_box,
    mirror,
    to_m,
)
from formline.schema.events import (
    BallRecoveryEvent,
    CardEvent,
    DuelEvent,
    FoulCommittedEvent,
    FreezeFramePlayer,
    HalfEndEvent,
    HalfStartEvent,
    InterceptionEvent,
    PassEvent,
    PassTracking,
    PressureEvent,
    ShotEvent,
    ShotTracking,
    SubstitutionEvent,
    VarReviewEndEvent,
    VarReviewStartEvent,
)
from formline.schema.reference import Match, Player

HALF_MS = 45 * 60_000
HALF_TIME_BREAK = timedelta(minutes=15)
BEAT_LEAD_MS = 12_000  # a scripted beat takes over this long before its shot
BEAT_BUILDUP_MS = 7_000  # its two build-up passes start this long before the shot

# Where each position tends to receive the ball: (x, y) in the attacking frame.
# y < 50 is the right flank (attacking toward x = 100), y > 50 the left.
POSITION_ZONES = {
    "GK": (6, 50), "CB": (28, 50), "RB": (45, 15), "LB": (45, 85), "DM": (42, 50),
    "CM": (55, 50), "AM": (70, 50), "RW": (74, 18), "LW": (74, 82), "ST": (84, 50),
}


@dataclass(order=True)
class ScriptedShot:
    """A demo beat pinned onto the live match: this shot happens at this time."""

    clock_ms: int
    player_id: str = field(compare=False)
    x: float = field(compare=False)
    y: float = field(compare=False)
    outcome: str = field(compare=False)
    speed_kmh: float = field(compare=False)
    body_part: str = field(compare=False, default="right_foot")
    under_pressure: bool = field(compare=False, default=False)
    end_y: float = field(compare=False, default=50.0)
    end_z: float = field(compare=False, default=0.5)
    var_cancel: bool = field(compare=False, default=False)


@dataclass
class PendingUpdate:
    """A corrected version of an event, published on the feed at `emit_at`."""

    emit_at: datetime
    event: ShotEvent


@dataclass
class Restart:
    team: str
    x: float
    y: float
    pattern: str
    pass_type: str | None = None  # kick_off, goal_kick, throw_in, corner, free_kick
    carrier: str | None = None
    penalty: bool = False


class MatchSim:
    def __init__(self, match: Match, league: League, match_no: int, seed: int,
                 script: list[ScriptedShot] | None = None):
        self.m = match
        self.rng = random.Random(f"{seed}:{match.match_id}")
        self.match_no = match_no
        self.players: dict[str, Player] = {p.player_id: p for p in league.players}
        self.profiles: dict[str, LatentProfile] = league.profiles
        self.script = sorted(script or [])
        self.events: list = []
        self.updates: list[PendingUpdate] = []
        self.n = 0
        self.possession = 0
        self.poss_team: str | None = None
        self.pattern = "regular_play"
        self.period = 1
        self.clock = 0
        self.first_half_len = timedelta(0)
        self.yellows: set[str] = set()
        self.on_pitch: dict[str, list[str]] = {}
        self.bench: dict[str, list[str]] = {}
        self.sub_times: dict[str, list[int]] = {}
        for club in (match.home_club_id, match.away_club_id):
            xi = list(league.starters[club])
            bench = [p.player_id for p in league.squad(club) if p.player_id not in xi]
            if not match.is_live_demo:  # light squad rotation in historical matches
                for i, pid in enumerate(xi):
                    group = self.players[pid].position_group
                    alt = [b for b in bench if self.players[b].position_group == group]
                    if group != "GK" and alt and self.rng.random() < 0.1:
                        swap = self.rng.choice(alt)
                        xi[i], bench[bench.index(swap)] = swap, pid
            self.on_pitch[club] = xi
            self.bench[club] = bench
            n_subs = self.rng.choice([3, 4, 4, 5])
            self.sub_times[club] = sorted(
                HALF_MS + self.rng.randint(55 - 45, 88 - 45) * 60_000 for _ in range(n_subs)
            )

    # ---------- public ----------

    def run(self) -> tuple[list, list[PendingUpdate]]:
        for period in (1, 2):
            self._play_period(period)
        return self.events, self.updates

    # ---------- time and emission ----------

    def _event_time(self) -> datetime:
        base = self.m.kickoff_at
        if self.period == 1:
            return base + timedelta(milliseconds=self.clock)
        return base + self.first_half_len + HALF_TIME_BREAK + timedelta(
            milliseconds=self.clock - HALF_MS)

    def _advance(self, lo_ms: int, hi_ms: int) -> None:
        self._tick(self.rng.randint(lo_ms, hi_ms))

    def _tick(self, step: int) -> None:
        """Move the clock, but never past the build-up point of the next scripted beat."""
        if self.script:
            limit = self.script[0].clock_ms - BEAT_BUILDUP_MS
            step = max(0, min(step, limit - self.clock)) if self.clock < limit else 0
        self.clock += step

    def _emit(self, cls, *, team: str | None = None, player: str | None = None,
              x: float | None = None, y: float | None = None, **fields):
        self.n += 1
        event = cls(
            event_id=f"evt_{self.match_no:02d}{self.n:05d}",
            match_id=self.m.match_id,
            period=self.period,
            match_clock_ms=self.clock,
            event_time=self._event_time(),
            team_id=team,
            player_id=player,
            position=self.players[player].position if player else None,
            possession=self.possession,
            possession_team_id=self.poss_team,
            play_pattern=self.pattern,
            x=None if x is None else round(x, 1),
            y=None if y is None else round(y, 1),
            **fields,
        )
        self.events.append(event)
        return event

    def _new_possession(self, team: str, pattern: str) -> None:
        self.possession += 1
        self.poss_team = team
        self.pattern = pattern

    # ---------- structure ----------

    def _opp(self, team: str) -> str:
        return self.m.away_club_id if team == self.m.home_club_id else self.m.home_club_id

    def _play_period(self, period: int) -> None:
        self.period = period
        rng = self.rng
        start = 0 if period == 1 else HALF_MS
        stoppage = (rng.randint(1, 3) if period == 1 else rng.randint(3, 6)) * 60_000
        end = start + HALF_MS + stoppage + rng.randint(0, 50) * 1000
        self.clock = start
        self._emit(HalfStartEvent)
        team = self.m.home_club_id if period == 1 else self.m.away_club_id
        nxt = Restart(team, 50, 50, "from_kick_off", "kick_off")
        while self.clock < end:
            nxt = self._possession(nxt, end)
        self.clock = max(self.clock, end)
        self._emit(HalfEndEvent)
        if period == 1:
            self.first_half_len = timedelta(milliseconds=self.clock)

    def _pick(self, team: str, x: float, y: float, exclude: str | None = None,
              shooter: bool = False, header: bool = False, keeper: bool = False) -> str:
        pool = [p for p in self.on_pitch[team] if p != exclude]
        if keeper:
            return next((p for p in pool if self.players[p].position == "GK"), pool[0])
        pool = [p for p in pool if self.players[p].position != "GK"] or pool
        weights = []
        for pid in pool:
            px, py = POSITION_ZONES[self.players[pid].position]
            w = exp(-((x - px) / 24) ** 2 - ((y - py) / 34) ** 2) + 0.02
            prof = self.profiles[pid]
            if shooter:
                w *= prof.shot_volume + 0.05
            if header:
                w *= prof.header_skill
            weights.append(w)
        return self.rng.choices(pool, weights)[0]

    def _maybe_substitute(self) -> None:
        if self.period != 2:
            return
        protected = {s.player_id for s in self.script}  # keep demo shooters on the pitch
        for team, times in self.sub_times.items():
            if not times or self.clock < times[0] or not self.bench[team]:
                continue
            times.pop(0)
            outfield = [p for p in self.on_pitch[team]
                        if self.players[p].position != "GK" and p not in protected]
            if not outfield:
                continue
            weights = [{"FWD": 3, "MID": 2, "DEF": 1}[self.players[p].position_group]
                       for p in outfield]
            off = self.rng.choices(outfield, weights)[0]
            group = self.players[off].position_group
            same = [b for b in self.bench[team] if self.players[b].position_group == group]
            candidates = same or [b for b in self.bench[team]
                                  if self.players[b].position != "GK"]
            if not candidates:
                continue
            on = self.rng.choice(candidates)
            self.on_pitch[team][self.on_pitch[team].index(off)] = on
            self.bench[team].remove(on)
            self._emit(SubstitutionEvent, team=team, player=off, player_off_id=off,
                       player_on_id=on)
            self._advance(20_000, 35_000)

    def _due_beat(self) -> ScriptedShot | None:
        if self.script and self.clock >= self.script[0].clock_ms - BEAT_LEAD_MS:
            return self.script.pop(0)
        return None

    # ---------- possession ----------

    def _possession(self, r: Restart, end: int) -> Restart:
        rng = self.rng
        self._maybe_substitute()
        team, opp = r.team, self._opp(r.team)
        self._new_possession(team, r.pattern)
        if r.penalty:
            taker = max((p for p in self.on_pitch[team] if self.players[p].position != "GK"),
                        key=lambda p: self.profiles[p].shot_volume)
            return self._shot(team, taker, 88.6, 50.0, None, False, shot_type="penalty")

        x, y = r.x, r.y
        pass_type = r.pass_type
        keeper = pass_type == "goal_kick"
        carrier = r.carrier or self._pick(team, x, y, keeper=keeper)
        last_pass: PassEvent | None = None
        from_cross = False

        while self.clock < end:
            beat = self._due_beat()
            if beat:
                return self._scripted(beat, team, x, y)

            if pass_type is None and rng.random() < self._shot_prob(x, y, carrier, from_cross):
                return self._shot(team, carrier, x, y, last_pass, from_cross)
            if pass_type == "free_kick" and goal_distance_m(x, y) < 30 and rng.random() < 0.4:
                return self._shot(team, carrier, x, y, None, False, shot_type="free_kick")

            pressured = pass_type is None and rng.random() < 0.12 + 0.24 * x / 100
            if pressured and rng.random() < 0.85:
                px, py = mirror(x, y)
                presser = self._pick(opp, px, py)
                self._emit(PressureEvent, team=opp, player=presser, x=px, y=py,
                           duration_ms=rng.randint(400, 1800),
                           counterpress=rng.random() < 0.18)

            if pass_type is None:
                roll = rng.random()
                if roll < 0.024:
                    restart = self._foul(team, carrier, x, y)
                    if restart.penalty:
                        return restart
                    x, y, pass_type = restart.x, restart.y, "free_kick"
                    if restart.carrier:
                        carrier = restart.carrier
                    continue
                if roll < 0.024 + 0.035:
                    px, py = mirror(x, y)
                    tackler = self._pick(opp, px, py)
                    won = rng.random() < 0.55
                    self._emit(DuelEvent, team=opp, player=tackler, x=px, y=py,
                               duel_type="tackle", outcome="won" if won else "lost")
                    self._advance(800, 2500)
                    if won:
                        return Restart(opp, px, py, "regular_play", carrier=tackler)

            event, recipient = self._pass(team, carrier, x, y, pass_type, pressured)
            pass_type = None
            if event.outcome == "complete":
                carrier, from_cross, last_pass = recipient, event.cross, event
                carry = 0.0 if event.cross else max(0.0, rng.gauss(1.5, 2.5))
                x, y = clamp(event.end_x + carry, 1, 99), event.end_y
                continue
            ex, ey = event.end_x, event.end_y
            mx, my = mirror(ex, ey)
            if event.outcome == "out":
                self._advance(8_000, 20_000)
                if ex >= 99:
                    return Restart(opp, 6, 50, "from_goal_kick", "goal_kick")
                return Restart(opp, mx, 0.5 if my < 50 else 99.5, "from_throw_in", "throw_in")
            if event.outcome == "offside":
                self._advance(10_000, 25_000)
                return Restart(opp, clamp(mx, 5, 40), my, "from_free_kick", "free_kick")
            winner = self._pick(opp, mx, my)
            if event.height == "high" and rng.random() < 0.5:
                self._emit(DuelEvent, team=opp, player=winner, x=mx, y=my,
                           duel_type="aerial", outcome="won")
            elif rng.random() < 0.4:
                self._emit(InterceptionEvent, team=opp, player=winner, x=mx, y=my, outcome="won")
            else:
                self._emit(BallRecoveryEvent, team=opp, player=winner, x=mx, y=my,
                           recovery_failure=False)
            self._advance(500, 1500)
            counter = mx < 45 and rng.random() < 0.15
            return Restart(opp, mx, my, "from_counter" if counter else "regular_play",
                           carrier=winner)
        return Restart(opp, 50, 50, "from_kick_off", "kick_off")

    def _foul(self, team: str, carrier: str, x: float, y: float) -> Restart:
        rng = self.rng
        opp = self._opp(team)
        px, py = mirror(x, y)
        fouler = self._pick(opp, px, py)
        penalty = in_box(x, y) and rng.random() < 0.45
        r = rng.random()
        card = "red" if r < 0.004 else "yellow" if r < 0.14 else "none"
        self._emit(FoulCommittedEvent, team=opp, player=fouler, x=px, y=py, card=card,
                   penalty=penalty)
        if card != "none":
            second = card == "yellow" and fouler in self.yellows
            self.yellows.add(fouler)
            self._emit(CardEvent, team=opp, player=fouler, x=px, y=py,
                       card="second_yellow" if second else card)
            if (card == "red" or second) and len(self.on_pitch[opp]) > 8:
                self.on_pitch[opp].remove(fouler)
        self._advance(15_000, 40_000)
        if penalty:
            self._advance(30_000, 60_000)
            return Restart(team, 88.6, 50, "from_free_kick", penalty=True)
        return Restart(team, x, y, "from_free_kick", "free_kick", carrier=carrier)

    def _pass(self, team: str, carrier: str, x: float, y: float, pass_type: str | None,
              pressured: bool) -> tuple[PassEvent, str | None]:
        rng = self.rng
        prof = self.profiles[carrier]
        cross = through = False
        height = "ground"
        if pass_type == "kick_off":
            x, y = 50.0, 50.0
            ex, ey, p = rng.uniform(36, 46), rng.uniform(35, 65), 0.99
        elif pass_type == "goal_kick":
            x, y = 6.0, 50.0
            if rng.random() < 0.45:
                ex, ey, p, height = rng.uniform(45, 70), rng.uniform(15, 85), 0.5, "high"
            else:
                ex, ey, p = rng.uniform(12, 25), rng.uniform(15, 85), 0.97
        elif pass_type == "throw_in":
            ex = clamp(x + rng.gauss(3, 6), 1, 99)
            ey = y + (1 if y < 50 else -1) * rng.uniform(5, 18)
            p, height = 0.86, "low"
        elif pass_type == "corner" or (pass_type == "free_kick" and x > 68
                                       and rng.random() < 0.6):
            if pass_type == "corner":
                x, y = 99.5, rng.choice([0.5, 99.5])
            ex, ey = rng.uniform(88, 97), rng.uniform(36, 64)
            p, height, cross = 0.32, "high", True
        else:
            r = rng.random()
            if x > 72 and (y < 25 or y > 75) and r < 0.30:
                ex, ey = rng.uniform(86, 97), rng.uniform(34, 66)
                p, height, cross = 0.27, "high", True
            elif x > 55 and r < 0.05:
                ex, ey = x + rng.uniform(10, 24), y + (50 - y) * rng.uniform(0.2, 0.6)
                p, through = 0.45, True
            elif r < 0.07:
                ex, ey = x + rng.uniform(25, 45), y + rng.gauss(0, 18)
                p, height = 0.5, "high"
            else:
                ex = x + rng.gauss(5.0 if x < 65 else 1.0, 11)
                ey = y + rng.gauss((50 - y) * 0.1, 14)
                p = 0.94
            ex, ey = clamp(ex, 1, 99.6), clamp(ey, 0.5, 99.5)
            length = to_m(ex - x, ey - y)
            if not cross and not through:
                p -= 0.004 * max(0.0, length - 12) + 0.08 * (ex > 84) + 0.04 * (height == "high")
            p -= 0.10 * pressured
        ex, ey = clamp(ex, 1, 99.6), clamp(ey, 0.5, 99.5)
        p = max(0.12, min(0.99, p + prof.pass_skill))
        length = to_m(ex - x, ey - y)

        forward = ex - x > 8 and ex > 70
        if (through or forward) and pass_type is None and rng.random() < 0.035:
            outcome = "offside"
        elif rng.random() < p:
            outcome = "complete"
        elif ey < 3 or ey > 97 or ex > 99 or rng.random() < 0.2:
            outcome = "out"
        else:
            outcome = "incomplete"
        recipient = self._pick(team, ex, ey, exclude=carrier) if outcome == "complete" else None

        speed = rng.gauss(62 if height == "high" else 42, 9)
        duration = int(length / max(speed, 15) * 3600)
        event = self._emit(
            PassEvent, team=team, player=carrier, x=x, y=y, under_pressure=pressured,
            duration_ms=duration, recipient_id=recipient, end_x=round(ex, 1),
            end_y=round(ey, 1), length_m=round(length, 1), height=height,
            pass_type=pass_type or "open_play", cross=cross, through_ball=through,
            outcome=outcome, tracking=PassTracking(ball_speed_kmh=round(speed, 1)),
        )
        self._tick(duration + max(400, int(rng.gauss(2400, 800))))
        return event, recipient

    # ---------- shots ----------

    def _shot_prob(self, x: float, y: float, carrier: str, from_cross: bool) -> float:
        d = goal_distance_m(x, y)
        if d > 35 or x < 60:
            return 0.0
        prof = self.profiles[carrier]
        if from_cross and in_box(x, y):
            return 0.5
        p = 0.025 + 0.32 * exp(-(d - 6) / 6.0)
        if d > 18:
            p *= 0.5 + 1.5 * prof.long_range_tendency
        return min(0.6, p * (0.6 + 0.4 * min(1.0, prof.shot_volume / 2)))

    def _freeze_frame(self, x: float, y: float, pressured: bool) -> list[FreezeFramePlayer]:
        rng = self.rng
        frame = [FreezeFramePlayer(x=round(rng.uniform(96.5, 99.6), 1),
                                   y=round(50 + (y - 50) * 0.12 + rng.gauss(0, 1), 1),
                                   teammate=False, goalkeeper=True)]
        n_def = rng.choice([1, 2, 2, 3, 3, 4]) if in_box(x, y) else rng.choice([1, 2, 2, 3])
        for i in range(n_def):
            if i == 0:  # the nearest defender decides "under pressure"
                dist = rng.uniform(0.6, 2.2) if pressured else rng.uniform(2.3, 7.0)
                dx_m = rng.uniform(0.3, 1.0) * dist
                dy_m = (dist ** 2 - dx_m ** 2) ** 0.5 * rng.choice([-1, 1])
                fx, fy = x + dx_m / 1.05, y + dy_m / 0.68
            else:
                for _ in range(20):  # keep the first defender the nearest one
                    t = rng.uniform(0.2, 0.9)
                    fx = clamp(x + (100 - x) * t + rng.gauss(0, 2))
                    fy = clamp(y + (50 - y) * t + rng.gauss(0, 6))
                    if to_m(fx - x, fy - y) > dist + 0.3:
                        break
                else:
                    continue
            frame.append(FreezeFramePlayer(x=round(clamp(fx), 1), y=round(clamp(fy), 1),
                                           teammate=False, goalkeeper=False))
        for _ in range(rng.choice([0, 1, 1, 2])):
            frame.append(FreezeFramePlayer(x=round(clamp(rng.uniform(85, 97)), 1),
                                           y=round(clamp(rng.uniform(30, 70)), 1),
                                           teammate=True, goalkeeper=False))
        return frame

    def _shot(self, team: str, shooter: str, x: float, y: float, key_pass: PassEvent | None,
              from_cross: bool, shot_type: str = "open_play",
              forced: ScriptedShot | None = None) -> Restart:
        rng = self.rng
        opp = self._opp(team)
        x, y = round(x, 1), round(y, 1)  # as published, so derived fields match the feed
        header = False
        if forced:
            header = forced.body_part == "head"
        elif from_cross and in_box(x, y) and rng.random() < 0.72:
            header = True
            shooter = self._pick(team, x, y, shooter=True, header=True)
        prof = self.profiles[shooter]
        player = self.players[shooter]
        d = goal_distance_m(x, y)
        if shot_type == "penalty":
            intent = False
        else:
            intent = forced.under_pressure if forced else rng.random() < (
                0.38 if in_box(x, y) else 0.25)
        frame = self._freeze_frame(x, y, intent)
        # Under pressure means a defender within 2.3 m in the frame, as an analyst would derive it.
        pressured = shot_type != "penalty" and min(
            to_m(p.x - x, p.y - y) for p in frame if not p.teammate and not p.goalkeeper) < 2.3

        strong = "left_foot" if player.preferred_foot == "left" else "right_foot"
        weak = "right_foot" if strong == "left_foot" else "left_foot"
        if forced:
            body_part = forced.body_part
        elif header:
            body_part = "head"
        else:
            body_part = strong if rng.random() < 0.8 else ("other" if rng.random() < 0.03
                                                             else weak)
        first_time = bool(key_pass) and rng.random() < (0.7 if from_cross else 0.3)
        if header:
            technique = "diving_header" if rng.random() < 0.06 else "normal"
        elif from_cross and first_time:
            technique = rng.choice(["volley", "half_volley", "normal"])
        else:
            technique = "lob" if rng.random() < 0.012 else (
                "half_volley" if rng.random() < 0.06 else "normal")

        # ----- speed (km/h) -----
        if forced:
            speed = forced.speed_kmh
        elif header:
            speed = rng.gauss(46 + 14 * prof.header_skill, 6)
        elif technique == "lob":
            speed = rng.gauss(45, 7)
        else:
            mean = prof.shot_power_mean_kmh + 0.45 * (d - 16)
            if shot_type == "penalty":
                mean = prof.shot_power_mean_kmh - 2
            mean += {"volley": 2.0, "half_volley": 1.0}.get(technique, 0.0)
            mean -= 3.0 if first_time else 0.0
            if body_part == weak:
                mean *= prof.weak_foot_factor
            elif body_part == "other":
                mean *= 0.6
            if pressured:
                mean *= 1 - prof.pressure_sensitivity
            speed = rng.gauss(mean, prof.shot_power_sd_kmh)
        speed = round(max(25.0, min(132.0, speed)), 1)

        # ----- outcome and end location -----
        corner_ness = 0.0
        if forced:
            outcome = forced.outcome
        else:
            block_p = 0.0 if header or shot_type == "penalty" else (
                0.20 + 0.08 * pressured + 0.06 * (d > 18))
            on_p = (0.47 + 0.3 * (prof.placement_skill - 0.5) - 0.012 * (d - 11)
                    - 0.08 * pressured - 0.06 * header - 0.08 * (body_part == weak))
            if shot_type == "penalty":
                on_p = 0.82
            r = rng.random()
            if r < block_p:
                outcome = "blocked"
            elif rng.random() < max(0.08, on_p):
                corner_ness = min(0.98, rng.betavariate(1 + 3 * prof.placement_skill, 1.6))
                logit = (-2.45 + 0.035 * (speed - 75) + 2.4 * corner_ness - 0.06 * (d - 12)
                         - 0.3 * header)
                goal_p = 0.76 if shot_type == "penalty" else 1 / (1 + exp(-logit))
                outcome = "goal" if rng.random() < goal_p else "saved"
                if self.m.is_live_demo:  # only scripted beats score: the demo story stays fixed
                    outcome = "saved"
            else:
                outcome = "post" if rng.random() < 0.06 else "off_target"

        half_goal = (GOAL_WIDTH_M / 2) / PITCH_WIDTH_M * 100
        if forced:
            end_x, end_y, end_z = 100.0, forced.end_y, forced.end_z
        elif outcome == "blocked":
            t = rng.uniform(1.5, 5.0) / max(d, 2)
            end_x, end_y, end_z = x + (100 - x) * t, y + (50 - y) * t, rng.uniform(0.1, 1.2)
        elif outcome in ("goal", "saved"):
            side = rng.choice([-1, 1])
            end_x = 100.0
            end_y = 50 + side * half_goal * max(0.05, corner_ness)
            end_z = (rng.uniform(1.4, 2.3) if rng.random() < 0.4 else rng.uniform(0.05, 0.9))
            if header:
                end_z = rng.uniform(0.1, 1.6)
        elif outcome == "post":
            end_x, end_y = 100.0, rng.choice([POST_LOW_Y, POST_HIGH_Y])
            end_z = rng.uniform(0.1, GOAL_HEIGHT_M)
        else:
            end_x = 100.0
            if rng.random() < 0.45:  # over the bar
                end_y, end_z = rng.uniform(POST_LOW_Y - 2, POST_HIGH_Y + 2), rng.uniform(2.6, 6)
            else:  # wide
                side = rng.choice([-1, 1])
                end_y, end_z = 50 + side * (half_goal + rng.uniform(0.5, 9)), rng.uniform(0, 2.2)

        shot = self._emit(
            ShotEvent, team=team, player=shooter, x=x, y=y, under_pressure=pressured,
            duration_ms=rng.randint(250, 600),
            related_event_ids=[key_pass.event_id] if key_pass else [],
            body_part=body_part, technique=technique, shot_type=shot_type,
            first_time=first_time, deflected=outcome != "blocked" and rng.random() < 0.04,
            end_x=round(end_x, 1), end_y=round(end_y, 1), end_z=round(end_z, 2),
            outcome=outcome, key_pass_event_id=key_pass.event_id if key_pass else None,
            freeze_frame=frame,
            tracking=ShotTracking(shot_speed_kmh=speed),
        )

        if forced and forced.var_cancel:
            return self._var_cancel(shot, team)
        if outcome == "goal":
            self._advance(50_000, 80_000)
            return Restart(opp, 50, 50, "from_kick_off", "kick_off")
        if outcome in ("saved", "blocked") and rng.random() < (0.3 if outcome == "saved"
                                                               else 0.4):
            self._advance(20_000, 35_000)
            return Restart(team, 99.5, 0.5, "from_corner", "corner")
        if outcome == "saved":
            self._advance(4_000, 10_000)
            return Restart(opp, 6, 50, "regular_play", carrier=self._pick(opp, 6, 50, keeper=True))
        if outcome == "blocked":
            mx, my = mirror(clamp(end_x), clamp(end_y))
            winner = self._pick(opp, mx, my)
            self._emit(BallRecoveryEvent, team=opp, player=winner, x=mx, y=my,
                       recovery_failure=False)
            self._advance(500, 1500)
            return Restart(opp, mx, my, "regular_play", carrier=winner)
        self._advance(15_000, 30_000)
        return Restart(opp, 6, 50, "from_goal_kick", "goal_kick")

    def _var_cancel(self, shot: ShotEvent, team: str) -> Restart:
        """VAR overturns the goal: review start, review end, then a v2 of the shot."""
        self._advance(25_000, 30_000)
        self._emit(VarReviewStartEvent, review_subject="goal", related_event_ids=[shot.event_id])
        self._advance(70_000, 85_000)
        end = self._emit(VarReviewEndEvent, outcome="no_goal",
                         related_event_ids=[shot.event_id])
        corrected = shot.model_copy(update={"outcome": "off_target"})
        self.updates.append(PendingUpdate(emit_at=end.event_time + timedelta(seconds=1.2),
                                          event=corrected))
        self._advance(15_000, 25_000)
        opp = self._opp(team)
        return Restart(opp, 12, 50, "from_free_kick", "free_kick")

    def _scripted(self, beat: ScriptedShot, team: str, x: float, y: float) -> Restart:
        """Bring the ball to the beat's shooter and play the pinned shot on time."""
        shooter_team = self.players[beat.player_id].club_id
        if team != shooter_team:
            x, y = mirror(x, y)
            winner = self._pick(shooter_team, x, y, exclude=beat.player_id)
            self._emit(BallRecoveryEvent, team=shooter_team, player=winner, x=x, y=y,
                       recovery_failure=False)
            self._new_possession(shooter_team, "regular_play")
            self._advance(800, 1500)
        else:
            winner = self._pick(shooter_team, x, y, exclude=beat.player_id)
        self.clock = max(self.clock, beat.clock_ms - BEAT_BUILDUP_MS)
        mid_x, mid_y = (x + beat.x) / 2, (y + beat.y) / 2
        carriers = [(winner, x, y, mid_x, mid_y), (None, mid_x, mid_y, beat.x, beat.y)]
        last: PassEvent | None = None
        for i, (passer, sx, sy, ex, ey) in enumerate(carriers):
            self.clock = max(self.clock, beat.clock_ms - (6_000 if i == 0 else 3_000))
            passer = passer or last.recipient_id
            recipient = beat.player_id if i == 1 else self._pick(
                shooter_team, ex, ey, exclude=beat.player_id)
            if passer == recipient:
                recipient = self._pick(shooter_team, ex, ey, exclude=passer)
            length = to_m(ex - sx, ey - sy)
            last = self._emit(
                PassEvent, team=shooter_team, player=passer, x=sx, y=sy,
                duration_ms=int(length / 13 * 1000), recipient_id=recipient,
                end_x=round(ex, 1), end_y=round(ey, 1), length_m=round(length, 1),
                height="ground", pass_type="open_play", cross=False, through_ball=False,
                outcome="complete", tracking=PassTracking(ball_speed_kmh=round(
                    self.rng.gauss(45, 6), 1)),
            )
        self.clock = max(self.clock, beat.clock_ms)
        return self._shot(shooter_team, beat.player_id, beat.x, beat.y, last, False,
                          forced=beat)
