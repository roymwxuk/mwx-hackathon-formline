import asyncio
from collections import Counter

import pytest

from formline.chaos import ChaosConfig, inject
from formline.engine.ingest import Ingestor, ingest_all
from formline.engine.log import current_events
from formline.generator.season import generate_season
from formline.replay import replay


@pytest.fixture(scope="module")
def live_feed():
    season = generate_season(2026)
    return next(gm.feed for gm in season.matches if gm.match.is_live_demo)


def ids(messages):
    return [m.message_id for m in messages]


def test_zero_rates_change_nothing(live_feed):
    quiet = ChaosConfig(duplicate_rate=0, reorder_rate=0, late_rate=0, correction_rate=0)
    result = inject(live_feed, quiet)
    assert ids(result.messages) == ids(live_feed)


def test_same_seed_same_chaos_different_seed_differs(live_feed):
    a = inject(live_feed, ChaosConfig(seed=1)).messages
    b = inject(live_feed, ChaosConfig(seed=1)).messages
    c = inject(live_feed, ChaosConfig(seed=2)).messages
    assert ids(a) == ids(b)
    assert ids(a) != ids(c)


def test_nothing_is_dropped(live_feed):
    result = inject(live_feed, ChaosConfig(seed=3))
    delivered = Counter(ids(result.messages))
    assert all(delivered[m.message_id] >= 1 for m in live_feed)


def test_rates_are_roughly_respected(live_feed):
    n = len(live_feed)
    r = inject(live_feed, ChaosConfig(seed=4, duplicate_rate=0.05, reorder_rate=0.1,
                                      late_rate=0.02)).report
    assert r.duplicates == pytest.approx(0.05 * n, rel=0.35)
    assert r.reordered == pytest.approx(0.1 * n * 0.98, rel=0.3)
    assert r.late == pytest.approx(0.02 * n, rel=0.5)
    assert r.messages_out == n + r.duplicates + r.corrections + r.reverts + r.deletes


def test_duplicates_are_identical_redeliveries(live_feed):
    result = inject(live_feed, ChaosConfig(seed=5, duplicate_rate=0.1))
    seen = {}
    for m in result.messages:
        if m.message_id in seen:
            assert m == seen[m.message_id]
        seen[m.message_id] = m


def test_corrections_add_higher_versions_and_reverts_restore(live_feed):
    cfg = ChaosConfig(seed=6, correction_rate=0.6, revert_rate=0.5)
    result = inject(live_feed, cfg)
    r = result.report
    assert r.corrections > 0 and r.reverts > 0
    original = {m.event_id: m.event for m in live_feed if m.op == "create"}
    var_shot = next(m.event_id for m in live_feed if m.op == "update")
    assert var_shot not in r.corrected_event_ids  # real updates are left alone
    by_event: dict[str, list] = {}
    for m in result.messages:
        if m.op == "update" and m.event_id in r.corrected_event_ids:
            by_event.setdefault(m.event_id, []).append(m)
    for eid, updates in by_event.items():
        updates.sort(key=lambda m: m.version)
        assert updates[0].version == 2
        assert updates[0].event != original[eid]  # outcome or shooter changed
        if len(updates) == 2:
            assert updates[1].version == 3 and updates[1].event == original[eid]


def test_deletes_remove_events_from_the_final_state(live_feed):
    result = inject(live_feed, ChaosConfig(seed=7, delete_rate=0.02))
    assert result.report.deletes > 0
    final = {e.event_id for e in current_events(result.messages)}
    assert len(final) == len({m.event_id for m in live_feed}) - result.report.deletes


def test_ingestor_sees_the_damage(live_feed):
    result = inject(live_feed, ChaosConfig(seed=8, late_rate=0.03))
    ing = Ingestor()
    ingest_all(result.messages, ing)
    assert ing.stats.duplicates == result.report.duplicates
    assert ing.stats.late > 0
    assert ing.stats.revisions >= 1


def test_plugs_into_replay(live_feed):
    feed = live_feed[:100]

    async def collect():
        cfg = ChaosConfig(seed=9, duplicate_rate=0.2)
        return [m async for m in replay(feed, speed=1e9,
                                        transform=lambda f: inject(f, cfg).messages)]

    out = asyncio.run(collect())
    assert len(out) > len(feed)
