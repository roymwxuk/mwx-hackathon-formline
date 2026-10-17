import pytest

from formline.engine.log import current_events
from formline.generator.season import generate_season
from formline.tracking.anchors import anchor_speeds, event_anchors


@pytest.fixture(scope="module")
def live():
    season = generate_season(2026)
    gm = next(g for g in season.matches if g.match.is_live_demo)
    players = {p.player_id: p for p in season.league.players}
    events = current_events(gm.feed)
    anchors = event_anchors(events, gm.match.home_club_id, players, season.league.starters)
    return season, gm, players, events, anchors


def test_every_pass_pins_its_passer_and_receiver(live):
    _, _, _, events, anchors = live
    subbed_off = {}
    for e in events:
        if e.type == "substitution":
            subbed_off[e.player_off_id] = (e.period, e.match_clock_ms)
    kinds = {}
    for a in anchors:
        kinds.setdefault(a.event_id, []).append(a)
    passes = [e for e in events if e.type == "pass"]
    skipped = [p for p in passes if p.event_id not in kinds]
    # Only actions by players already substituted off are skipped (one generator quirk).
    assert len(skipped) <= 1
    assert all(subbed_off.get(p.player_id, (9, 0)) < (p.period, p.match_clock_ms) for p in skipped)
    for p in passes:
        if p in skipped:
            continue
        got = kinds[p.event_id]
        assert any(a.kind == "passer" and a.t_ms == p.match_clock_ms for a in got)
        receiver = [a for a in got if a.kind == "receiver"]
        if p.recipient_id:
            assert receiver and receiver[0].t_ms == p.match_clock_ms + (p.duration_ms or 0)


def test_spots_are_in_the_shared_frame(live):
    _, gm, _, events, anchors = live
    by_id = {e.event_id: e for e in events}
    for a in anchors:
        assert 0 <= a.x <= 100 and 0 <= a.y <= 100
        if a.kind == "passer":
            e = by_id[a.event_id]
            home = e.team_id == gm.match.home_club_id
            assert (a.x, a.y) == ((e.x, e.y) if home else (100 - e.x, 100 - e.y))


def test_anchors_name_players_on_the_pitch(live):
    season, gm, players, events, anchors = live
    on = {club: {players[p].shirt_number for p in xi} for club, xi in season.league.starters.items()}
    home = gm.match.home_club_id
    away = next(c for c in on if c != home)
    changes = sorted(((e.period, e.match_clock_ms), e) for e in events if e.type == "substitution")
    for a in sorted(anchors, key=lambda a: (a.period, a.t_ms)):
        while changes and changes[0][0] <= (a.period, a.t_ms):
            _, sub = changes.pop(0)
            on[sub.team_id].discard(players[sub.player_off_id].shirt_number)
            on[sub.team_id].add(players[sub.player_on_id].shirt_number)
        assert a.shirt in on[home if a.home else away], a


def test_freeze_frames_go_to_distinct_real_players(live):
    _, _, _, events, anchors = live
    shots = [e for e in events if e.type == "shot"]
    for s in shots:
        frame = [a for a in anchors if a.event_id == s.event_id and a.kind in ("freeze_frame", "keeper")]
        assert len(frame) == len(s.freeze_frame or [])
        shooter = next(a for a in anchors if a.event_id == s.event_id and a.kind == "shooter")
        people = {(a.home, a.shirt) for a in frame} | {(shooter.home, shooter.shirt)}
        assert len(people) == len(frame) + 1  # nobody used twice, never the shooter
        keeper = [a for a in frame if a.kind == "keeper"]
        assert len(keeper) == 1 and keeper[0].home != shooter.home and keeper[0].shirt in (1, 13)


def test_anchors_are_reachable_at_human_speeds(live):
    speeds = sorted(anchor_speeds(live[4]))
    p99 = speeds[int(0.99 * (len(speeds) - 1))]
    assert p99 < 8.0  # m/s; elite sprints top out around 10
    assert sum(v > 9.5 for v in speeds) / len(speeds) < 0.01  # rare; the motion model softens these
