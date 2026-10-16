"""Season assembly: fixtures, the scripted live match, and feed envelopes."""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from formline.generator.league import League, build_league
from formline.generator.match_sim import MatchSim, PendingUpdate, ScriptedShot
from formline.schema.feed import FeedMessage
from formline.schema.reference import Match

SEASON = "2026-27"
SEASON_START = datetime(2026, 8, 15, 14, 0, tzinfo=UTC)
LIVE_KICKOFF = datetime(2026, 10, 24, 19, 0, tzinfo=UTC)


def _m(minute: int, second: int = 0) -> int:
    return (minute * 60 + second) * 1000


# The demo storyline for the live match (mirrors the UI mock): HAR vs NOR.
LIVE_SCRIPT = [
    ScriptedShot(_m(12, 5), "ply_0107", 82.5, 58.0, "saved", 101.2, end_y=53.4, end_z=1.9),
    ScriptedShot(_m(22, 30), "ply_0111", 88.0, 44.0, "goal", 94.0, end_y=46.0, end_z=0.4),
    ScriptedShot(_m(27, 52), "ply_0210", 93.0, 52.0, "saved", 62.0, body_part="head",
                 end_y=50.2, end_z=1.1),
    ScriptedShot(_m(40, 12), "ply_0107", 84.2, 41.0, "saved", 84.1, under_pressure=True,
                 end_y=47.2, end_z=0.6),
    ScriptedShot(_m(63, 42), "ply_0107", 87.0, 61.0, "goal", 118.3, end_y=52.5, end_z=1.7,
                 var_cancel=True),
    ScriptedShot(_m(78, 20), "ply_0208", 76.0, 35.0, "off_target", 79.0, end_y=30.0,
                 end_z=1.0),
]


@dataclass
class GeneratedMatch:
    match: Match
    feed: list[FeedMessage]


@dataclass
class Season:
    league: League
    matches: list[GeneratedMatch]


def _match_id(matchday: int, home: str, away: str) -> str:
    return f"mtc_s26_md{matchday:02d}_{home}_{away}"


def fixtures(league: League) -> list[tuple[int, str, str]]:
    """Double round robin (circle method): (matchday, home_club_id, away_club_id)."""
    ids = [c.club_id for c in league.clubs]
    n = len(ids)
    rounds = []
    rotation = ids[:]
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = rotation[i], rotation[n - 1 - i]
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        rounds.append(pairs)
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    second_leg = [[(b, a) for a, b in pairs] for pairs in rounds]
    return [(md, h, a) for md, pairs in enumerate(rounds + second_leg, start=1)
            for h, a in pairs]


def build_feed(match_no: int, events: list, updates: list[PendingUpdate],
               rng: random.Random) -> list[FeedMessage]:
    """Wrap events as a clean provider feed: create per event, update per correction.

    Emission lags the action by a small latency; the file is in emission order.
    """
    staged: list[tuple[datetime, str, int, object]] = []
    for event in sorted(events, key=lambda e: e.event_time):
        lag = timedelta(milliseconds=rng.randint(250, 900))
        staged.append((event.event_time + lag, "create", 1, event))
    for upd in updates:
        staged.append((upd.emit_at, "update", 2, upd.event))
    staged.sort(key=lambda s: s[0])
    return [
        FeedMessage(message_id=f"msg_{match_no:02d}{seq:05d}", op=op, event_id=event.event_id,
                    version=version, emitted_at=emitted, sequence=seq, event=event)
        for seq, (emitted, op, version, event) in enumerate(staged, start=1)
    ]


def generate_season(seed: int) -> Season:
    league = build_league(seed)
    short = {c.club_id: c.short_name.lower() for c in league.clubs}
    matches: list[GeneratedMatch] = []
    plan = fixtures(league)
    for match_no, (md, home, away) in enumerate(plan, start=1):
        kickoff = SEASON_START + timedelta(weeks=md - 1, hours=(match_no - 1) % 3 * 2.5)
        matches.append(_play(league, seed, match_no, Match(
            match_id=_match_id(md, short[home], short[away]), season=SEASON, matchday=md,
            kickoff_at=kickoff, home_club_id=home, away_club_id=away,
            venue=league.venues[home], is_live_demo=False)))

    live_md = plan[-1][0] + 1
    home, away = "clb_harbourside", "clb_northgate"
    live = Match(match_id=_match_id(live_md, short[home], short[away]), season=SEASON,
                 matchday=live_md, kickoff_at=LIVE_KICKOFF, home_club_id=home,
                 away_club_id=away, venue=league.venues[home], is_live_demo=True)
    matches.append(_play(league, seed, len(plan) + 1, live, LIVE_SCRIPT))
    return Season(league=league, matches=matches)


def _play(league: League, seed: int, match_no: int, match: Match,
          script: list[ScriptedShot] | None = None) -> GeneratedMatch:
    events, updates = MatchSim(match, league, match_no, seed, script).run()
    rng = random.Random(f"{seed}:{match.match_id}:feed")
    return GeneratedMatch(match=match, feed=build_feed(match_no, events, updates, rng))
