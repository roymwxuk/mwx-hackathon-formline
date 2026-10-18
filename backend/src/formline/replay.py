"""Replay a recorded feed as if it were live, at accelerated speed.

`transform` is the hook for the chaos injector (duplicates, reordering, delays,
corrections): it rewrites the message list before pacing starts.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta

from formline.schema.feed import FeedMessage

FeedTransform = Callable[[list[FeedMessage]], list[FeedMessage]]


async def replay(feed: list[FeedMessage], speed: float = 10.0,
                 transform: FeedTransform | None = None) -> AsyncIterator[FeedMessage]:
    """Yield messages paced by `emitted_at`; `speed` = feed seconds per real second."""
    messages = transform(feed) if transform else feed
    if not messages:
        return
    prev = messages[0].emitted_at
    for msg in messages:
        gap = (msg.emitted_at - prev).total_seconds()
        if gap > 0:
            await asyncio.sleep(gap / speed)
        prev = max(prev, msg.emitted_at)
        yield msg


def to_stream_message(msg: FeedMessage) -> dict | None:
    """The viewer's `StreamMessage` (frontend/src/lib/types.ts). Deletes are not shown."""
    if msg.event is None:
        return None
    event = msg.event.model_dump(mode="json")
    event["version"] = msg.version
    return {"kind": "event", "event": event}


END_MESSAGE = {"kind": "end"}  # last StreamMessage: the match feed is over


def merge_stream(feed: list[FeedMessage], overlays: list[tuple[datetime, object]],
                 comments: list[tuple[datetime, dict]] = ()) -> list[tuple[datetime, dict]]:
    """Events, precomputed overlays and Analyst comments as one timed list of StreamMessages.

    Overlays and comments are placed right after the message that triggered them (same
    emission time; events, then overlays, then comments), where the live pipeline would
    have produced them.
    """
    from formline.schema.overlay import overlay_message

    items: list[tuple[datetime, int, int, dict]] = []
    for i, msg in enumerate(feed):
        payload = to_stream_message(msg)
        if payload is not None:
            items.append((msg.emitted_at, 0, i, payload))
    for i, (at, overlay) in enumerate(overlays):
        items.append((at, 1, i, overlay_message(overlay)))
    for i, (at, comment) in enumerate(comments):
        items.append((at, 2, i, {"kind": "comment", "comment": comment}))
    items.sort(key=lambda x: (x[0], x[1], x[2]))
    return [(at, payload) for at, _, _, payload in items]


TICK_SECONDS = 0.25  # during a gap, send the match time this often (real seconds)
MAX_SEND_DELAY_MS = 15_000  # true time may lead the next event by its send delay; more is bad data
PERIOD_ENDS = {"half_end"}  # the match clock stops here: no clock messages until play resumes

SLOW_FACTOR = 6.0  # around shots and cards, pacing is this many times slower (20x -> ~3x)
MIN_SLOW_PACE = 3.0  # ...but never slower than 3x (unless the viewer chose a slower speed)
SLOW_BEFORE = timedelta(seconds=4)  # feed time before a key moment
SLOW_AFTER = timedelta(seconds=14)  # and after it


def match_time(payload: dict) -> tuple[int, int] | None:
    """(period, match clock) of an event or clock message; None for overlays and the end."""
    if payload.get("kind") == "clock":
        return payload["period"], payload["match_clock_ms"]
    if payload.get("kind") != "event":
        return None
    e = payload["event"]
    return e["period"], e["match_clock_ms"]


def _clock_after(payload: dict, at: datetime, clock, kickoff: dict[int, datetime]):
    """The running match clock after a message: (period, ms, emitted_at) of the last event,
    or None once a period has ended (half-time: the clock stops).

    Also records each half's kick-off wall time, once, from the half's first event that has
    an `event_time`: the football clock never stops within a half, so event_time minus match
    clock is the same for every event in it (docs/live-clock-anchoring.md)."""
    if payload.get("kind") != "event":
        return clock
    e = payload["event"]
    period = e["period"]
    if period not in kickoff and e.get("event_time"):
        try:
            kickoff[period] = (datetime.fromisoformat(e["event_time"])
                               - timedelta(milliseconds=e["match_clock_ms"]))
        except (TypeError, ValueError):
            pass  # malformed: this half falls back to counting from the last event
    return None if e.get("type") in PERIOD_ENDS else (period, e["match_clock_ms"], at)


