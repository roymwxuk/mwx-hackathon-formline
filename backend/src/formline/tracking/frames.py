"""Tracking frames for the stream: the frame at a match time, as a ready JSON message.

Frames are kept as their compact JSON lines (about 23 MB for a match) rather than parsed
objects (which would take several times more memory in a small container), and a frame
message is built by string splicing: `{"kind":"frame","p":1,"t":…,"b":…,"h":…,"a":…}`.
"""

import gzip
import json
from functools import lru_cache
from pathlib import Path

from formline.schema.tracking import FRAME_MS


class FrameIndex:
    def __init__(self, lines_by_period: dict[int, tuple[int, list[str]]]):
        self.periods = lines_by_period  # period -> (first frame's ms, lines)

    def message(self, period: int, match_clock_ms: int) -> str | None:
        """The stream message for the frame nearest this match time, or None."""
        entry = self.periods.get(period)
        if entry is None:
            return None
        start, lines = entry
        i = round((match_clock_ms - start) / FRAME_MS)
        if not 0 <= i < len(lines):
            return None
        return '{"kind":"frame",' + lines[i][1:]


def load_frames(path: Path) -> FrameIndex:
    periods: dict[int, tuple[int, list[str]]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            head = json.loads(line[: line.index(',"b"')] + "}")  # just "p" and "t"
            period, t = head["p"], head["t"]
            if period not in periods:
                periods[period] = (t, [])
            periods[period][1].append(line)
    return FrameIndex(periods)


@lru_cache(maxsize=2)
def cached_frames(path: Path, mtime: float) -> FrameIndex:
    """Loaded once per file version (mtime is part of the key)."""
    return load_frames(path)


def frames_for(path: Path) -> FrameIndex | None:
    return cached_frames(path, path.stat().st_mtime) if path.exists() else None
