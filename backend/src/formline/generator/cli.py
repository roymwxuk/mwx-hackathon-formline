"""`formline-gen`: generate the synthetic season and its realism report."""

import argparse
import sys
from pathlib import Path

from formline.generator.output import write_season
from formline.generator.report import compute, render
from formline.generator.season import generate_season

DEFAULT_SEED = 2026
BACKEND = Path(__file__).resolve().parents[3]
DEFAULT_DATA = BACKEND / "data"
DEFAULT_REPORT = BACKEND.parent / "docs" / "realism-report.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="formline-gen")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="generate league, 30 past matches and the live match")
    gen.add_argument("--seed", type=int, default=DEFAULT_SEED)
    gen.add_argument("--out", type=Path, default=DEFAULT_DATA)
    rep = sub.add_parser("report", help="write the realism report from generated data")
    rep.add_argument("--data", type=Path, default=DEFAULT_DATA)
    rep.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    rep.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    if args.command == "generate":
        season = generate_season(args.seed)
        write_season(season, args.out)
        n = sum(len(m.feed) for m in season.matches)
        print(f"wrote {len(season.matches)} matches, {n} feed messages to {args.out}")
        return 0

    checks, extra = compute(args.data)
    args.out.write_text(render(checks, extra, args.seed), encoding="utf-8")
    for c in checks:
        print(f"{'ok ' if c.ok else 'OUT'} {c.metric}: {c.fmt.format(c.value)}")
    print(f"wrote {args.out}")
    return 0 if all(c.ok for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
