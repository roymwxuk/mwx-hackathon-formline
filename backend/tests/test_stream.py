import asyncio
import json
from itertools import pairwise

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
    assert len(rows) == 88  # 56 cards + 20 secondary + 4 corrected + 4 retracted + 4 banners
    times = [at for at, _ in rows]
    assert times == sorted(times)
    assert {o.op for _, o in rows} == {"show", "correct", "retract"}


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
    assert k.count("overlay") == 88 and k.count("event") > 1000
    ops = [m["overlay"]["op"] for m in messages if m["kind"] == "overlay"]
    assert "correct" in ops


def test_live_mode_runs_the_agents_during_replay(client):
    messages = read_stream(client, "live=true")
    assert kinds(messages)[-1] == "end"
    overlays = [m["overlay"] for m in messages if m["kind"] == "overlay"]
    assert len(overlays) == 88
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


def _fake_clock(monkeypatch):
    """Patch replay sleeps: record them and keep a fake real-time clock."""
    from formline import replay as rp

    state = {"now": 0.0, "waits": []}

    async def fake_sleep(seconds):
        state["waits"].append(seconds)
        state["now"] += seconds

    monkeypatch.setattr(rp.asyncio, "sleep", fake_sleep)
    return rp, state


def _events(times_s, period=1, types=None):
    from datetime import datetime, timedelta

    t0 = datetime(2026, 10, 24, 19, 0)
    return [(t0 + timedelta(seconds=t),
             {"kind": "event", "event": {"period": period, "match_clock_ms": 1000 * t,
                                         "type": (types or {}).get(t, "pass")}})
            for t in times_s]


def test_pacing_slows_down_around_key_moments(monkeypatch):
    rp, state = _fake_clock(monkeypatch)
    items = _events([0, 10, 20, 30, 40, 50])
    key = [items[-1][0]]  # a shot at the last item

    async def run(**kw):
        """Real seconds waited before each event."""
        state["waits"].clear()
        out, last = [], 0.0
        state["now"] = 0.0
        async for i, _ in rp.paced(items, 10.0, key_times=key, **kw):
            if i is not None:
                out.append((i, round(state["now"] - last, 6)))
                last = state["now"]
        return out

    got = asyncio.run(run())
    assert [i for i, _ in got] == [1, 2, 3, 4, 5, 6]
    assert [w for _, w in got[1:4]] == [1.0, 1.0, 1.0]  # 10 s of feed at 10x
    assert got[-1][1] == pytest.approx(10 / rp.MIN_SLOW_PACE)  # near the shot: slower (3x)
    assert [w for _, w in asyncio.run(run(slow=False))[1:]] == [1.0] * 5
    got = asyncio.run(run(start=(1, 30_000)))
    assert [w for _, w in got][:5] == [0, 0, 0, 0, 1.0]  # the past arrived at once
    assert got[-1][1] == pytest.approx(10 / rp.MIN_SLOW_PACE)


def test_gaps_carry_clock_messages_with_the_running_match_time(monkeypatch):
    rp, _ = _fake_clock(monkeypatch)
    items = _events([0, 27, 30])  # a 27 s gap: at 20x, 1.35 s of real time

    async def run():
        return [x async for x in rp.paced(items, 20.0, slow=False)]

    out = asyncio.run(run())
    ids = [i for i, _ in out if i is not None]
    ticks = [p for i, p in out if i is None]
    assert ids == [1, 2, 3]  # clock messages take no id
    assert all(p["kind"] == "clock" and p["period"] == 1 for p in ticks)
    times = [p["match_clock_ms"] for p in ticks]
    assert len(times) == 6  # every 0.25 s of real time: 5 in the 1.35 s gap, 1 in the next
    assert times == sorted(times) and times[0] == 5_000 and times[-1] <= 30_000
    first_after_gap = next(n for n, (i, _) in enumerate(out) if i == 2)
    gap_ticks = [p["match_clock_ms"] for i, p in out[1:first_after_gap]]
    assert len(gap_ticks) == 5 and max(gap_ticks) <= 27_000  # never past the next event