async def _wait(seconds: float, pace: float, clock, prev: datetime,
                nxt: tuple[int, int] | None, phase: list[float],
                kickoff: datetime | None = None,
                last_tick: list | None = None) -> AsyncIterator[dict]:
    """Sleep `seconds`; meanwhile yield a clock message every TICK_SECONDS of real time with
    the match time reached at `pace`, never past the next event. `phase` carries the time
    since the last tick across waits, so ticks keep a steady rate even when events arrive
    faster than TICK_SECONDS apart (tracking frames need that). No ticks while the clock
    is stopped or when the next event is in another period.

    With the half's `kickoff` wall time the match time is feed time minus kick-off, which
    ticks evenly whatever each event's send delay; without it, it counts from the last
    event (which runs behind by that event's delay, so it stalls and catches up)."""
    stopped = clock is None or (nxt is not None and nxt[0] != clock[0])
    if not stopped:
        period, base_ms, anchor = clock
        if kickoff is not None:
            base_ms, offset = 0, (prev - kickoff).total_seconds()
        else:
            offset = (prev - anchor).total_seconds()
    waited, last = 0.0, None
    while seconds - waited >= TICK_SECONDS - phase[0] - 1e-9:
        step = TICK_SECONDS - phase[0]
        await asyncio.sleep(step)
        waited += step
        phase[0] = 0.0
        if stopped:
            continue
        ms = base_ms + round((offset + waited * pace) * 1000)
        if nxt is not None:
            # Counting from the last event, the clock must not pass the next event. Counting
            # from kick-off it is the true time, which leads the next event by that event's
            # send delay; only a lead beyond any real delay is capped (bad data).
            ms = min(ms, nxt[1] + (MAX_SEND_DELAY_MS if kickoff is not None else 0))
        if last_tick is not None:
            if last_tick[0] is not None and last_tick[0][0] == period and ms <= last_tick[0][1]:
                continue  # never backwards (a late or corrected event)
            last_tick[0] = (period, ms)
        if ms != last:
            last = ms
            yield {"kind": "clock", "period": period, "match_clock_ms": ms}
    rest = seconds - waited
    if rest > 0:
        await asyncio.sleep(rest)
        phase[0] += rest


def parse_clock(text: str | None) -> tuple[int, int] | None:
    """`mm:ss` to (period, ms); minutes above 45 mean the second half."""
    if not text:
        return None
    minutes, seconds = (int(x) for x in text.split(":"))
    ms = (minutes * 60 + seconds) * 1000
    return (2 if ms > 45 * 60_000 else 1, ms)


async def _aiter(items):
    if hasattr(items, "__aiter__"):
        async for item in items:
            yield item
    else:
        for item in items:
            yield item


async def paced(items, speed: float = 10.0, *, start: tuple[int, int] | None = None,
                resume_after: int = 0, key_times: list[datetime] | None = None,
                slow: bool = True) -> AsyncIterator[tuple[int | None, dict]]:
    """Yield (id, StreamMessage) from timed items, paced like a live broadcast.

    - ids number the items 1, 2, 3, … in order, so a client can resume;
    - `{"kind": "clock"}` messages (id None) carry the running match time every
      TICK_SECONDS of real time, so the viewer's clock (and tracking) keeps moving;
    - items with id <= `resume_after` (the client's Last-Event-ID) are skipped;
    - everything before `start` (match time) is delivered at once, then pacing begins;
    - within SLOW_BEFORE/SLOW_AFTER of a key moment (shots, cards), pacing is SLOW_FACTOR
      times slower, so the moment stays readable at any speed.
    """
    keys = sorted(key_times or [])
    catching_up = start is not None
    prev: datetime | None = None
    clock = None  # (period, ms, emitted_at) of the last event while the clock runs
    phase = [0.0]  # real seconds since the last clock message
    kickoff: dict[int, datetime] = {}  # wall time of each half's kick-off, fixed once
    last_tick: list = [None]  # (period, ms) of the last clock message
    idx = 0
    async for at, payload in _aiter(items):
        idx += 1
        mt = match_time(payload)
        if catching_up and mt is not None and mt >= start:
            catching_up = False
            prev = at
        if idx <= resume_after:
            prev = at if prev is None else max(prev, at)
            clock = _clock_after(payload, at, clock, kickoff)
            continue
        if not catching_up and prev is not None:
            gap = (at - prev).total_seconds()
            if gap > 0:
                pace = _slow_pace(speed) if slow and _near_key(keys, at) else speed
                kick = kickoff.get(clock[0]) if clock is not None else None
                async for tick in _wait(gap / pace, pace, clock, prev, mt, phase, kick,
                                        last_tick):
                    yield None, tick
        prev = at if prev is None else max(prev, at)
        clock = _clock_after(payload, at, clock, kickoff)
        yield idx, payload


def _slow_pace(speed: float) -> float:
    """Pace near a key moment: 20x -> 3.3x, 10x and 5x -> 3x, 1x stays 1x."""
    return min(speed, max(speed / SLOW_FACTOR, MIN_SLOW_PACE))


def _near_key(keys: list[datetime], at: datetime) -> bool:
    from bisect import bisect_left
    i = bisect_left(keys, at - SLOW_AFTER)
    return i < len(keys) and keys[i] <= at + SLOW_BEFORE


async def replay_items(items: list[tuple[datetime, dict]],
                       speed: float = 10.0) -> AsyncIterator[dict]:
    """Yield pre-timed StreamMessages, paced by their timestamps (no slow-down)."""
    async for idx, payload in paced(items, speed, slow=False):
        if idx is not None:  # clock messages are for live viewers only
            yield payload
