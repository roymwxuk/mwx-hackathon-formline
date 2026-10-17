import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from formline import api
from formline.agents.precompute import default_runner, overlays_path, precompute, read_overlays
from formline.config import settings
from formline.engine.bootstrap import bootstrap_history
from formline.generator.output import read_feed, write_season
from formline.generator.season import generate_season
from formline.replay import merge_stream

LIVE = "mtc_s26_md11_har_nor"


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    write_season(generate_season(2026), data)
    asyncio.run(precompute(data, LIVE, bootstrap_history(data), default_runner(data)))
    original = settings.data_dir
    settings.data_dir = data
    api.history_engine.cache_clear()
    yield data
    settings.data_dir = original
    api.history_engine.cache_clear()


@pytest.fixture(scope="module")
def client(data_dir):
    return TestClient(api.app)


def read_stream(client, query: str) -> list[dict]:
    out = []
    with client.stream("GET", f"/matches/{LIVE}/stream?speed=1e9&{query}") as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                out.append(json.loads(line[5:].strip()))
    return out


def kinds(messages):
    return [m["kind"] for m in messages]


def test_precompute_writes_timed_overlays(data_dir):
    rows = read_overlays(overlays_path(data_dir, LIVE))
    assert len(rows) == 64  # 56 cards + 4 corrections + 4 banners
    times = [at for at, _ in rows]
    assert times == sorted(times)
    assert {o.op for _, o in rows} == {"show", "correct"}


def test_rerun_is_served_from_the_cache(data_dir):
    runner = default_runner(data_dir)
    asyncio.run(precompute(data_dir, LIVE, bootstrap_history(data_dir), runner))
    assert runner.budget.calls == 0 and runner.cache_hits > 0


def test_overlays_follow_their_trigger(data_dir):
    feed = read_feed(data_dir / "feeds" / f"{LIVE}.jsonl")
    merged = merge_stream(feed, read_overlays(overlays_path(data_dir, LIVE)))
    first = next(i for i, (_, m) in enumerate(merged) if m["kind"] == "overlay")
    shot_id = merged[first][1]["overlay"]["source_event_ids"][0]
    shot_at = next(i for i, (_, m) in enumerate(merged)
                   if m["kind"] == "event" and m["event"]["event_id"] == shot_id)
    assert shot_at < first


def test_default_stream_merges_events_and_cached_overlays(client):
    messages = read_stream(client, "")
    k = kinds(messages)
    assert k[-1] == "end" and k.count("end") == 1
    assert k.count("overlay") == 64 and k.count("event") > 1000
    ops = [m["overlay"]["op"] for m in messages if m["kind"] == "overlay"]
    assert "correct" in ops


def test_live_mode_runs_the_agents_during_replay(client):
    messages = read_stream(client, "live=true")
    assert kinds(messages)[-1] == "end"
    overlays = [m["overlay"] for m in messages if m["kind"] == "overlay"]
    assert len(overlays) == 64
    assert any(o["template_id"] == "correction_banner" for o in overlays)


def test_chaos_mode_keeps_overlays_consistent(client):
    messages = read_stream(client, "chaos=true&chaos_seed=3")
    assert kinds(messages)[-1] == "end"
    seen = set()
    for o in (m["overlay"] for m in messages if m["kind"] == "overlay"):
        assert o["overlay_id"] not in seen
        if o["op"] in ("correct", "retract"):
            assert o["supersedes_overlay_id"] in seen
        seen.add(o["overlay_id"])
    assert seen


def test_until_stops_at_a_match_moment(client):
    messages = read_stream(client, "until=40:30")
    assert kinds(messages)[-1] == "end"
    events = [m["event"] for m in messages if m["kind"] == "event"]
    assert max((e["period"], e["match_clock_ms"]) for e in events) <= (1, 40 * 60_000 + 30_000)
    second_half = read_stream(client, "until=65:40")
    assert any(m["kind"] == "overlay" and m["overlay"]["op"] == "correct" for m in second_half)


def read_raw(client, query: str, headers: dict | None = None) -> list[tuple[int, dict]]:
    """(id, message) pairs from the SSE stream."""
    out, current_id = [], None
    with client.stream("GET", f"/matches/{LIVE}/stream?speed=1e9&{query}",
                       headers=headers or {}) as r:
        for line in r.iter_lines():
            if line.startswith("id:"):
                current_id = int(line[3:].strip())
            elif line.startswith("data:"):
                out.append((current_id, json.loads(line[5:].strip())))
    return out


def test_every_message_has_a_sequential_id(client):
    pairs = read_raw(client, "until=05:00")
    ids = [i for i, _ in pairs]
    assert ids == list(range(1, len(ids) + 1))
    assert pairs[-1][1]["kind"] == "end"


def test_reconnect_resumes_after_last_event_id(client):
    full = read_raw(client, "until=20:00")
    resumed = read_raw(client, "until=20:00", headers={"Last-Event-ID": "100"})
    assert resumed[0][0] == 101
    assert [m for _, m in resumed] == [m for i, m in full if i > 100]


def test_start_delivers_the_past_at_once_then_continues(client):
    from_40 = read_raw(client, "start=40:00&until=41:00")
    events = [m["event"] for _, m in from_40 if m["kind"] == "event"]
    assert events[0]["match_clock_ms"] == 0  # history up to 40:00 is included
    assert max((e["period"], e["match_clock_ms"]) for e in events) <= (1, 41 * 60_000)


def test_pacing_slows_down_around_key_moments(monkeypatch):
    from datetime import datetime, timedelta

    from formline import replay as rp

    waits: list[float] = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(rp.asyncio, "sleep", fake_sleep)
    t0 = datetime(2026, 10, 24, 19, 0)
    items = [(t0 + timedelta(seconds=10 * i),
              {"kind": "event", "event": {"period": 1, "match_clock_ms": 10_000 * i}})
             for i in range(6)]
    key = [t0 + timedelta(seconds=50)]  # a shot at the last item

    async def run(**kw):
        waits.clear()
        return [i async for i, _ in rp.paced(items, 10.0, key_times=key, **kw)]

    ids = asyncio.run(run())
    assert ids == [1, 2, 3, 4, 5, 6]
    assert waits[:3] == [1.0, 1.0, 1.0]  # 10 s of feed at 10x
    assert waits[-1] == pytest.approx(10 / (10 / rp.SLOW_FACTOR))  # near the shot: slower
    asyncio.run(run(slow=False))
    assert waits == [1.0] * 5
    asyncio.run(run(start=(1, 30_000)))
    assert waits[0] == 1.0 and len(waits) == 2  # 40 s and 50 s; the rest arrived at once
