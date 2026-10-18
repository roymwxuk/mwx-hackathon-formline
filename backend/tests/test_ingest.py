from datetime import timedelta

import pytest

from formline.engine.ingest import Applied, Ingestor, Revised, ingest_all
from formline.engine.log import JsonlEventLog, MemoryEventLog, current_events
from formline.generator.season import generate_season
from formline.schema.feed import FeedMessage


@pytest.fixture(scope="module")
def live_feed() -> list[FeedMessage]:
    season = generate_season(2026)
    return next(m.feed for m in season.matches if m.match.is_live_demo)


@pytest.fixture(scope="module")
def creates(live_feed) -> list[FeedMessage]:
    """Plain create messages, in emission order."""
    return [m for m in live_feed if m.op == "create"][:200]


def msg(base: FeedMessage, **changes) -> FeedMessage:
    return base.model_copy(update=changes)


def update(base: FeedMessage, version: int, **event_changes) -> FeedMessage:
    event = base.event.model_copy(update=event_changes)
    return msg(base, op="update", version=version, event=event,
               message_id=f"{base.message_id}_v{version}")


def applied_ids(changes) -> list[str]:
    return [c.event.event_id for c in changes if isinstance(c, Applied)]


# ---------- duplicates ----------

def test_duplicate_delivery_is_ignored(creates):
    ing = Ingestor()
    changes = ingest_all([creates[0], creates[0], creates[1], creates[0]], ing)
    assert sorted(applied_ids(changes)) == sorted([creates[0].event_id, creates[1].event_id])
    assert ing.stats.duplicates == 2
    assert len(ing.log) == 2


# ---------- ordering ----------

def test_out_of_order_within_window_is_released_in_event_time_order(creates):
    batch = creates[10:30]
    span = batch[-1].event.event_time - batch[0].event.event_time
    shuffled = batch[::-1]  # fully reversed arrival
    changes = ingest_all(shuffled, Ingestor(window=span + timedelta(seconds=1)))
    expected = [e.event_id for e in sorted((m.event for m in batch),
                                           key=lambda e: (e.event_time, e.event_id))]
    assert applied_ids(changes) == expected


def test_events_wait_for_the_watermark(creates):
    ing = Ingestor(window=timedelta(seconds=5))
    first = creates[0]
    assert ing.ingest(first) == []  # buffered: nothing later seen yet
    later = next(m for m in creates if m.event.event_time > first.event.event_time
                 + timedelta(seconds=6))
    released = applied_ids(ing.ingest(later))
    assert first.event_id in released and later.event_id not in released


def test_idle_timeout_releases_without_a_next_message(creates):
    ing = Ingestor(window=timedelta(seconds=5))
    first = creates[0]
    assert ing.ingest(first) == []
    t = first.event.event_time
    assert ing.advance_to(t + timedelta(seconds=3)) == []  # still inside the window
    assert applied_ids(ing.advance_to(t + timedelta(seconds=6))) == [first.event_id]
    # an older event arriving after the timeout is applied late, as usual
    older = msg(creates[1], event=creates[1].event.model_copy(
        update={"event_time": t - timedelta(seconds=1)}), event_id="evt_older",
        message_id="m_older")
    older = older.model_copy(update={"event": older.event.model_copy(update={"event_id": "evt_older"})})
    assert ing.ingest(older) == [Applied(older.event, late=True)]


def test_event_after_watermark_is_applied_late(creates):
    early, rest = creates[0], creates[1:]
    ing = Ingestor()
    changes = ingest_all(rest, ing)  # flush releases everything
    late = ing.ingest(early)
    assert late == [Applied(early.event, late=True)]
    assert ing.stats.late == 1
    assert early.event_id not in applied_ids(changes)


def test_clean_feed_has_no_late_events(live_feed):
    ing = Ingestor()
    changes = ingest_all(live_feed, ing)
    n_events = len({m.event_id for m in live_feed})
    assert ing.stats.late == 0
    assert len([c for c in changes if isinstance(c, Applied)]) == n_events
    times = [c.event.event_time for c in changes if isinstance(c, Applied)]
    assert times == sorted(times)


# ---------- corrections ----------

def test_update_before_release_replaces_silently(creates):
    base = creates[5]
    ing = Ingestor()
    ing.ingest(base)
    ing.ingest(update(base, 2, player_id="ply_9999"))
    changes = ing.flush()
    assert len(changes) == 1 and changes[0].event.player_id == "ply_9999"
    assert ing.stats.revisions == 0


def test_update_after_release_is_a_revision(creates):
    base = creates[5]
    ing = Ingestor()
    ingest_all([base], ing)
    changes = ing.ingest(update(base, 2, player_id="ply_9999"))
    assert len(changes) == 1 and isinstance(changes[0], Revised)
    assert changes[0].before.player_id == base.event.player_id
    assert changes[0].after.player_id == "ply_9999" and changes[0].version == 2


def test_stale_version_is_ignored(creates):
    base = creates[5]
    v2 = update(base, 2, player_id="ply_9999")
    ing = Ingestor()
    changes = ingest_all([v2, base], ing)  # v1 arrives after v2
    assert [c.event.player_id for c in changes] == ["ply_9999"]
    assert ing.stats.stale == 1


def test_delete_after_release_revises_to_nothing(creates):
    base = creates[5]
    ing = Ingestor()
    ingest_all([base], ing)
    delete = FeedMessage(message_id="del", op="delete", event_id=base.event_id, version=2,
                         emitted_at=base.emitted_at, sequence=999, event=None)
    assert ing.ingest(delete) == [Revised(base.event, None, 2)]


def test_var_update_in_live_feed_is_one_revision(live_feed):
    changes = ingest_all(live_feed)
    revisions = [c for c in changes if isinstance(c, Revised)]
    assert len(revisions) == 1
    rev = revisions[0]
    assert rev.before.outcome == "goal" and rev.after.outcome == "off_target"


# ---------- log ----------

def test_current_events_is_highest_version(live_feed):
    final = {e.event_id: e for e in current_events(MemoryEventLog(live_feed))}
    shot = next(m.event for m in live_feed if m.op == "update")
    assert final[shot.event_id].outcome == "off_target"
    assert len(final) == len({m.event_id for m in live_feed})


def test_jsonl_log_persists_and_dedupes(tmp_path, creates):
    path = tmp_path / "log.jsonl"
    log = JsonlEventLog(path)
    assert log.append(creates[0]) and log.append(creates[1])
    assert not log.append(creates[0])
    reopened = JsonlEventLog(path)
    assert [m.message_id for m in reopened] == [creates[0].message_id, creates[1].message_id]
    assert not reopened.append(creates[1])
