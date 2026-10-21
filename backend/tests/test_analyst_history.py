"""History questions: season leaders and a player's or a team's last 1–5 games, computed
from the past matches (no generator change), answered and verified like any typed question."""

import asyncio

import pytest

from formline.agents.fakes import FakeAgents
from formline.agents.llm import LLMConfig, make_runner
from formline.agents.verifier import league_names
from formline.analyst.ask import answer_free, known_events
from formline.analyst.followups import Moment, moment_kind
from formline.analyst.router import check_route
from formline.analyst.sections import facts_for
from formline.analyst.store import MatchContext, history_rows, player_season_stats
from formline.analyst.verify import AnswerContext, verify_answer
from formline.analyst.writer import AnalystWriter, write_comments
from formline.engine.log import current_events
from formline.generator.season import generate_season

REYNER = "ply_0107"


@pytest.fixture(scope="module")
def match():
    season = generate_season(2026)
    gm = next(g for g in season.matches if g.match.is_live_demo)
    players = {p.player_id: p for p in season.league.players}
    clubs = {c.club_id: c.name for c in season.league.clubs}
    short = {c.club_id: c.short_name for c in season.league.clubs}
    past = [(g.match.model_dump(), current_events(g.feed)) for g in season.matches
            if not g.match.is_live_demo]
    ctx = MatchContext(league_names(season.league.players, season.league.clubs), players, clubs,
                       gm.match.home_club_id, gm.match.away_club_id,
                       info=gm.match.model_dump(),
                       player_seasons=player_season_stats(e for _, e in past),
                       history=history_rows(past))
    w = AnalystWriter(make_runner(LLMConfig(), fake_responder=FakeAgents()), ctx.league,
                      ctx.players, ctx.clubs, ctx.home, ctx.away)
    rows = asyncio.run(write_comments(gm.feed, w))
    goal = next(c for _, c in rows if c.get("goal") and c["lang"] == "en"
                and c["match_clock_ms"] // 1000 == 22 * 60 + 30)
    return gm, ctx, goal, short


def ask(match, text, lang="en"):
    gm, ctx, goal, short = match
    runner = make_runner(LLMConfig(), fake_responder=FakeAgents())
    return asyncio.run(answer_free(moment_kind(goal["ask"]["moment"])[1], 1, text, lang,
                                   gm.feed, ctx, runner, short_names=short))


def moment(match) -> Moment:
    gm, ctx, goal, _ = match
    kind, eid = moment_kind(goal["ask"]["moment"])
    known = known_events(gm.feed, goal["ask"]["seq"])
    return Moment(kind, known[eid], sorted(known.values(), key=lambda e: (e.period, e.match_clock_ms)),
                  known[eid].player_id, ctx.home, ctx.away, ctx.clubs, ctx.players)


def test_history_rows_agree_with_the_season_stats(match):
    _, ctx, _, _ = match
    rows = ctx.history
    assert len(rows) == 30 and rows == sorted(rows, key=lambda r: r["kickoff_at"])
    for pid, season in ctx.player_seasons.items():
        assert sum(r["players"].get(pid, {}).get("goals", 0) for r in rows) == season["goals"]
        assert sum(pid in r["players"] for r in rows) == season["appearances"]
    for r in rows:
        assert r["home_goals"] + r["away_goals"] == len(r["scorers"])


def test_top_scorer_for_each_team(match):
    """Reported: "top score getter in this season for these two teams" was declined."""
    _, ctx, _, _ = match
    out = ask(match, "top score getter in this season for these two teams")
    assert out["retrieved"]["sections"][0] == "season_leaders" and out["answer"]["verified"]
    pack = facts_for(["season_leaders"], moment(match), seasons=ctx.player_seasons)
    facts = pack.facts["season_leaders"]
    for side, club in (("home", ctx.home), ("away", ctx.away)):
        squad = [pid for pid, p in ctx.players.items() if p.club_id == club]
        best = max(ctx.player_seasons.get(pid, {}).get("goals", 0) for pid in squad)
        leaders = {pid for pid in squad if ctx.player_seasons.get(pid, {}).get("goals", 0) == best}
        named = {pid for role, pid in pack.roles.items() if role in facts[f"{side}_top_scorer"]}
        assert named == leaders and f"with {best} goal(s)" in facts[f"{side}_top_scorer"]


def test_a_players_last_three_games(match):
    """Reported: "what was player-A's performance last 3 games" should be answered."""
    _, ctx, _, _ = match
    out = ask(match, "what was Reyner's performance last 3 games?")
    assert out["retrieved"]["sections"] == ["player_recent"]
    assert out["retrieved"]["player_id"] == REYNER and out["retrieved"]["label"] == "Reyner: last 3 games"
    facts = facts_for(["player_recent"], moment(match), player_id=REYNER, history=ctx.history,
                      n=3).facts["player_recent"]
    games = [r for r in ctx.history if REYNER in r["players"]][-3:]
    assert facts["games"].count(" against ") == 3
    goals = sum(r["players"][REYNER]["goals"] for r in games)
    assert facts["totals"].startswith(f"over these 3 game(s): {goals} goal(s)")
    ja = ask(match, "レイナーの直近3試合は？", "ja")
    assert ja["retrieved"]["label"] == "レイナーの直近3試合"


def test_past_opponents_named_in_facts_pass_the_verifier(match):
    """Eval a37_07: opponents from a player's last games were rejected as clubs not in this
    match, so the answer fell back to a template without them."""
    _, ctx, _, _ = match
    pack = facts_for(["player_recent"], moment(match), player_id=REYNER, history=ctx.history, n=3)
    games = [r for r in ctx.history if REYNER in r["players"]][-3:]
    opponents = {r["away"] if r["home"] == ctx.home else r["home"] for r in games} - {ctx.home, ctx.away}
    assert opponents, "the fixture needs a past opponent outside tonight's match"
    named = ctx.clubs[next(iter(opponents))]
    actx = AnswerContext(pack, "en", (ctx.home, ctx.away), free=True)
    ok = {"headline": "Reyner's last three games", "body": f"He played {named}.", "coverage": "full"}
    assert verify_answer(ok, actx, ctx.league).ok, verify_answer(ok, actx, ctx.league).failures
    absent = next(name for cid, name in ctx.clubs.items()
                  if cid not in (ctx.home, ctx.away) and name not in str(pack.facts))
    bad = {**ok, "body": f"He played {absent}."}
    assert "entities" in {f.check for f in verify_answer(bad, actx, ctx.league).failures}


def test_a_teams_last_five_games(match):
    _, ctx, _, _ = match
    out = ask(match, "Northgate's last 5 games?")
    assert out["retrieved"]["sections"] == ["team_recent"] and out["retrieved"]["club_id"] == ctx.away
    facts = facts_for(["team_recent"], moment(match), club_id=ctx.away, history=ctx.history,
                      n=5).facts["team_recent"]
    games = [r for r in ctx.history if ctx.away in (r["home"], r["away"])][-5:]
    won = sum((r["home_goals"] > r["away_goals"]) == (r["home"] == ctx.away)
              and r["home_goals"] != r["away_goals"] for r in games)
    assert facts["games"].count(" against ") == 5 and f"{won} won" in facts["totals"]


def test_the_number_of_games_and_the_subject_are_checked(match):
    m = moment(match)
    elsewhere = next(pid for pid, p in match[1].players.items() if p.club_id not in (m.home, m.away))
    ok = {"sections": ["player_recent"], "player_id": REYNER, "n": 3}
    assert check_route(ok, m) is None
    assert check_route({"sections": ["player_recent"], "player_id": REYNER}, m) is None  # n defaults to 3
    for bad_n in (0, 6, "3", True, 2.5):
        assert "n must be" in check_route({**ok, "n": bad_n}, m), bad_n
    assert "PLAYERS" in check_route({**ok, "player_id": elsewhere}, m)
    assert "club_id" in check_route({"sections": ["team_recent"], "club_id": "clb_nope", "n": 2}, m)
