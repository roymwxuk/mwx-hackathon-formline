"""Ingestion: turn a messy live feed into an ordered stream of changes.

Real feeds deliver duplicates, out-of-order messages and corrections. The ingestor
stores every message in the append-only log, then:

- drops duplicates (same event_id and version);
- holds events in a reorder buffer and releases them in **event-time** order once
  the watermark (latest event time seen minus `window`) has passed them;
- applies "highest version wins": a newer version of a buffered event simply
  replaces it, while a newer version (or delete) of an already released event
  becomes a `Revised` change so downstream state can roll back and re-apply;
- releases events that arrive after the watermark immediately, flagged `late`.

Downstream consumers (the baseline engine) only ever see `Applied` and `Revised`.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from formline.engine.log import EventLog, MemoryEventLog
from formline.schema.feed import FeedMessage

DEFAULT_WINDOW = timedelta(seconds=5)


@dataclass(frozen=True)
class Applied:
    """A new event, released in event-time order (or immediately, if late)."""

    event: object
    late: bool = False


@dataclass(frozen=True)
class Revised:
    """An already released event changed: `after` is None when it was deleted."""

    before: object
    after: object | None
    version: int


Change = Applied | Revised


@dataclass
class IngestStats:
    received: int = 0
    duplicates: int = 0
    stale: int = 0  # older version than the one already known
    late: int = 0
    revisions: int = 0
    released: int = 0
    orphans: int = 0  # deletes for events never seen


@dataclass
class _Known:
    version: int
    event: object | None  # None once deleted
    released: bool


@dataclass
class Ingestor:
    log: EventLog = field(default_factory=MemoryEventLog)
    window: timedelta = DEFAULT_WINDOW
    stats: IngestStats = field(default_factory=IngestStats)

    def __post_init__(self) -> None:
        self._known: dict[str, _Known] = {}
        self._buffer: dict[str, object] = {}
        self._max_event_time: datetime | None = None

    @property
    def watermark(self) -> datetime | None:
        return None if self._max_event_time is None else self._max_event_time - self.window

    def ingest(self, msg: FeedMessage) -> list[Change]:
        self.stats.received += 1
        if not self.log.append(msg):
            self.stats.duplicates += 1
            return []

        known = self._known.get(msg.event_id)
        if known and msg.version <= known.version:
            self.stats.stale += 1
            return []

        changes: list[Change] = []
        if msg.op == "delete":
            if known is None:
                self.stats.orphans += 1
                self._known[msg.event_id] = _Known(msg.version, None, released=True)
                return []
            if known.released and known.event is not None:
                changes.append(Revised(known.event, None, msg.version))
                self.stats.revisions += 1
            self._buffer.pop(msg.event_id, None)
            self._known[msg.event_id] = _Known(msg.version, None, released=True)
            return changes

        event = msg.event
        if known and known.released and known.event is not None:
            # Correction of something downstream has already seen.
            self._known[msg.event_id] = _Known(msg.version, event, released=True)
            self.stats.revisions += 1
            return [Revised(known.event, event, msg.version)]

        wm = self.watermark
        if known is None and wm is not None and event.event_time <= wm:
            # Arrived after its slot was released: apply now, flagged late.
            self._known[msg.event_id] = _Known(msg.version, event, released=True)
            self.stats.late += 1
            self.stats.released += 1
            changes.append(Applied(event, late=True))
        else:
            # New, or a newer version of an event still waiting in the buffer.
            self._known[msg.event_id] = _Known(msg.version, event, released=False)
            self._buffer[msg.event_id] = event
            if self._max_event_time is None or event.event_time > self._max_event_time:
                self._max_event_time = event.event_time
        changes.extend(self._release(self.watermark))
        return changes

    def flush(self) -> list[Change]:
        """End of stream: release everything still buffered."""
        return self._release(None)

    def advance_to(self, now: datetime) -> list[Change]:
        """Idle timeout: no message has arrived for a while, so time moves on anyway.

        Without this the watermark only moves when the next message arrives, and after a
        goal (no events for half a minute) its insight would wait for whatever comes next.
        The watermark advances to `now` minus the window; events still buffered behind it
        are released, and anything older that arrives later is flagged late as usual.
        """
        if self._max_event_time is None or now > self._max_event_time:
            self._max_event_time = now
        return self._release(self.watermark)

    def _release(self, upto: datetime | None) -> list[Change]:
        ready = [e for e in self._buffer.values() if upto is None or e.event_time <= upto]
        ready.sort(key=lambda e: (e.event_time, e.event_id))
        for event in ready:
            del self._buffer[event.event_id]
            self._known[event.event_id].released = True
        self.stats.released += len(ready)
        return [Applied(e) for e in ready]


def ingest_all(feed: list[FeedMessage], ingestor: Ingestor | None = None) -> list[Change]:
    """Run a whole feed through ingestion, including the final flush."""
    ing = ingestor or Ingestor()
    changes = [c for msg in feed for c in ing.ingest(msg)]
    return changes + ing.flush()
