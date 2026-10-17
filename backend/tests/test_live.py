import asyncio

import pytest

from formline.agents.fakes import FakeAgents
from formline.agents.live import LiveOrchestrator
from formline.agents.llm import LLMConfig, make_runner
from formline.agents.template_narrator import names_for
from formline.agents.verifier import league_names
from formline.agents.workflow import Deps
from formline.chaos import ChaosConfig, inject
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.log import current_events
from formline.generator.season import generate_season
from formline.schema.feed import FeedMessage


@pytest.fixture(scope="module")
def season():
    return generate_season(2026)


@pytest.fixture(scope="module")
def live_feed(season):
    return next(gm.feed for gm in season.matches if gm.match.is_live_demo)


def orchestrator(season) -> LiveOrchestrator:
    eng = BaselineEngine(season.league.players)
    eng.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                  for e in current_events(gm.feed))
    eng.fit_priors()
    names = {p.player_id: names_for(p.display_name, p.display_name_ja)
             for p in season.league.players}
    deps = Deps(make_runner(LLMConfig(), fake_responder=FakeAgents()),
                league_names(season.league.players, season.league.clubs), names)
    return LiveOrchestrator(eng, deps)


def run(season, feed):
    orch = orchestrator(season)
    return orch, asyncio.run(orch.run(feed))


def assert_consistent(overlays):
    """Ids are unique and every correct/retract supersedes something shown earlier."""
    seen = set()
    for o in overlays:
        assert o.overlay_id not in seen, o.overlay_id
        if o.op in ("correct", "retract"):
            assert o.supersedes_overlay_id in seen, o.overlay_id
        seen.add(o.overlay_id)


@pytest.fixture(scope="module")
def clean_run(season, live_feed):
    return run(season, live_feed)


def test_var_overturn_corrects_the_shown_card(clean_run, live_feed):
    orch, overlays = clean_run
    assert_consistent(overlays)
    shot = next(m.event_id for m in live_feed if m.op == "update")
    corrected = [o for o in overlays if o.op == "correct"]
    assert len(corrected) == 4 and orch.summary.corrected_cards == 4
    assert all(o.source_event_ids[0] == shot for o in corrected)
    en = next(o for o in corrected if o.lang == "en" and o.audience_mode == "casual")
    assert en.slots.headline == "Reyner: 118 km/h, missed the target"  # re-narrated
    original = next(o for o in overlays if o.overlay_id == en.supersedes_overlay_id)
    assert original.slots.headline == "Reyner: 118 km/h, goal"


def test_banner_cites_the_shot_and_the_var_events(clean_run, live_feed):
    _, overlays = clean_run
    banners = [o for o in overlays if o.template_id == "correction_banner"]
    assert len(banners) == 4 and all(o.verified and o.priority == 1 for o in banners)
    shot = next(m.event_id for m in live_feed if m.op == "update")
    var_ids = [m.event_id for m in live_feed if m.event.type.startswith("var_review")]
    assert banners[0].source_event_ids == [shot, *var_ids]
    assert {o.slots.headline for o in banners} == {"Goal disallowed after review",
                                                   "ゴール取り消し（判定変更）"}


def test_corrections_are_timed_at_the_var_decision(clean_run, live_feed):
    _, overlays = clean_run
    var_end = next(m.event for m in live_feed if m.event.type == "var_review_end")
    shot_card = next(o for o in overlays if o.op == "correct")
    assert shot_card.match_clock_ms > var_end.match_clock_ms
    original = next(o for o in overlays if o.overlay_id == shot_card.supersedes_overlay_id)
    assert original.match_clock_ms < var_end.match_clock_ms


def test_deleted_shot_retracts_every_variant(season, live_feed, clean_run):
    _, overlays = clean_run
    shown = next(o for o in overlays if o.op == "show" and o.template_id != "correction_banner")
    shot = shown.source_event_ids[0]
    delete = FeedMessage(message_id="del_x", op="delete", event_id=shot, version=9,
                         emitted_at=live_feed[-1].emitted_at, sequence=99_999, event=None)
    orch, out = run(season, [*live_feed, delete])
    assert_consistent(out)
    retracts = [o for o in out if o.op == "retract" and o.source_event_ids[0] == shot]
    assert len(retracts) == 4 and orch.summary.retracted_cards == 4
    assert {o.supersedes_overlay_id for o in retracts} == {
        o.overlay_id for o in overlays if o.insight_id == shown.insight_id and o.op == "show"}
    assert all(o.slots.headline == "" and o.ttl_ms == 0 for o in retracts)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_chaotic_feed_still_gives_consistent_overlays(season, live_feed, seed):
    chaotic = inject(live_feed, ChaosConfig(seed=seed, correction_rate=0.6, delete_rate=0.02))
    orch, out = run(season, chaotic.messages)
    assert_consistent(out)
    assert orch.summary.cards > 0
