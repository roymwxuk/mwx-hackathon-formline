"""Stage b: aggregate events into match state and statistics."""

from collections import Counter, defaultdict
from math import hypot

from pydantic import BaseModel

from formline.models import EventType, MatchEvent


class MatchState(BaseModel):
    score: dict[str, int] = {}
    passes: dict[str, int] = {}
    pass_accuracy: dict[str, float] = {}
    shots: dict[str, int] = {}
    possession_pct: dict[str, float] = {}
    last_minute: int = 0


class Interpreter:
    def __init__(self) -> None:
        self.score: Counter[str] = Counter()
        self.passes: Counter[str] = Counter()
        self.completed: Counter[str] = Counter()
        self.shots: Counter[str] = Counter()
        self.touches: defaultdict[str, int] = defaultdict(int)
        self.last_minute = 0

    def update(self, ev: MatchEvent) -> MatchState:
        self.last_minute = ev.minute
        self.touches[ev.team] += 1
        if ev.type == EventType.PASS:
            self.passes[ev.team] += 1
            if ev.outcome == "success":
                self.completed[ev.team] += 1
        elif ev.type in (EventType.SHOT, EventType.GOAL):
            self.shots[ev.team] += 1
            if ev.type == EventType.GOAL:
                self.score[ev.team] += 1
        return self.state()

    def state(self) -> MatchState:
        total = sum(self.touches.values()) or 1
        return MatchState(
            score=dict(self.score),
            passes=dict(self.passes),
            pass_accuracy={t: round(self.completed[t] / n, 3) for t, n in self.passes.items()},
            shots=dict(self.shots),
            possession_pct={t: round(100 * n / total, 1) for t, n in self.touches.items()},
            last_minute=self.last_minute,
        )


def pass_difficulty(ev: MatchEvent) -> float | None:
    """0-1 heuristic: longer, more forward passes are harder."""
    if ev.type != EventType.PASS or ev.end_x is None or ev.end_y is None:
        return None
    dist = hypot(ev.end_x - ev.x, ev.end_y - ev.y)
    forward = max(0.0, ev.end_x - ev.x) / 100
    return round(min(1.0, dist / 60 + forward), 2)
