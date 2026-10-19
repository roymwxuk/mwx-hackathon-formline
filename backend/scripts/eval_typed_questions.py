"""Real-model evaluation of typed questions (docs/plan-agentic-research.md, review point 6).

Usage: uv run python scripts/eval_typed_questions.py [--only d01,c01] [--out FILE]
Asks every question in scripts/typed_questions.json through `answer_free`, in process (no
rate limit), as of the stated match minute of the live match. Each row records the outcome,
the lookups, the answer, model calls and latency; relevance is scored by hand afterwards,
separately from verifier acceptance. Uses a fresh response cache, so every call is real
(with AZURE_AI_PROJECT_ENDPOINT set) and the shared cache is untouched.
"""

import argparse
import asyncio
import json
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from formline.agents.llm import LLMConfig, make_runner
from formline.agents.precompute import FakeAgents
from formline.analyst.ask import answer_free
from formline.analyst.store import match_context
from formline.config import settings
from formline.engine.bootstrap import bootstrap_history
from formline.generator.output import read_feed

HERE = Path(__file__).resolve().parent
LIVE = "mtc_s26_md11_har_nor"


def as_of(feed, minute: float) -> tuple[str, int]:
    """The last message at or before `minute`: what a viewer at that minute has received."""
    last = feed[0]
    for msg in feed:
        if msg.event.match_clock_ms > minute * 60_000:
            break
        last = msg
    return last.event_id, last.version


async def run(questions: list[dict], out: Path) -> None:
    data = settings.data_dir
    feed = read_feed(data / "feeds" / f"{LIVE}.jsonl")
    ctx = match_context(data, LIVE)
    norm = bootstrap_history(data).season_norm
    league = json.loads((data / "league.json").read_text(encoding="utf-8"))
    short = {c["club_id"]: c["short_name"] for c in league["clubs"]}
    cache = Path(tempfile.mkdtemp()) / "eval_cache.jsonl"
    runner = make_runner(replace(LLMConfig.from_settings(), max_calls=400),
                         fake_responder=FakeAgents(), cache_path=cache)
    print(f"model: {runner.kind}; {len(questions)} questions -> {out}")
    with out.open("w", encoding="utf-8") as f:
        for q in questions:
            event_id, version = as_of(feed, float(q["at"]))
            calls = runner.budget.calls
            t0 = time.perf_counter()
            try:
                res = await answer_free(event_id, version, q["text"], q["lang"], feed, ctx,
                                        runner, norm=norm, short_names=short)
                error = None
            except Exception as exc:  # noqa: BLE001 - recorded: the eval measures failures too
                res, error = {}, f"{type(exc).__name__}: {exc}"
            row = {**q, "model": runner.kind, "outcome": res.get("outcome"),
                   "calls": runner.budget.calls - calls,
                   "seconds": round(time.perf_counter() - t0, 2),
                   "research": res.get("research"), "retrieved": res.get("retrieved"),
                   "answer": res.get("answer"), "declined": res.get("declined"), "error": error}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{q['id']:>4} {row['outcome'] or error!s:<18} calls={row['calls']} "
                  f"{row['seconds']:>5}s")
    print(f"total model calls: {runner.budget.calls}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated question ids")
    ap.add_argument("--out", type=Path, default=Path("eval-typed-questions.jsonl"))
    args = ap.parse_args()
    questions = json.loads((HERE / "typed_questions.json").read_text(encoding="utf-8"))
    if args.only:
        keep = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in keep]
    asyncio.run(run(questions, args.out))


if __name__ == "__main__":
    main()
