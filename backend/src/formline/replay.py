"""Replay a recorded feed as if it were live, at accelerated speed.

`transform` is the hook for the chaos injector (duplicates, reordering, delays,
corrections): it rewrites the message list before pacing starts.
"""

import asyncio
from collections.abc import AsyncIterator, Callable

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
