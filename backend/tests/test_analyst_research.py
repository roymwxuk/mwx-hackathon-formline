"""The Researcher under adversarial scripts, through the real Agent Framework tool loop.

From Codex's review (private/researcher-plan-review.md): chaining must use the id a tool
returned; bad arguments add no facts; the call limit holds inside one parallel batch; every
model round-trip is charged; repeated lookups survive; failures fall back to the Router
with reserved budget; the name check runs first; errors never reach the Analyst.
"""

import asyncio
import json

import pytest

from formline.agents.fakes import FakeAgents
from formline.agents.llm import BudgetExceeded, LLMConfig, make_runner
from formline.agents.verifier import league_names
from formline.analyst import ask as ask_module
from formline.analyst import tools as tools_module
from formline.analyst.ask import answer_free, known_events
from formline.analyst.followups import Moment, _Roles, moment_kind
from formline.analyst.researcher import ResearchFailed, research
from formline.analyst.sections import season_leaders
from formline.analyst.store import MatchContext, history_rows, player_season_stats
from formline.analyst.tools import MAX_TOOL_CALLS, ResearchSession
from formline.analyst.writer import AnalystWriter, write_comments
from formline.engine.log import current_events
from formline.generator.season import generate_season

REYNER, ITO = "ply_0107", "ply_0111"
SHORT = {"clb_harbourside": "HAR", "clb_northgate": "NOR"}


