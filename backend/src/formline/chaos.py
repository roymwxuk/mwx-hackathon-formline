"""Chaos injector: make a clean feed misbehave the way real provider feeds do.

Every message gets an arrival time (its `emitted_at`), the schedule is damaged, and
messages are delivered in arrival order:

- duplicate   the same message (same message_id) delivered again a little later
- reorder     small jitter, within the ingestor's reorder window
- late        a long delay, beyond the window, so the event arrives "late"
- correction  a newer version of a shot with a changed outcome or shooter;
              some are reverted later by a further version restoring the original
- delete      the event is retracted entirely (off by default)

Nothing is dropped: missing-data inference is out of scope. The provider's
`emitted_at` and `sequence` stay on each message; only delivery order changes.
Injected corrections get new, higher versions and new sequence numbers.

Deterministic for a given seed, so a failing convergence case can be replayed.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from formline.schema.feed import FeedMessage

OUTCOME_SWAPS = {
    "goal": "saved",
    "saved": "off_target",
    "off_target": "saved",
    "post": "off_target",
    "blocked": "off_target",
}


@dataclass(frozen=True)
class ChaosConfig:
    seed: int = 0
    duplicate_rate: float = 0.03
    reorder_rate: float = 0.05
    reorder_max_s: float = 3.0  # stays inside the default 5 s reorder window
    late_rate: float = 0.01
    late_delay_s: tuple[float, float] = (6.0, 30.0)  # beyond the window
    correction_rate: float = 0.15  # share of eligible shots that get a correction
    revert_rate: float = 0.5  # share of corrections later reverted
    delete_rate: float = 0.0  # share of events retracted entirely


@dataclass
class ChaosReport:
    messages_in: int = 0
    messages_out: int = 0
    duplicates: int = 0
    reordered: int = 0
    late: int = 0
    corrections: int = 0
    reverts: int = 0
    deletes: int = 0
    corrected_event_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChaosResult:
    messages: list[FeedMessage]
    report: ChaosReport


def _correct(msg: FeedMessage, version: int, seq: int, at: datetime, rng: random.Random,
             teammates: list[str]) -> FeedMessage:
    """A newer version of a shot: outcome changed, or (sometimes) the shooter."""
    event = msg.event
    others = [p for p in teammates if p != event.player_id]
    if others and rng.random() < 0.3:
        changed = event.model_copy(update={"player_id": rng.choice(others)})
    else:
        changed = event.model_copy(update={"outcome": OUTCOME_SWAPS[event.outcome]})
    return FeedMessage(message_id=f"{msg.message_id}_c{version}", op="update",
                       event_id=msg.event_id, version=version, emitted_at=at, sequence=seq,
                       event=changed)


def inject(feed: list[FeedMessage], config: ChaosConfig | None = None) -> ChaosResult:
    config = config or ChaosConfig()
    rng = random.Random(f"chaos:{config.seed}")
    report = ChaosReport(messages_in=len(feed))
    schedule: list[tuple[datetime, int, FeedMessage]] = []  # (arrival, tiebreak, message)
    tiebreak = 0
    next_seq = max((m.sequence for m in feed), default=0) + 1

    def deliver(at: datetime, msg: FeedMessage) -> None:
        nonlocal tiebreak
        schedule.append((at, tiebreak, msg))
        tiebreak += 1

    # Shots that already have an update (e.g. the VAR overturn) are left alone, so
    # injected versions never collide with real ones.
    updated = {m.event_id for m in feed if m.op != "create"}
    max_version = {}
    for m in feed:
        max_version[m.event_id] = max(max_version.get(m.event_id, 0), m.version)
    squads: dict[str, set[str]] = {}
    for m in feed:
        if m.event is not None and m.event.team_id and m.event.player_id:
            squads.setdefault(m.event.team_id, set()).add(m.event.player_id)

    for msg in feed:
        arrival = msg.emitted_at
        if rng.random() < config.late_rate:
            arrival += timedelta(seconds=rng.uniform(*config.late_delay_s))
            report.late += 1
        elif rng.random() < config.reorder_rate:
            arrival += timedelta(seconds=rng.uniform(0.2, config.reorder_max_s))
            report.reordered += 1
        deliver(arrival, msg)

        if rng.random() < config.duplicate_rate:
            deliver(arrival + timedelta(seconds=rng.uniform(0.1, 10.0)), msg)
            report.duplicates += 1

        event = msg.event
        if msg.op != "create" or event is None:
            continue
        if event.type == "shot" and msg.event_id not in updated \
                and rng.random() < config.correction_rate:
            version = max_version[msg.event_id] + 1
            at = arrival + timedelta(seconds=rng.uniform(20, 120))
            teammates = sorted(squads.get(event.team_id, ()))
            correction = _correct(msg, version, next_seq, at, rng, teammates)
            next_seq += 1
            deliver(at, correction)
            report.corrections += 1
            report.corrected_event_ids.append(msg.event_id)
            max_version[msg.event_id] = version
            if rng.random() < config.revert_rate:
                version += 1
                revert = FeedMessage(
                    message_id=f"{msg.message_id}_r{version}", op="update",
                    event_id=msg.event_id, version=version,
                    emitted_at=at + timedelta(seconds=rng.uniform(10, 90)), sequence=next_seq,
                    event=event)
                next_seq += 1
                deliver(revert.emitted_at, revert)
                report.reverts += 1
                max_version[msg.event_id] = version
        elif config.delete_rate and rng.random() < config.delete_rate:
            version = max_version[msg.event_id] + 1
            at = arrival + timedelta(seconds=rng.uniform(5, 60))
            deliver(at, FeedMessage(message_id=f"{msg.message_id}_d{version}", op="delete",
                                    event_id=msg.event_id, version=version, emitted_at=at,
                                    sequence=next_seq, event=None))
            next_seq += 1
            report.deletes += 1
            max_version[msg.event_id] = version

    schedule.sort(key=lambda s: (s[0], s[1]))
    messages = [m for _, _, m in schedule]
    report.messages_out = len(messages)
    return ChaosResult(messages, report)