def test_ticks_keep_a_steady_rate_when_events_are_frequent(monkeypatch):
    rp, state = _fake_clock(monkeypatch)
    items = _events([2 * i for i in range(51)])  # every 2 s of feed: 0.1 s apart at 20x

    async def run():
        out = []
        async for i, p in rp.paced(items, 20.0, slow=False):
            out.append((i, p, state["now"]))
        return out

    out = asyncio.run(run())
    ticks = [now for i, _, now in out if i is None]
    assert len(ticks) == 20  # 5 s of real time, one tick every 0.25 s
    gaps = [b - a for a, b in pairwise(ticks)]
    assert all(abs(g - 0.25) < 1e-6 for g in gaps)


def test_no_clock_messages_while_the_clock_is_stopped(monkeypatch):
    rp, _ = _fake_clock(monkeypatch)
    first = _events([2700, 2760], types={2760: "half_end"})
    second = _events([2700, 2760], period=2, types={2700: "half_start"})
    from datetime import timedelta
    second = [(at + timedelta(seconds=900), p) for at, p in second]  # half-time break

    async def run():
        return [x async for x in rp.paced(first + second, 20.0, slow=False)]

    out = asyncio.run(run())
    half_end = next(n for n, (i, p) in enumerate(out) if i == 2)
    half_start = next(n for n, (i, p) in enumerate(out) if i == 3)
    before = [p for i, p in out[:half_end] if i is None]
    assert before and all(p["period"] == 1 and p["match_clock_ms"] <= 2_760_000 for p in before)
    assert half_start == half_end + 1  # no ticks during the break
    after = [p for i, p in out[half_start:] if i is None]
    assert after and all(p["period"] == 2 for p in after)  # the second half ticks again


def test_clock_messages_carry_no_sse_id(client, monkeypatch):
    _fake_clock(monkeypatch)  # instant sleeps: 20x pacing without the wait
    with client.stream("GET", f"/matches/{LIVE}/stream?speed=20&until=03:00&slow=false") as r:
        raw = r.read().decode()
    blocks = [b for b in raw.split("\r\n\r\n") if "data:" in b]
    clock = [b for b in blocks if '"kind": "clock"' in b]
    assert clock and all("id:" not in b for b in clock)
    ids = [int(line[3:].strip()) for b in blocks for line in b.splitlines()
           if line.startswith("id:")]
    assert ids == list(range(1, len(ids) + 1))


@pytest.fixture(scope="module")
def tracked(data_dir):
    """Tracking for the first 4 minutes of each half, written into the test data."""
    from formline.engine.log import current_events
    from formline.schema.tracking import tracking_path, write_tracking
    from formline.tracking.motion import build_frames

    season = generate_season(2026)
    gm = next(g for g in season.matches if g.match.is_live_demo)
    players = {p.player_id: p for p in season.league.players}
    frames = build_frames(current_events(gm.feed), gm.match.home_club_id, players,
                          season.league.starters, limit_ms=4 * 60_000)
    path = tracking_path(data_dir, LIVE)
    write_tracking(path, frames)
    yield path
    path.unlink()


def _stream_blocks(client, query):
    with client.stream("GET", f"/matches/{LIVE}/stream?{query}") as r:
        raw = r.read().decode()
    return [b for b in raw.split("\r\n\r\n") if "data:" in b]


def _data(block):
    return json.loads(next(line[5:] for line in block.splitlines() if line.startswith("data:")))


def test_ticks_become_tracking_frames_when_the_match_has_tracking(client, tracked, monkeypatch):
    _fake_clock(monkeypatch)
    blocks = _stream_blocks(client, "speed=20&until=03:00&slow=false")
    frames = [(b, _data(b)) for b in blocks if '"kind":"frame"' in b]
    assert frames and not any('"kind": "clock"' in b for b in blocks)
    assert all("id:" not in b for b, _ in frames)  # resume ids stay on real messages
    times = [d["t"] for _, d in frames]
    assert times == sorted(times) and times[-1] <= 180_000
    first = frames[0][1]
    assert set(first) == {"kind", "p", "t", "b", "h", "a"}
    assert len(first["h"]) == 11 and len(first["a"]) == 11 and len(first["b"]) == 3


