"""A small in-memory sliding-window rate limiter (one process, one replica).

Used for the viewer's typed questions to the Match Analyst, which always cost a model call.
The key is the client address; behind Azure Container Apps ingress that is the first
`X-Forwarded-For` entry, which a client can spoof, so this is a cost guard for the demo, not
an abuse defence (that would sit at the ingress or an API gateway).
"""

import time
from collections import deque
from collections.abc import Callable

MAX_KEYS = 10_000  # forget the oldest clients beyond this, so memory stays bounded


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self.hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        """Record a request for `key` and say whether it is within the limit."""
        now = self.clock()
        q = self.hits.pop(key, None) or deque()
        while q and now - q[0] >= self.window_s:
            q.popleft()
        allowed = len(q) < self.limit
        if allowed:
            q.append(now)
        self.hits[key] = q  # re-inserted: dict order is least recently seen first
        while len(self.hits) > MAX_KEYS:
            self.hits.pop(next(iter(self.hits)))
        return allowed
