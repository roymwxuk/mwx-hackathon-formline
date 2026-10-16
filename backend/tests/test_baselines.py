import random
import statistics as st

import pytest

from formline.engine.baselines import MIN_N, Bucket, bucket_keys
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied, ingest_all
from formline.engine.log import current_events
from formline.generator.season import generate_season


@pytest.fixture(scope="module")
def season():
    return generate_season(2026)


def history_events(season):
    return [e for gm in season.matches if not gm.match.is_live_demo
            for e in current_events(gm.feed)]


def live_feed(season):
    return next(gm.feed for gm in season.matches if gm.match.is_live_demo)


@pytest.fixture(scope="module")
def engine(season):
    eng = BaselineEngine(season.league.players)
    eng.apply_all(Applied(e) for e in history_events(season))
    return eng


# ---------- exact bucket ----------

def test_bucket_matches_statistics_module():
    values = [84.1, 99.4, 101.2, 76.0, 88.8, 92.3]
    b = Bucket(scale=10)
    for i, v in enumerate(values):
        b.add(v, f"e{i}")
    assert b.n == 6
    assert b.mean == pytest.approx(st.mean(values))
    assert b.sd == pytest.approx(st.stdev(values))
    assert b.extremes() == (76.0, 101.2)
    assert b.percentile_of(90.0) == pytest.approx(50.0)


def test_bucket_add_remove_is_exact_and_order_independent():
    rng = random.Random(1)
    values = [(round(rng.uniform(50, 120), 1), f"e{i}") for i in range(200)]
    a, b = Bucket(10), Bucket(10)
    for v, eid in values:
        a.add(v, eid)
    for v, eid in reversed(values):
        b.add(v, eid)
    for v, eid in values[:50]:  # remove a quarter again
        a.remove(v, eid)
    c = Bucket(10)
    for v, eid in values[50:]:
        c.add(v, eid)
    assert (a.values, a.total, a.total_sq) == (c.values, c.total, c.total_sq)
    assert (b.total, b.total_sq) == (sum(round(v * 10) for v, _ in values),
                                     sum(round(v * 10) ** 2 for v, _ in values))


def test_removing_unknown_value_fails_loudly():
    b = Bucket(10)
    b.add(80.0, "e1")
    with pytest.raises(KeyError):
        b.remove(80.0, "e2")


# ---------- like with like ----------

def test_lookup_compares_like_with_like(engine):
    f = next(iter(engine.features.values()))
    view = engine.store.lookup(f, "shot_speed_kmh", min_n=1)
    assert view.level == "zone_body_pressure"
    matching = [g for g in engine.features.values() if g.player_id == f.player_id
                and bucket_keys(g)["zone_body_pressure"] == bucket_keys(f)["zone_body_pressure"]
                and g.shot_type != "penalty" and g.body_group != "other"]
    assert view.player.n == len(matching)
    assert view.player.mean == pytest.approx(st.mean(g.shot_speed_kmh for g in matching), abs=0.05)


def test_ladder_widens_until_enough_shots(engine):
    for f in engine.features.values():
        view = engine.store.lookup(f, "shot_speed_kmh")
        if view is None:
            continue
        assert view.thin or view.player.n >= MIN_N
        if view.thin:  # nothing reached MIN_N, so it reports the widest level
            assert view.level == "body"


def test_regular_shooter_gets_a_specific_comparison(engine):
    reyner = [f for f in engine.features.values() if f.player_id == "ply_0107"
              and f.body_group == "strong_foot"]
    levels = {engine.store.lookup(f, "shot_speed_kmh").level for f in reyner}
    assert levels & {"zone_body_pressure", "zone_body"}


def test_group_bucket_is_filled_alongside(engine):
    f = next(f for f in engine.features.values() if f.player_id == "ply_0107")
    view = engine.store.lookup(f, "shot_speed_kmh")
    assert view.group is not None and view.group.n >= view.player.n


# ---------- comparisons ----------

def test_shot_is_compared_before_it_is_added(season):
    eng = BaselineEngine(season.league.players)
    comparisons = eng.apply_all(Applied(e) for e in history_events(season))
    first = {}
    for c in comparisons:
        first.setdefault(c.features.player_id, c)
    # A player's first shot has nothing to compare against.
    assert all(not c.metrics for c in first.values())


def test_live_slow_shot_reads_below_his_norm(season):
    eng = BaselineEngine(season.league.players)
    eng.apply_all(Applied(e) for e in history_events(season))
    comparisons = eng.apply_all(ingest_all(live_feed(season)))
    slow = next(c for c in comparisons if c.features.player_id == "ply_0107"
                and c.features.shot_speed_kmh == 84.1)
    speed = slow.metrics["shot_speed_kmh"]
    assert speed.mean > speed.value
    assert speed.percentile < 50


# ---------- corrections and rebuilds ----------

def test_var_revision_removes_on_target_metrics(season):
    eng = BaselineEngine(season.league.players)
    comparisons = eng.apply_all(ingest_all(live_feed(season)))
    revised = [c for c in comparisons if c.revision]
    assert len(revised) == 1
    f = revised[0].features
    assert f.outcome == "off_target" and eng.features[f.event_id].outcome == "off_target"
    for key, (n, *_rest, values) in eng.store.snapshot().items():
        if key[1] in ("placement", "psxg"):
            assert all(eid != f.event_id for _, eid in values)


def test_incremental_equals_rebuild_from_log(season):
    feed = live_feed(season)
    incremental = BaselineEngine(season.league.players)
    incremental.apply_all(ingest_all(feed))
    rebuilt = BaselineEngine(season.league.players)
    rebuilt.apply_all(Applied(e) for e in current_events(feed))
    assert incremental.store.snapshot() == rebuilt.store.snapshot()