def test_tracking_can_be_turned_off(client, tracked, monkeypatch):
    _fake_clock(monkeypatch)
    blocks = _stream_blocks(client, "speed=20&until=01:00&slow=false&tracking=false")
    assert any('"kind": "clock"' in b for b in blocks)
    assert not any('"kind":"frame"' in b for b in blocks)


def test_slow_down_never_drops_below_3x_or_above_the_chosen_speed():
    from formline import replay as rp

    assert rp._slow_pace(20) == pytest.approx(20 / 6)
    assert rp._slow_pace(10) == rp._slow_pace(5) == 3.0
    assert rp._slow_pace(1) == 1.0
    assert rp._slow_pace(1e9) == pytest.approx(1e9 / 6)  # tests' instant replays stay instant



def _timed_events(spec, period=1, kick=None):
    """Events (clock_s, send_delay_s): event_time = kick-off + clock, sent `delay` later."""
    from datetime import datetime, timedelta

    kick = kick or datetime(2026, 10, 24, 19, 0)
    return [(kick + timedelta(seconds=c + d),
             {"kind": "event", "event": {"period": period, "match_clock_ms": int(c * 1000),
                                         "type": "pass",
                                         "event_time": (kick + timedelta(seconds=c)).isoformat()}})
            for c, d in spec]


def _ticks(rp, items, speed):
    async def run():
        return [p for i, p in [x async for x in rp.paced(items, speed, slow=False)] if i is None]
    return asyncio.run(run())


def test_clock_ticks_evenly_whatever_each_events_send_delay(monkeypatch):
    rp, _ = _fake_clock(monkeypatch)
    # passes every 3 s, sent alternately 0.3 s and 0.9 s late (the feed's real spread)
    items = _timed_events([(3 * i, 0.3 if i % 2 == 0 else 0.9) for i in range(9)])
    times = [p["match_clock_ms"] for p in _ticks(rp, items, 1.0)]
    steps = {b - a for a, b in pairwise(times)}
    assert steps == {250}  # one quarter second per quarter second: real time at 1x
    assert times[0] == 550  # true match time (the first pass was sent 0.3 s after 0:00)


def test_a_late_event_does_not_stall_the_clock(monkeypatch):
    rp, _ = _fake_clock(monkeypatch)
    spec = [(3 * i, 0.4) for i in range(8)]
    spec.insert(4, (1.0, 10.0))  # happened at 0:01, arrives about 11 s in (chaos-style)
    items = sorted(_timed_events(spec), key=lambda x: x[0])
    times = [p["match_clock_ms"] for p in _ticks(rp, items, 1.0)]
    assert {b - a for a, b in pairwise(times)} == {250}


def test_kick_off_is_fixed_per_half(monkeypatch):
    from datetime import datetime, timedelta

    rp, _ = _fake_clock(monkeypatch)
    first_kick = datetime(2026, 10, 24, 19, 0)
    first = _timed_events([(2697, 0.5), (2700, 0.5)], kick=first_kick)
    first[-1][1]["event"]["type"] = "half_end"
    second_kick = first_kick + timedelta(minutes=63)  # 45:00 + break, so a new kick-off
    second = _timed_events([(2700, 0.5), (2703, 0.5), (2706, 0.5)], period=2,
                           kick=second_kick - timedelta(seconds=2700))
    times = [(p["period"], p["match_clock_ms"]) for p in _ticks(rp, first + second, 1.0)]
    second_half = [ms for per, ms in times if per == 2]
    assert second_half and all(2_700_000 < ms <= 2_706_500 for ms in second_half)  # + send delay
    assert {b - a for a, b in pairwise(second_half)} == {250}
