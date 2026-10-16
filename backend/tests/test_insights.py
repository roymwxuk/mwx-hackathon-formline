import pytest

from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.insights import (
    MIN_SEASON_N,
    MIN_THIN_N,
    InsightCorrected,
    InsightCreated,
    InsightRetracted,
)
from formline.engine.log import current_events
from formline.engine.pipeline import LivePipeline
from formline.generator.season import generate_season
from formline.schema.feed import FeedMessage


@pytest.fixture(scope="module")
def season():
    return generate_season(2026)


def history_engine(season) -> BaselineEngine:
    eng = BaselineEngine(season.league.players)
    eng.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                  for e in current_events(gm.feed))
    eng.fit_priors()
    return eng


@pytest.fixture(scope="module")
def live_feed(season):
    return next(gm.feed for gm in season.matches if gm.match.is_live_demo)


@pytest.fixture(scope="module")
def run(season, live_feed):
    pipe = LivePipeline(history_engine(season))
    return pipe, pipe.run(live_feed)


def created(changes):
    return [c.insight for c in changes if isinstance(c, InsightCreated)]


# ---------- detection ----------

def test_live_slow_shot_is_an_insight(run):
    _, changes = run
    slow = next(i for i in created(changes) if i.player_id == "ply_0107"
                and i.type == "shot_speed_vs_norm" and i.facts["value"] == 84.1)
    f = slow.facts
    assert slow.direction == "below" and f["norm"] > f["value"]
    assert f["delta"] == pytest.approx(f["value"] - f["norm"], abs=0.11)
    assert f["est_percentile"] <= 25 and f["sample_n"] >= 5
    assert f["comparison"] and f["pressure"] == "pressured"


def test_insight_facts_carry_everything_a_narrator_needs(run):
    _, changes = run
    required = {"value", "norm", "delta", "est_percentile", "sample_n", "comparison",
                "weight_on_own_shots", "outcome", "xg", "thin_sample"}
    for ins in created(changes):
        assert required <= ins.facts.keys()
        assert 0 <= ins.salience <= 1 and ins.confidence in ("high", "medium", "low")


def test_season_records_need_support_and_agree_with_direction(run):
    _, changes = run
    records = [i for i in created(changes) if i.type.startswith("season_")]
    assert records
    for ins in records:
        assert ins.facts["season_sample_n"] >= MIN_SEASON_N
        assert (ins.type == "season_best") == (ins.direction == "above")


def test_no_insights_from_tiny_thin_samples(run):
    _, changes = run
    assert not [i for i in created(changes)
                if i.facts["thin_sample"] and i.facts["sample_n"] < MIN_THIN_N]


def test_detection_is_deterministic(season, live_feed, run):
    _, first = run
    again = LivePipeline(history_engine(season)).run(live_feed)
    assert again == first


# ---------- lineage ----------

def test_every_insight_cites_its_shot_and_key_pass(run, live_feed):
    pipe, changes = run
    shots = {m.event.event_id: m.event for m in live_feed if m.event.type == "shot"}
    for ins in created(changes):
        shot = shots[ins.source_event_ids[0]]
        if shot.key_pass_event_id:
            assert shot.key_pass_event_id in ins.source_event_ids
        for eid in ins.source_event_ids:
            assert ins.insight_id in pipe.tracker.by_event[eid]


def test_var_overturn_retracts_and_corrects_dependent_insights(run, live_feed):
    pipe, changes = run
    overturned = next(m.event_id for m in live_feed if m.op == "update")
    retracted = [c for c in changes if isinstance(c, InsightRetracted)]
    corrected = [c for c in changes if isinstance(c, InsightCorrected)]
    assert [c.insight.source_event_ids[0] for c in retracted] == [overturned]
    assert [c.before.source_event_ids[0] for c in corrected] == [overturned]

    gone = retracted[0]
    assert gone.insight.metric in ("placement", "psxg")  # only defined for on-target shots
    assert "no longer applies (outcome off_target)" in gone.reason

    fix = corrected[0]
    assert fix.before.facts["outcome"] == "goal" and fix.after.facts["outcome"] == "off_target"
    assert fix.after.version == 2 and fix.after.supersedes == fix.before.insight_id
    assert "outcome goal → off_target" in fix.reason

    active_ids = {i.insight_id for i in pipe.tracker.active()}
    assert gone.insight.insight_id not in active_ids
    assert fix.after.insight_id in active_ids


def test_deleted_source_event_retracts_its_insights(season, live_feed):
    pipe = LivePipeline(history_engine(season))
    changes = pipe.run(live_feed)
    target = created(changes)[0]
    shot_id = target.source_event_ids[0]
    original = next(m for m in live_feed if m.event_id == shot_id)
    delete = FeedMessage(message_id="del_1", op="delete", event_id=shot_id, version=9,
                         emitted_at=live_feed[-1].emitted_at, sequence=99_999, event=None)
    out = pipe.process(delete)
    retracted = {c.insight.insight_id for c in out if isinstance(c, InsightRetracted)}
    expected = {i.insight_id for i in created(changes) if i.source_event_ids[0] == shot_id}
    assert retracted == expected and original.event.type == "shot"
