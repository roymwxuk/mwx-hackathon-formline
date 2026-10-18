"""Realism checks for the synthetic tracking (milestone T6, ADR-010).

Informational, unlike the event-data checks: the report shows how the modeled movement
compares with typical elite-football figures, including where it falls short (smoother
motion means less running), but the build does not fail on them.
"""

from collections import defaultdict
from collections.abc import Iterable
from statistics import median

from formline.generator.report import Check
from formline.pitch import PITCH_LENGTH_M, PITCH_WIDTH_M, to_m
from formline.schema.tracking import FRAME_MS, TrackingFrame
from formline.tracking.anchors import Anchor

HIGH_SPEED = 7.0  # m/s (about 25 km/h): sprinting
STEP = 5  # measure movement over 0.5 s: positions are stored to 0.1 units (about 10 cm), so
# frame-to-frame (0.1 s) speeds would carry up to about 1 m/s of rounding noise
KEEPER_SHIRTS = {1, 13}
ASSUMED = "typical elite figures (assumption)"


def tracking_checks(frames: Iterable[TrackingFrame], anchors: list[Anchor] | None = None
                    ) -> tuple[list[Check], dict]:
    dt = FRAME_MS / 1000 * STEP
    dist: dict[tuple[str, int], float] = defaultdict(float)
    secs: dict[tuple[str, int], float] = defaultdict(float)
    fast: dict[tuple[str, int], float] = defaultdict(float)
    top: dict[tuple[str, int], float] = defaultdict(float)
    lengths, widths = [], []
    by_time: dict[tuple[int, int], TrackingFrame] = {}
    prev: TrackingFrame | None = None
    for n, f in enumerate(frames):
        by_time[(f.period, f.match_clock_ms)] = f
        if n % 10 == 0:  # team shape once a second, home team, outfield players
            out = [p for p in f.home if p.shirt not in KEEPER_SHIRTS]
            if len(out) >= 8:
                lengths.append((max(p.x for p in out) - min(p.x for p in out)) * PITCH_LENGTH_M / 100)
                widths.append((max(p.y for p in out) - min(p.y for p in out)) * PITCH_WIDTH_M / 100)
        if n % STEP:
            continue
        if prev is not None and prev.period == f.period:
            for side, now, before in (("h", f.home, prev.home), ("a", f.away, prev.away)):
                last = {p.shirt: p for p in before}
                for p in now:
                    q = last.get(p.shirt)
                    if q is None:
                        continue
                    key = (side, p.shirt)
                    d = to_m(p.x - q.x, p.y - q.y)
                    dist[key] += d
                    secs[key] += dt
                    fast[key] += dt if d / dt > HIGH_SPEED else 0.0
                    top[key] = max(top[key], d / dt)
        prev = f

    def per90(values: dict, keys: list) -> list[float]:
        return [values[k] * 5400 / secs[k] for k in keys]

    # per-90 figures only for players on the pitch at least 45 minutes
    regular = [k for k in secs if secs[k] >= 45 * 60]
    outfield = [k for k in regular if k[1] not in KEEPER_SHIRTS]
    keepers = [k for k in regular if k[1] in KEEPER_SHIRTS]
    checks = []  # each check only when there is data for it (small test inputs, partial files)
    if outfield:
        checks += [
            Check("Distance per 90, outfield (km)", median(per90(dist, outfield)) / 1000, 9.5, 12.5,
                  ASSUMED, "{:.1f}"),
        ]
    if keepers:
        checks.append(Check("Distance per 90, goalkeepers (km)", median(per90(dist, keepers)) / 1000,
                            4.0, 6.5, ASSUMED, "{:.1f}"))
    if outfield:
        checks += [
            Check("Time above 7 m/s per 90, outfield (s)", median(per90(fast, outfield)), 20, 45,
                  ASSUMED, "{:.0f}"),
            Check("Peak speed, outfield median (m/s)", median(top[k] for k in outfield), 8.0, 9.6,
                  ASSUMED, "{:.1f}"),
        ]
    if lengths:
        checks += [
            Check("Team length, median (m)", median(lengths), 30, 50, ASSUMED, "{:.0f}"),
            Check("Team width, median (m)", median(widths), 35, 55, ASSUMED, "{:.0f}"),
        ]
    if anchors:
        errors = []
        for a in anchors:
            f = by_time.get((a.period, round(a.t_ms / FRAME_MS) * FRAME_MS))
            if f is None:
                continue
            p = next((p for p in (f.home if a.home else f.away) if p.shirt == a.shirt), None)
            if p is not None:
                errors.append(to_m(p.x - a.x, p.y - a.y))
        share = sum(e <= 0.5 for e in errors) / len(errors) * 100
        checks.append(Check("Players on their event spots, within 0.5 m (%)", share, 98, 100,
                            "Formline target (ADR-010)", "{:.1f}"))
    spread = per90(dist, outfield) or [0.0]
    extra = {"players": len(regular), "frames": len(by_time),
             "distance_range": (min(spread) / 1000, max(spread) / 1000)}
    return checks, extra
