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
        """The stream message for this match time, or None outside the tracking.

        Frames are stored every 100 ms but clock messages fall anywhere in between; the two
        neighbouring frames are blended to the exact time, so at 1x consecutive frames step
        exactly 0.25 s of match time (the nearest frame alternated 0.2 and 0.3 s, a visible
        speed wobble)."""
        entry = self.periods.get(period)
        if entry is None:
            return None
        start, lines = entry
        pos = (match_clock_ms - start) / FRAME_MS
        i = int(pos // 1)
        if not 0 <= i < len(lines):
            return None
        u = pos - i
        if u < 1e-6 or i + 1 >= len(lines):
            return '{"kind":"frame",' + lines[i][1:]
        a, b = json.loads(lines[i]), json.loads(lines[i + 1])
        return json.dumps({"kind": "frame", "p": period, "t": match_clock_ms,
                           "b": _lerp(a["b"], b["b"], u),
                           "h": _lerp_side(a["h"], b["h"], u),
                           "a": _lerp_side(a["a"], b["a"], u)}, separators=(",", ":"))


def _lerp(a: list, b: list, u: float) -> list:
    return [round(x + (y - x) * u, 1) for x, y in zip(a, b, strict=True)]


def _lerp_side(a: list, b: list, u: float) -> list:
    """Blend [shirt, x, y] rows by shirt; a player only in one frame (a substitution) is
    taken from the nearer frame."""
    nxt = {row[0]: row for row in b}
    if u >= 0.5 and {row[0] for row in a} != set(nxt):
        return b
    return [[r[0], *_lerp(r[1:], nxt[r[0]][1:], u)] if r[0] in nxt else r for r in a]


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
