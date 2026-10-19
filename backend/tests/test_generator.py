import asyncio
import json
from collections import Counter
from datetime import date
from math import hypot

import pytest

from formline.generator.output import read_feed, write_season
from formline.generator.report import compute, latest_events
from formline.generator.season import generate_season
from formline.replay import replay, to_stream_message
from formline.schema.feed import FeedMessage

SEED = 2026


@pytest.fixture(scope="module")
def season():
    return generate_season(SEED)


@pytest.fixture(scope="module")
def data_dir(season, tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    write_season(season, out)
    return out


def live(season):
    return next(m for m in season.matches if m.match.is_live_demo)


def dumps(feed: list[FeedMessage]) -> list[str]:
    return [m.model_dump_json() for m in feed]


# ---------- reproducibility ----------

def test_same_seed_same_season(season):
    again = generate_season(SEED)
    assert [m.match.match_id for m in again.matches] == [m.match.match_id for m in season.matches]
    for a, b in zip(again.matches, season.matches, strict=True):
        assert dumps(a.feed) == dumps(b.feed)


def test_different_seed_differs(season):
    other = generate_season(SEED + 1)
    assert dumps(other.matches[0].feed) != dumps(season.matches[0].feed)


# ---------- league ----------

def test_league_shape(season):
    league = season.league
    assert len(league.clubs) == 6
    assert all(len(league.squad(c.club_id)) == 18 for c in league.clubs)
    assert all(len(xi) == 11 for xi in league.starters.values())
    names = [p.display_name for p in league.players]
    assert len(names) == len(set(names))
    by_id = {p.player_id: p.display_name for p in league.players}
    assert by_id["ply_0107"] == "Tomas Reyner" and by_id["ply_0210"] == "Daniel Okafor"
    for club in league.clubs:
        squad = league.squad(club.club_id)
        numbers = [p.shirt_number for p in squad]
        assert len(numbers) == len(set(numbers))
        surnames = [p.display_name.split()[-1] for p in squad]
        assert len(surnames) == len(set(surnames)), club.name


def test_every_public_profile_survives_generation_and_disk_roundtrip(season, data_dir):
    from formline.agents.precompute import load_league
    from formline.schema.biography import COUNTRIES, PLACES, synthetic_biography

    raw = json.loads((data_dir / "league.json").read_text())
    players, clubs = load_league(data_dir)
    assert len(raw["players"]) == len(players) == 108
    assert {c.club_id for c in clubs} == {c.club_id for c in season.league.clubs}
    for generated, stored, loaded in zip(season.league.players, raw["players"], players, strict=True):
        assert loaded == generated
        assert generated.display_name and generated.display_name_ja
        assert generated.club_id and generated.position and generated.position_group
        assert generated.shirt_number > 0 and generated.preferred_foot in ("left", "right")
        assert generated.nationality in COUNTRIES
        assert date(1990, 1, 1) <= generated.date_of_birth <= date(2007, 12, 31)
        city, country = generated.birthplace.split(", ")
        assert city in PLACES[country]
        assert stored["date_of_birth"] == generated.date_of_birth.isoformat()
        assert stored["nationality"] == generated.nationality
        assert stored["birthplace"] == generated.birthplace
        assert synthetic_biography(generated.player_id) == {
            "nationality": generated.nationality, "date_of_birth": generated.date_of_birth,
            "birthplace": generated.birthplace}


def test_season_is_double_round_robin(season):
    history = [m.match for m in season.matches if not m.match.is_live_demo]
    assert len(history) == 30
    pairs = Counter((m.home_club_id, m.away_club_id) for m in history)
    assert all(n == 1 for n in pairs.values()) and len(pairs) == 30


# ---------- feed integrity ----------

def test_feed_round_trips_through_json(data_dir, season):
    for gm in season.matches[:3]:
        assert dumps(read_feed(data_dir / "feeds" / f"{gm.match.match_id}.jsonl")) == dumps(gm.feed)


def test_event_ids_unique_and_feed_ordered(season):
    ids = Counter()
    for gm in season.matches:
        seqs = [m.sequence for m in gm.feed]
        assert seqs == list(range(1, len(seqs) + 1))
        emitted = [m.emitted_at for m in gm.feed]
        assert emitted == sorted(emitted)
        ids.update(m.event_id for m in gm.feed if m.op == "create")
    assert max(ids.values()) == 1


def test_locations_and_freeze_frames_are_valid(season):
    for gm in season.matches:
        for msg in gm.feed:
            e = msg.event
            if e.x is not None:
                assert 0 <= e.x <= 100 and 0 <= e.y <= 100
            if e.type != "shot":
                continue
            keepers = [p for p in e.freeze_frame if p.goalkeeper]
            assert len(keepers) == 1
            defenders = [p for p in e.freeze_frame if not p.teammate and not p.goalkeeper]
            nearest = min(hypot((p.x - e.x) * 1.05, (p.y - e.y) * 0.68) for p in defenders)
            assert (nearest < 2.3) == e.under_pressure or e.shot_type == "penalty"


# ---------- realism ----------

def test_realism_targets(data_dir):
    checks, extra = compute(data_dir)
    failed = [f"{c.metric}={c.value:.2f}" for c in checks if not c.ok]
    assert not failed
    assert extra["shooters_25"] >= 5  # enough regular shooters for stable baselines


# ---------- live demo match ----------

def test_live_match_hits_scripted_beats(season):
    feed = live(season).feed
    shots = {(m.event.player_id, m.event.match_clock_ms): m.event
             for m in feed if m.op == "create" and m.event.type == "shot"}
    slow = shots[("ply_0107", (40 * 60 + 12) * 1000)]
    assert slow.tracking.shot_speed_kmh == 84.1 and slow.under_pressure
    assert ("ply_0111", (22 * 60 + 30) * 1000) in shots


def test_live_match_var_cancels_goal(season):
    gm = live(season)
    feed = gm.feed
    update = next(m for m in feed if m.op == "update")
    assert update.version == 2 and update.event.outcome == "off_target"
    review_end = next(m for m in feed if m.event.type == "var_review_end")
    assert review_end.event.related_event_ids == [update.event_id]
    assert review_end.sequence < update.sequence
    original = next(m for m in feed if m.event_id == update.event_id and m.op == "create")
    assert original.event.outcome == "goal"

    events = latest_events(feed)
    goals = Counter(e.team_id for e in events if e.type == "shot" and e.outcome == "goal")
    assert goals == {gm.match.home_club_id: 1}


# ---------- replay ----------

def test_replay_yields_viewer_stream_messages(season):
    feed = live(season).feed[:50]

    async def collect():
        return [m async for m in replay(feed, speed=1e9)]

    out = asyncio.run(collect())
    assert [m.message_id for m in out] == [m.message_id for m in feed]
    msg = to_stream_message(out[0])
    assert msg["kind"] == "event"
    assert msg["event"]["version"] == 1 and msg["event"]["event_id"] == out[0].event_id


def test_match_conditions_are_plausible_and_do_not_change_the_events():
    from formline.generator.season import REFEREES, conditions

    season = generate_season(2026)
    for gm in season.matches:
        c = gm.match.conditions
        assert c is not None and 0.8 * c.capacity <= c.attendance <= c.capacity
        assert 0 <= c.temperature_c <= 22 and (c.referee, c.referee_ja) in REFEREES
        assert conditions(2026, gm.match) == c  # its own stream: deterministic per match
    live = next(g for g in season.matches if g.match.is_live_demo)
    assert live.match.conditions.weather and len(live.feed) > 1000
