"""Stage a: synthetic, football-realistic match event generator."""

import random
from collections.abc import Iterator

from formline.models import EventType, MatchEvent

TEAMS = {
    "Northbridge FC": ["Okafor", "Lindqvist", "Ramos", "Haddad", "Whitaker", "Mensah"],
    "Southvale United": ["Kowalski", "Bennett", "Tanaka", "Diallo", "Ferreira", "Moreau"],
}


def generate_match(match_id: str = "demo-001", seed: int | None = 42) -> Iterator[MatchEvent]:
    rng = random.Random(seed)
    teams = list(TEAMS)
    team = teams[0]
    eid = 0
    yield MatchEvent(id=eid, match_id=match_id, minute=0, second=0,
                     type=EventType.KICKOFF, team=team, x=50, y=50)
    clock = 0
    x, y = 50.0, 50.0
    while clock < 90 * 60:
        clock += rng.randint(2, 12)
        eid += 1
        player = rng.choice(TEAMS[team])
        roll = rng.random()
        attack = x if team == teams[0] else 100 - x
        if roll < 0.04 and attack > 65:
            goal = rng.random() < 0.12
            ev_type = EventType.GOAL if goal else EventType.SHOT
            yield MatchEvent(id=eid, match_id=match_id, minute=clock // 60, second=clock % 60,
                             type=ev_type, team=team, player=player, x=x, y=y,
                             outcome="success" if goal else "fail",
                             speed_kmh=round(rng.uniform(60, 120), 1))
            team, x, y = teams[1 - teams.index(team)], 50.0, 50.0
        elif roll < 0.12:
            other = teams[1 - teams.index(team)]
            yield MatchEvent(id=eid, match_id=match_id, minute=clock // 60, second=clock % 60,
                             type=EventType.TACKLE, team=other,
                             player=rng.choice(TEAMS[other]), x=x, y=y, outcome="success")
            team = other
        elif roll < 0.20:
            other = teams[1 - teams.index(team)]
            yield MatchEvent(id=eid, match_id=match_id, minute=clock // 60, second=clock % 60,
                             type=EventType.PRESSURE, team=other,
                             player=rng.choice(TEAMS[other]), x=x, y=y)
        else:
            direction = 1 if team == teams[0] else -1
            ex = min(100, max(0, x + direction * rng.uniform(-5, 20)))
            ey = min(100, max(0, y + rng.uniform(-20, 20)))
            ok = rng.random() < 0.82
            yield MatchEvent(id=eid, match_id=match_id, minute=clock // 60, second=clock % 60,
                             type=EventType.PASS, team=team, player=player, x=x, y=y,
                             end_x=ex, end_y=ey, outcome="success" if ok else "fail",
                             speed_kmh=round(rng.uniform(25, 70), 1))
            x, y = ex, ey
            if not ok:
                team = teams[1 - teams.index(team)]
    eid += 1
    yield MatchEvent(id=eid, match_id=match_id, minute=90, second=0,
                     type=EventType.FULL_TIME, team=team, x=50, y=50)
