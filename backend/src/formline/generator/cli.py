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
DEFAULT_SCHEMA = BACKEND.parent / "docs" / "contracts" / "overlay.schema.json"
DEFAULT_EXAMPLES = BACKEND / "data" / "sample" / "overlays.example.json"


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
    ovl = sub.add_parser("overlays", help="run the agents over a match and cache its overlays")
    ovl.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ovl.add_argument("--match", default=None, help="match id (default: the live demo match)")
    con = sub.add_parser("contracts", help="write the overlay JSON Schema and example overlays")
    con.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    if args.command == "overlays":
        return _overlays(args.data, args.match)

    if args.command == "contracts":
        from formline.agents.examples import write_contracts
        write_contracts(DEFAULT_SCHEMA, DEFAULT_EXAMPLES, args.seed)
        print(f"wrote {DEFAULT_SCHEMA} and {DEFAULT_EXAMPLES}")
        return 0

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


def _overlays(data: Path, match_id: str | None) -> int:
    import asyncio
    import json

    from formline.agents.precompute import default_runner, precompute, summary_dict
    from formline.engine.bootstrap import bootstrap_history

    if match_id is None:
        matches = json.loads((data / "matches.json").read_text())
        match_id = next(m["match_id"] for m in matches if m["is_live_demo"])
    runner = default_runner(data)
    path, summary, runner = asyncio.run(precompute(data, match_id, bootstrap_history(data),
                                                   runner))
    print(f"wrote {path}")
    print(json.dumps(summary_dict(summary, runner), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
