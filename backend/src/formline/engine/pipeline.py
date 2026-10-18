"""Live pipeline: feed message → ingestion → baselines → insights (with lineage)."""

from dataclasses import dataclass, field

from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Change, Ingestor, Revised
from formline.engine.insights import InsightChange, InsightTracker
from formline.schema.feed import FeedMessage


@dataclass
class LivePipeline:
    engine: BaselineEngine
    ingestor: Ingestor = field(default_factory=Ingestor)
    tracker: InsightTracker = field(default_factory=InsightTracker)

    def process(self, msg: FeedMessage) -> list[InsightChange]:
        return [ic for change in self.ingestor.ingest(msg) for ic in self._handle(change)]

    def flush(self) -> list[InsightChange]:
        return [ic for change in self.ingestor.flush() for ic in self._handle(change)]

    def advance_to(self, now) -> list[InsightChange]:
        """Idle timeout (see Ingestor.advance_to)."""
        return [ic for change in self.ingestor.advance_to(now) for ic in self._handle(change)]

    def run(self, feed: list[FeedMessage]) -> list[InsightChange]:
        out = [ic for msg in feed for ic in self.process(msg)]
        return out + self.flush()

    def _handle(self, change: Change) -> list[InsightChange]:
        comparisons = self.engine.apply(change)
        out = self.tracker.on_comparisons(comparisons)
        if isinstance(change, Revised) and change.before.type == "shot" and (
                change.after is None or change.after.type != "shot"):
            out += self.tracker.on_deleted(change.before.event_id)
        return out
