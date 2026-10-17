import asyncio
import json
from dataclasses import replace

import pytest

from formline.agents.cards import VARIANTS, build_cards
from formline.agents.composer import compose, overlay_id
from formline.agents.fakes import FakeAgents
from formline.agents.llm import LLMConfig, make_runner
from formline.agents.narrator import (
    MAX_ATTEMPTS,
    NarrationParseError,
    narrate_verified,
    parse_slots,
    request_payload,
)
from formline.agents.selector import (
    COOLDOWN_MS,
    MIN_SALIENCE,
    RATE_MAX,
    Selection,
    SelectorState,
    parse_choice,
    select,
    shortlist,
)
from formline.agents.template_narrator import names_for
from formline.agents.verifier import league_names
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
    players = {p.player_id: p for p in season.league.players}
    names = {pid: names_for(p.display_name, p.display_name_ja) for pid, p in players.items()}
    return insights, names, league_names(season.league.players, season.league.clubs)


def runner_with(fake: FakeAgents):
    return make_runner(LLMConfig(), fake_responder=fake)


def by_shot(insights):
    shots: dict[str, list] = {}
    for ins in insights:
        shots.setdefault(ins.source_event_ids[0], []).append(ins)
    return list(shots.values())


def slow_shot(insights):
    return next(i for i in insights if i.player_id == "ply_0107" and i.facts["value"] == 84.1
                and i.type == "shot_speed_vs_norm")


# ---------- selector ----------

def test_shortlist_rules(world):
    insights, _, _ = world
    ins = slow_shot(insights)
    state = SelectorState()
    assert shortlist([replace(ins, salience=MIN_SALIENCE - 0.01)], state) == []
    assert shortlist([ins], state) == [ins]
    # cooldown: same player shortly after
    state.last_shown[ins.player_id] = (ins.period, ins.match_clock_ms - COOLDOWN_MS // 2)
    assert shortlist([ins], state) == []
    assert shortlist([replace(ins, salience=0.95)], state)  # a record overrides the cooldown
    # rate limit
    state = SelectorState(shown_times=[(ins.period, ins.match_clock_ms - 1000)] * RATE_MAX)
    assert shortlist([ins], state) == []


def test_selector_picks_one_card_per_shot_through_the_llm(world):
    insights, names, _ = world
    fake = FakeAgents()
    runner = runner_with(fake)
    state = SelectorState()
    en = {pid: n.en for pid, n in names.items()}
    multi = next(group for group in by_shot(insights) if len(shortlist(group, state)) > 1)
    sel = asyncio.run(select(multi, state, runner, en))
    assert sel.decided_by == "llm" and sel.reason
    assert sel.insight in multi and sel.insight.salience == max(i.salience for i in multi)
    assert state.last_shown[sel.insight.player_id] == (sel.insight.period,
                                                       sel.insight.match_clock_ms)


def test_selector_falls_back_on_bad_llm_output():
    allowed = {"ins_a", "ins_b"}
    assert parse_choice('{"show": "ins_a", "reason": "x"}', allowed) == ("ins_a", "x")
    assert parse_choice('```json\n{"show": "ins_b"}\n```', allowed) == ("ins_b", "")
    assert parse_choice('{"show": "ins_zzz"}', allowed) is None  # not on the shortlist
    assert parse_choice("I pick the first one", allowed) is None


def test_selector_uses_rules_when_the_model_is_unusable(world):
    insights, names, _ = world
    runner = make_runner(LLMConfig(), fake_responder=lambda t: "no idea")
    state = SelectorState()
    en = {pid: n.en for pid, n in names.items()}
    multi = next(group for group in by_shot(insights) if len(shortlist(group, state)) > 1)
    sel = asyncio.run(select(multi, state, runner, en))
    assert sel.decided_by == "rules" and sel.insight == shortlist(multi, SelectorState())[0]


# ---------- narrator ----------

def test_payload_carries_facts_limits_and_mode(world):
    insights, names, _ = world
    ins = slow_shot(insights)
    p = request_payload(ins, "ja", "analyst", names[ins.player_id], feedback="- [numbers] x")
    assert p["player"] == "レイナー" and p["audience_mode"] == "analyst"
    assert p["FACTS"]["value"] == 84.1 and p["LIMITS"]["headline"] == 30
    assert p["COMPARISON"] == ins.facts["comparison_level"]
    assert p["FIX_THESE_PROBLEMS"] == "- [numbers] x"


def test_parse_slots():
    assert parse_slots('```json\n{"tag": "a", "headline": "b", "sub": "c"}\n```')["tag"] == "a"
    with pytest.raises(NarrationParseError):
        parse_slots("not json")


def test_good_model_passes_first_time(world):
    insights, names, league = world
    ins = slow_shot(insights)
    n = asyncio.run(narrate_verified(ins, "en", "casual", names[ins.player_id],
                                     runner_with(FakeAgents()), league))
    assert n.source == "llm" and n.attempts == 1 and not n.failures


def test_wrong_number_is_retried_with_feedback(world):
    insights, names, league = world
    ins = slow_shot(insights)
    fake = FakeAgents(bad_first_attempts=1)
    runner = runner_with(fake)
    n = asyncio.run(narrate_verified(ins, "en", "casual", names[ins.player_id], runner, league))
    assert n.source == "llm" and n.attempts == 2
    assert "[numbers]" in n.failures[0]
    retry_payload = json.loads(runner.client.calls[-1][-1])
    assert "FIX_THESE_PROBLEMS" in retry_payload


def test_persistent_failure_falls_back_to_the_template(world):
    insights, names, league = world
    ins = slow_shot(insights)
    for fake in (FakeAgents(bad_first_attempts=99), FakeAgents(garbage=True)):
        runner = runner_with(fake)
        n = asyncio.run(narrate_verified(ins, "ja", "analyst", names[ins.player_id], runner,
                                         league))
        assert n.source == "template" and len(n.failures) == MAX_ATTEMPTS
        assert len(runner.client.calls) == MAX_ATTEMPTS


# ---------- composer and the full card set ----------

def test_composer_builds_a_valid_overlay(world):
    insights, _, _ = world
    ins = slow_shot(insights)
    sel = Selection(ins, 2, "test", "rules")
    text = {"tag": "T", "headline": "Reyner — not his usual strike", "sub": "84 km/h (estimate)."}
    o = compose(sel, "en", "casual", text)
    assert o.overlay_id == overlay_id(ins.insight_id, "en", "casual")
    assert o.match_clock_ms == ins.match_clock_ms + 2_000 and o.priority == 2
    assert o.metric == "shot_speed" and o.source_event_ids == list(ins.source_event_ids)
    assert [b.value for b in o.slots.bars] == [84.1, ins.facts["norm"]]


def test_one_insight_becomes_four_verified_overlays(world):
    insights, names, league = world
    ins = slow_shot(insights)
    sel = Selection(ins, 2, "test", "rules")
    cards = asyncio.run(build_cards(sel, names[ins.player_id], runner_with(FakeAgents()),
                                    league))
    assert [(c.overlay.lang, c.overlay.audience_mode) for c in cards] == list(VARIANTS)
    assert all(c.overlay.verified and c.narration.source == "llm" for c in cards)
    assert {c.overlay.overlay_id for c in cards} == {
        overlay_id(ins.insight_id, lang, mode) for lang, mode in VARIANTS}
    ja = next(c for c in cards if c.overlay.lang == "ja" and c.overlay.audience_mode == "casual")
    assert ja.overlay.slots.headline == "レイナー、いつもの威力がない"
