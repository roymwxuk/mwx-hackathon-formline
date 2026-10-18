import asyncio
import json
from collections import Counter

import pytest

from formline.agents.fakes import FakeAgents
from formline.agents.llm import LLMConfig, make_runner
from formline.agents.verifier import league_names
from formline.analyst.agent import answer_verified
from formline.analyst.facts import shot_pack
from formline.analyst.verify import AnswerContext, verify_answer
from formline.analyst.writer import AnalystWriter, write_comments
from formline.engine.log import current_events
from formline.generator.season import generate_season


@pytest.fixture(scope="module")
def match():
    season = generate_season(2026)
    gm = next(g for g in season.matches if g.match.is_live_demo)
    players = {p.player_id: p for p in season.league.players}
    clubs = {c.club_id: c.name for c in season.league.clubs}
    league = league_names(season.league.players, season.league.clubs)
    return season, gm, players, clubs, league


def writer(match, responder=None):
    _, gm, players, clubs, league = match
    runner = make_runner(LLMConfig(), fake_responder=responder or FakeAgents())
    return AnalystWriter(runner, league, players, clubs, gm.match.home_club_id, gm.match.away_club_id)


@pytest.fixture(scope="module")
def comments(match):
    w = writer(match)
    return w, asyncio.run(write_comments(match[1].feed, w))


def test_a_comment_for_every_shot_corner_and_card_and_nothing_else(match, comments):
    _, gm, *_ = match
    w, rows = comments
    events = current_events(gm.feed)
    created = [m.event for m in gm.feed if m.op == "create" and m.event is not None]
    shots = sum(e.type == "shot" for e in created)
    corners = sum(e.type == "pass" and e.pass_type == "corner" for e in created)
    cards = sum(e.type == "card" for e in created)
    shown = Counter(c["question"] for _, c in rows if c["op"] == "show" and c["lang"] == "en")
    assert shown == {"shot_outcome": shots, "corner": corners, "card": cards, "var": 1}
    assert {c["lang"] for _, c in rows} == {"en", "ja"}
    assert all(c["verified"] and c["evidence"] for _, c in rows if c["op"] == "show")
    assert len(events) > 0 and w.summary["template"] == 0


def test_the_var_overturn_withdraws_the_goal_comments(comments):
    _, rows = comments
    goal = [c for _, c in rows if c["question"] == "shot_outcome" and "scored" in c["body"].lower()
            and c["lang"] == "en"]
    retracts = [c for _, c in rows if c["op"] == "retract"]
    assert len(retracts) == 2  # EN and JA
    assert {r["supersedes_comment_id"] for r in retracts} >= {g["comment_id"] for g in goal
                                                                if g["match_clock_ms"] // 1000 == 3822}
    var = [c for _, c in rows if c["question"] == "var" and c["lang"] == "en"]
    assert var and "1–0" in var[0]["body"]


def test_the_red_card_explains_the_second_yellow(comments):
    _, rows = comments
    red = next(c for _, c in rows if c["question"] == "card" and c["lang"] == "en"
               and "sent off" in c["headline"])
    assert "minute 14" in red["body"] and "10 men" in red["body"]
    assert "does not record who was fouled" in red["body"]  # an honest limit, not a guess


def test_shot_facts_come_from_the_engine(match):
    _, gm, players, clubs, _ = match
    events = sorted(current_events(gm.feed), key=lambda e: (e.period, e.match_clock_ms))
    goal = next(e for e in events if e.type == "shot" and e.match_clock_ms // 1000 == 3822)
    goal_v1 = goal.model_copy(update={"outcome": "goal"})  # as it was before the VAR review
    before = [goal_v1 if e.event_id == goal.event_id else e for e in events
              if (e.period, e.match_clock_ms) <= (goal.period, goal.match_clock_ms)]
    pack = shot_pack(goal_v1, before, players, clubs, gm.match.home_club_id, gm.match.away_club_id)
    assert pack.roles["SHOOTER"] == "ply_0107"
    assert pack.facts["distance"] == "16 m from goal" and pack.facts["shot_speed"] == "118 km/h"
    assert "model estimate" in pack.facts["chance_quality"]
    assert pack.facts["score_now"].endswith("2–0 Northgate Rovers")
    assert goal.event_id in pack.source_event_ids


def test_the_verifier_rejects_wrong_numbers_other_players_and_placeholders(match):
    _, gm, players, clubs, league = match
    events = sorted(current_events(gm.feed), key=lambda e: (e.period, e.match_clock_ms))
    shot = next(e for e in events if e.type == "shot")
    pack = shot_pack(shot, events, players, clubs, gm.match.home_club_id, gm.match.away_club_id)
    ctx = AnswerContext(pack, "en", (gm.match.home_club_id, gm.match.away_club_id))
    shooter = league.players[shot.player_id][0].split()[-1]
    other = next(en for pid, (en, _) in league.players.items()
                 if pid not in pack.roles.values() and en.split()[-1] != shooter).split()[-1]
    good = {"headline": f"{shooter}'s effort", "body": f"From {pack.facts['distance']}, a modest chance."}
    assert verify_answer(good, ctx, league).ok
    checks = {
        "numbers": {**good, "body": "From 99 m, a modest chance."},
        "entities": {**good, "body": f"{other} should have scored."},
        "jargon": {**good, "body": "SHOOTER took it early."},
        "certainty": {**good, "body": "He will score next time, definitely."},
        "estimates": {**good, "body": f"It had a {pack.facts['chance_quality'].split('%')[0]}% chance."},
    }
    for check, answer in checks.items():
        verdict = verify_answer(answer, ctx, league)
        assert not verdict.ok and check in {f.check for f in verdict.failures}, check


def test_a_misbehaving_model_falls_back_to_a_verified_template(match):
    _, gm, players, clubs, league = match
    events = sorted(current_events(gm.feed), key=lambda e: (e.period, e.match_clock_ms))
    shot = next(e for e in events if e.type == "shot")
    pack = shot_pack(shot, events, players, clubs, gm.match.home_club_id, gm.match.away_club_id)
    runner = make_runner(LLMConfig(), fake_responder=lambda texts: "not json at all")
    for lang in ("en", "ja"):
        a = asyncio.run(answer_verified(pack, lang, runner, league,
                                        (gm.match.home_club_id, gm.match.away_club_id)))
        assert a.source == "template" and a.attempts == 3 and a.headline


def test_comment_messages_are_json_ready(comments):
    _, rows = comments
    json.dumps([c for _, c in rows], ensure_ascii=False)
    ids = [c["comment_id"] for _, c in rows]
    assert len(ids) == len(set(ids))
