"""Replay a recorded feed as if it were live, at accelerated speed.

`transform` is the hook for the chaos injector (duplicates, reordering, delays,
corrections): it rewrites the message list before pacing starts.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime

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


def merge_stream(feed: list[FeedMessage], overlays: list[tuple[datetime, object]]
                 ) -> list[tuple[datetime, dict]]:
    """Events and precomputed overlays as one timed list of StreamMessages.

    An overlay is placed right after the message that triggered it (same emission time,
    events first), which is where the live pipeline would have produced it.
    """
    from formline.schema.overlay import overlay_message

    items: list[tuple[datetime, int, int, dict]] = []
    for i, msg in enumerate(feed):
        payload = to_stream_message(msg)
        if payload is not None:
            items.append((msg.emitted_at, 0, i, payload))
    for i, (at, overlay) in enumerate(overlays):
        items.append((at, 1, i, overlay_message(overlay)))
    items.sort(key=lambda x: (x[0], x[1], x[2]))
    return [(at, payload) for at, _, _, payload in items]


async def replay_items(items: list[tuple[datetime, dict]],
                       speed: float = 10.0) -> AsyncIterator[dict]:
    """Yield pre-timed StreamMessages, paced by their timestamps."""
    if not items:
        return
    prev = items[0][0]
    for at, payload in items:
        gap = (at - prev).total_seconds()
        if gap > 0:
            await asyncio.sleep(gap / speed)
        prev = max(prev, at)
        yield payload
