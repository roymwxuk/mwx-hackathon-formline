import asyncio
from dataclasses import replace

import pytest

from formline.agents.cards import VARIANTS
from formline.agents.fakes import FakeAgents
from formline.agents.llm import CallBudget, FakeChatClient, LLMConfig, LLMRunner, make_runner
from formline.agents.selector import MIN_SALIENCE, SelectorState
from formline.agents.template_narrator import names_for
from formline.agents.verifier import league_names
from formline.agents.workflow import Deps, build_workflow, run_match, run_moment
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.insights import InsightCreated
from formline.engine.log import current_events
from formline.engine.pipeline import LivePipeline
from formline.generator.season import generate_season


@pytest.fixture(scope="module")
def world():
    season = generate_season(2026)
    eng = BaselineEngine(season.league.players)
    eng.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                  for e in current_events(gm.feed))
    eng.fit_priors()
    live = next(gm.feed for gm in season.matches if gm.match.is_live_demo)
    insights = [c.insight for c in LivePipeline(eng).run(live) if isinstance(c, InsightCreated)]
    names = {p.player_id: names_for(p.display_name, p.display_name_ja)
             for p in season.league.players}
    return insights, names, league_names(season.league.players, season.league.clubs)


def deps_for(world, responder, budget: int | None = None) -> Deps:
    _, names, league = world
    if budget is None:
        runner = make_runner(LLMConfig(), fake_responder=responder)
    else:
        runner = LLMRunner(FakeChatClient(responder), "fake", LLMConfig(),
                           budget=CallBudget(budget))
    return Deps(runner, league, names)


def run(world, responder, budget=None):
    insights = world[0]
    return asyncio.run(run_match(insights, deps_for(world, responder, budget)))


def events(results):
    return [(e["executor"], e["event"]) for r in results for e in r.trace]


def test_graph_has_distinct_roles(world):
    wf = build_workflow(deps_for(world, FakeAgents()))
    ids = {e.id for e in wf.get_executors_list()}
    assert ids == {"insight_selector", "verifier", "template_fallback", "overlay_composer",
                   "collector", *(f"narrator_{lang}_{mode}" for lang, mode in VARIANTS)}


def test_good_model_every_card_from_the_llm(world):
    results, summary = run(world, FakeAgents())
    assert summary.selected > 0 and summary.cards == 4 * summary.selected
    assert summary.llm_texts == summary.cards and summary.template_texts == 0
    for r in results:
        if r.cards:
            assert r.selection is not None
            assert [(c.overlay.lang, c.overlay.audience_mode) for c in r.cards] == list(VARIANTS)
            assert all(c.overlay.verified for c in r.cards)
            assert {c.overlay.insight_id for c in r.cards} == {r.selection.insight.insight_id}


def test_wrong_first_attempt_is_retried_through_the_cycle(world):
    results, summary = run(world, FakeAgents(bad_first_attempts=1))
    assert summary.retried_texts == summary.cards and summary.llm_texts == summary.cards
    ev = events(results)
    assert ("verifier", "rejected") in ev and ("verifier", "passed") in ev
    first_moment = [e for e in results[0].trace if e["executor"] == "verifier"]
    assert [e["event"] for e in first_moment][:4] == ["rejected"] * 4


def test_garbage_falls_back_to_templates(world):
    results, summary = run(world, FakeAgents(garbage=True))
    assert summary.template_texts == summary.cards > 0
    assert ("template_fallback", "template_used") in events(results)
    assert all(c.overlay.verified for r in results for c in r.cards)


def test_model_exceptions_never_crash_the_run(world):
    def broken(texts):
        raise TimeoutError("model timed out")

    results, summary = run(world, broken)
    assert summary.cards == 4 * summary.selected > 0
    assert summary.template_texts == summary.cards
    assert summary.selector_llm == 0  # the selector fell back to rules
    assert any("[model] TimeoutError" in (e.get("error") or "") for r in results for e in r.trace)


def test_exhausted_budget_degrades_gracefully(world):
    _, summary = run(world, FakeAgents(), budget=6)
    assert summary.model_calls == 6
    assert summary.cards == 4 * summary.selected
    assert summary.template_texts > 0 and summary.llm_texts > 0


def test_runs_are_deterministic(world):
    a, _ = run(world, FakeAgents())
    b, _ = run(world, FakeAgents())
    dump = lambda rs: [c.overlay.model_dump() for r in rs for c in r.cards]
    assert dump(a) == dump(b)


def test_nothing_selected_for_a_quiet_moment(world):
    insights = world[0]
    quiet = [replace(insights[0], salience=MIN_SALIENCE / 2)]
    deps = deps_for(world, FakeAgents())
    out = asyncio.run(run_moment(build_workflow(deps), quiet, SelectorState()))
    assert out.selection is None and out.cards == []
    assert [e["event"] for e in out.trace] == ["nothing_selected"]