@pytest.fixture(scope="module")
def match():
    season = generate_season(2026)
    gm = next(g for g in season.matches if g.match.is_live_demo)
    past = [(g.match.model_dump(), current_events(g.feed)) for g in season.matches
            if not g.match.is_live_demo]
    ctx = MatchContext(league_names(season.league.players, season.league.clubs),
                       {p.player_id: p for p in season.league.players},
                       {c.club_id: c.name for c in season.league.clubs},
                       gm.match.home_club_id, gm.match.away_club_id, info=gm.match.model_dump(),
                       player_seasons=player_season_stats(e for _, e in past),
                       history=history_rows(past))
    w = AnalystWriter(make_runner(LLMConfig(), fake_responder=FakeAgents()), ctx.league,
                      ctx.players, ctx.clubs, ctx.home, ctx.away)
    rows = asyncio.run(write_comments(gm.feed, w))
    goal = next(c for _, c in rows if c.get("goal") and c["lang"] == "en"
                and c["match_clock_ms"] // 1000 == 22 * 60 + 30)
    kind, eid = moment_kind(goal["ask"]["moment"])
    known = known_events(gm.feed, goal["ask"]["seq"])
    m = Moment(kind, known[eid], sorted(known.values(), key=lambda e: (e.period, e.match_clock_ms)),
               known[eid].player_id, ctx.home, ctx.away, ctx.clubs, ctx.players)
    return gm, ctx, m, eid


class Script:
    """Single-turn agents as the normal fake; the Researcher follows `turns`: a function
    (turn, tool results so far) -> tool calls or the final text."""

    def __init__(self, turns):
        self.fake, self.turns = FakeAgents(), turns

    def __call__(self, texts):
        return self.fake(texts)

    def research(self, turn, seen):
        results = [json.loads(t) for _, kind, t in seen if kind == "function_result"]
        return self.turns(turn, results)


def runner_for(turns, max_calls: int = 600):
    return make_runner(LLMConfig(max_calls=max_calls), fake_responder=Script(turns))


def run(match, turns, text="tell me something", runner=None):
    _, ctx, m, _ = match
    return asyncio.run(research(text, "en", m, ctx, runner or runner_for(turns), SHORT))


def free(match, text, runner):
    gm, ctx, _, eid = match
    return asyncio.run(answer_free(eid, 1, text, "en", gm.feed, ctx, runner, short_names=SHORT))


# ---------- chaining ----------

def test_chaining_uses_the_id_the_first_tool_returned(match, monkeypatch):
    """The first result names Ito as top scorer (not the real Reyner): the second call must
    use the returned id, so the agent really reads what it looked up."""
    def leaders_with_ito(m, roles, seasons):
        return {"home_top_scorer": f"top scorer: {roles('PLAYER', ITO)} with 9 goal(s)"}, []
    monkeypatch.setattr(tools_module, "season_leaders", leaders_with_ito)

    def turns(turn, results):
        if turn == 1:
            return [("get_season_leaders", {})]
        if turn == 2:
            role = next(r for r in results[-1]["players"] if r in results[-1]["facts"]["home_top_scorer"])
            return [("get_player_recent", {"player_id": results[-1]["players"][role]["id"], "n": 3})]
        return '{"done": true}'
    session = run(match, turns).session
    assert [lk.args.get("player_id") for lk in session.lookups.values()] == [None, ITO]


def test_the_compound_question_chains_on_the_default_fake(match):
    out = free(match, "how did the top scorer do in his last 3 games?", make_runner(
        LLMConfig(), fake_responder=FakeAgents()))
    assert [s["tool"] for s in out["research"]] == ["get_season_leaders", "get_player_recent"]
    assert out["retrieved"]["label"] == "Season leaders → Reyner: last 3 games"
    assert out["outcome"] == "answered" and out["answer"]["verified"]


# ---------- arguments and limits ----------

def test_bad_arguments_return_errors_and_add_no_facts(match):
    _, ctx, m, _ = match
    s = ResearchSession(m, ctx, max_calls=10)
    nobody = next(pid for pid, p in ctx.players.items() if p.club_id not in (m.home, m.away))
    for args in ({"player_id": "ply_9999", "n": 3}, {"player_id": nobody, "n": 3},
                 {"player_id": REYNER, "n": True}, {"player_id": REYNER, "n": "3"},
                 {"player_id": REYNER, "n": 0}, {"player_id": REYNER, "n": 6},
                 {"player_id": REYNER, "n": 2.5}):
        out = json.loads(s.call("get_player_recent", args, lambda: pytest.fail("built facts")))
        assert "error" in out, args
    assert json.loads(s.call("get_team_tonight", {"club_id": "clb_nope"}, lambda: ({}, [])))["error"]
    assert not s.lookups and s.calls == 8 and not any(st["ok"] for st in s.steps)


def test_the_call_limit_holds_inside_one_parallel_batch(match):
    def turns(turn, results):
        if turn == 1:  # seven calls in one model turn: the 6th and 7th must not run
            return [("get_player_recent", {"player_id": REYNER, "n": n}) for n in (1, 2, 3, 4, 5)] + \
                   [("get_match_info", {}), ("get_discipline", {})]
        return '{"done": true}'
    session = run(match, turns).session
    assert session.calls == MAX_TOOL_CALLS
    assert [st["ok"] for st in session.steps] == [True] * 5 + [False, False]
    assert {lk.tool for lk in session.lookups.values()} == {"get_player_recent"}


def test_every_model_round_trip_is_charged_and_the_allowance_stops_the_loop(match):
    def forever(turn, results):
        return [("get_match_so_far", {})]
    runner = runner_for(forever)
    with pytest.raises(BudgetExceeded):
        asyncio.run(research("go on", "en", match[2], match[1], runner, SHORT, max_model_calls=3))
    assert runner.budget.calls == 3 == runner.tool_client.turns  # the 4th was refused, not sent


def test_repeated_tools_with_different_arguments_all_survive(match):
    def turns(turn, results):
        if turn == 1:
            return [("get_player_recent", {"player_id": REYNER, "n": 3}),
                    ("get_player_recent", {"player_id": ITO, "n": 3}),
                    ("get_player_recent", {"player_id": REYNER, "n": 1}),
                    ("get_player_recent", {"player_id": REYNER, "n": 3})]  # a duplicate
        return '{"done": true}'
    session = run(match, turns).session
    assert len(session.lookups) == 3
    pack = session.pack()
    assert len(set(pack.roles.values())) == len(pack.roles)  # one role per player
    assert sorted(pack.roles.values()) == sorted({REYNER, ITO})


def test_lookup_errors_never_reach_the_analysts_facts(match):
    def turns(turn, results):
        if turn == 1:
            return [("get_team_tonight", {"club_id": "clb_nope"}), ("get_match_info", {})]
        return '{"done": true}'
    pack = run(match, turns).session.pack()
    assert "error" not in json.dumps(pack.facts) and len(pack.facts) == 1


# ---------- failures and fallback ----------

@pytest.mark.parametrize("final, outcome", [("Sure! Reyner is great.", "fallback_malformed"),
                                            ('["done"]', "fallback_malformed"),
                                            ('{"done": true}', "fallback_no_evidence")])
def test_a_bad_final_reply_falls_back_to_the_router(match, final, outcome):
    with pytest.raises(ResearchFailed) as err:
        run(match, lambda turn, results: final)
    assert err.value.outcome == outcome
    out = free(match, "why nor score nothing today", runner_for(lambda turn, results: final))
    assert out["outcome"] == outcome and out["answer"]["verified"]  # the Router still answered
    assert out["retrieved"]["club_id"] == match[1].away


def test_a_research_timeout_falls_back(match, monkeypatch):
    async def slow(*args, **kwargs):
        await asyncio.sleep(1)
    monkeypatch.setattr(ask_module, "research", slow)
    monkeypatch.setattr(ask_module, "RESEARCH_TIMEOUT_S", 0.05)
    out = free(match, "why nor score nothing today", make_runner(LLMConfig(), fake_responder=FakeAgents()))
    assert out["outcome"] == "fallback_timeout" and out["answer"]


def test_research_running_out_still_leaves_the_reserved_fallback(match):
    forever = runner_for(lambda turn, results: [("get_match_so_far", {})], max_calls=8)
    out = free(match, "why nor score nothing today", forever)
    assert out["outcome"] == "fallback_budget" and out["answer"]  # the Router and Analyst ran
    assert forever.budget.calls <= 8


def test_an_exhausted_budget_declines_politely(match):
    runner = make_runner(LLMConfig(max_calls=3), fake_responder=FakeAgents())
    out = free(match, "why nor score nothing today", runner)
    assert out["outcome"] == "budget_exhausted" and out["answer"] is None and out["declined"]
    assert runner.budget.calls == 0


def test_the_name_check_runs_before_any_research(match):
    runner = make_runner(LLMConfig(), fake_responder=FakeAgents())
    out = free(match, "where is Lacombe borned", runner)
    assert out["outcome"] == "clarify" and "Which player" in out["declined"]
    assert runner.budget.calls == 0 and runner.tool_client is None


def test_tied_top_scorers_are_named_together(match):
    _, ctx, m, _ = match
    home = [pid for pid, p in ctx.players.items() if p.club_id == m.home][:2]
    seasons = {pid: {"goals": 4, "assists": 0, "shots": 9} for pid in home}
    roles = _Roles()
    facts, _ = season_leaders(m, roles, seasons)
    assert " and " in facts["home_top_scorer"] and "with 4 goal(s)" in facts["home_top_scorer"]
    assert set(roles.roles.values()) >= set(home)
