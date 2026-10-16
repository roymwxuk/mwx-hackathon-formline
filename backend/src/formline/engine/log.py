"""Append-only event log: the source of truth for everything the engine derives.

Every distinct message that arrives is stored once, in arrival order. A message is
a duplicate if its (event_id, version) is already in the log; duplicates are not
stored. Baselines and insights are derived state and can always be rebuilt from
`current_events()`, which applies "highest version wins" and deletes.
"""

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Protocol

from formline.schema.feed import FeedMessage


class EventLog(Protocol):
    def append(self, msg: FeedMessage) -> bool:
        """Store the message; False if it is a duplicate and was not stored."""
        ...

    def __iter__(self) -> Iterator[FeedMessage]: ...

    def __len__(self) -> int: ...


class MemoryEventLog:
    def __init__(self, messages: Iterable[FeedMessage] = ()):
        self._messages: list[FeedMessage] = []
        self._keys: set[tuple[str, int]] = set()
        for msg in messages:
            self.append(msg)

    def append(self, msg: FeedMessage) -> bool:
        key = (msg.event_id, msg.version)
        if key in self._keys:
            return False
        self._keys.add(key)
        self._messages.append(msg)
        return True

    def __iter__(self) -> Iterator[FeedMessage]:
        return iter(self._messages)

    def __len__(self) -> int:
        return len(self._messages)


class JsonlEventLog(MemoryEventLog):
    """Same semantics, persisted as one JSON line per stored message.

    Postgres replaces this in the Azure deployment; the interface stays the same.
    """

    def __init__(self, path: Path):
        self.path = path
        existing = []
        if path.exists():
            with path.open(encoding="utf-8") as f:
                existing = [FeedMessage.model_validate_json(line) for line in f if line.strip()]
        super().__init__(existing)
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, msg: FeedMessage) -> bool:
        if not super().append(msg):
            return False
        with self.path.open("a", encoding="utf-8") as f:
            f.write(msg.model_dump_json() + "\n")
        return True


def current_events(log: Iterable[FeedMessage]) -> list:
    """Final state of every event: highest version wins, deletes remove.

    Sorted by event time, so a batch rebuild sees events in the order they happened.
    """
    best: dict[str, FeedMessage] = {}
    for msg in log:
        prev = best.get(msg.event_id)
        if prev is None or msg.version > prev.version:
            best[msg.event_id] = msg
    events = [m.event for m in best.values() if m.op != "delete" and m.event is not None]
    return sorted(events, key=lambda e: (e.event_time, e.event_id))
