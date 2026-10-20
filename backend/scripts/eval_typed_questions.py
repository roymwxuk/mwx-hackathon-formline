"""Real-model smoke evaluation of typed questions (docs/plan-typed-question-eval.md).

Usage: uv run python scripts/eval_typed_questions.py --out FILE.jsonl [--only d01,c01]
Asks every question in scripts/typed_questions.json through `answer_free`, in process (no
rate limit), as of the stated minute of the live match. Each row records the outcome, the
lookups, the answer, model calls, cache hits and latency, plus the gold facts: the
deterministic sections that answer the question, rendered with real names, to score the
answer against by hand. FILE.meta.json records what was run (commit, prompts, model, data).
Uses a fresh response cache, so calls are real (with AZURE_AI_PROJECT_ENDPOINT set) and the
shared cache is untouched. Never overwrites a previous run: reruns get their own file.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from formline.agents.llm import LLMConfig, make_runner
from formline.agents.precompute import FakeAgents
from formline.analyst.ask import answer_free, moment_as_of
from formline.analyst.sections import facts_for
from formline.analyst.store import match_context
from formline.config import settings
from formline.engine.bootstrap import bootstrap_history
from formline.generator.output import read_feed
from formline.prompts import DIR as PROMPTS
from formline.prompts import load

HERE = Path(__file__).resolve().parent
QUESTIONS = HERE / "typed_questions.json"
LIVE = "mtc_s26_md11_har_nor"
ROLE = re.compile(r"\b[A-Z]+_[A-Z]+\b")  # role placeholders: PLAYER_A, SCORER_A, CHANCE_B


def as_of(feed, minute: float) -> tuple[str, int]:
    """The last message at or before `minute`: what a viewer at that minute has received."""
    last = feed[0]
    for msg in feed:
        if msg.event.match_clock_ms > minute * 60_000:
            break
        last = msg
    return last.event_id, last.version


class AskLog(logging.Handler):
    """Keeps the last `ask_free` log record: the Analyst's attempts and rejection reasons, as
    production logs them."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.last: dict | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            data = json.loads(record.getMessage())
        except ValueError:
            return
        if data.get("event") == "ask_free":
            self.last = data


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, cwd=HERE, check=True)
    return done.stdout.strip()


def meta(runner, data: Path) -> dict:
    return {"started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "commit": git("rev-parse", "--short", "HEAD"),
            "dirty": bool(git("status", "--porcelain", "--", "..")),
            "model": runner.kind,
            "deployment": runner.config.deployment if runner.kind == "foundry" else None,
            "prompts": sorted(load(p.stem).ref for p in PROMPTS.glob("*.md")),
            "match_id": LIVE,
            "data": {name: sha(data / name) for name in
                     (f"feeds/{LIVE}.jsonl", "league.json", "matches.json")},
            "questions": sha(QUESTIONS)}


def gold_facts(gold: dict | None, m, ctx, norm) -> dict | None:
    """The sections that answer the question, computed by the engine, with real names."""
    if gold is None:
        return None
    pack = facts_for(gold["sections"], m, gold.get("club_id"), gold.get("player_id"),
                     ctx.info, ctx.records, ctx.player_seasons, norm, history=ctx.history,
                     n=gold.get("n"))
    names = {role: ctx.league.players[pid][0] for role, pid in pack.roles.items()}
    text = json.dumps(pack.facts, ensure_ascii=False)
    return json.loads(ROLE.sub(lambda r: names.get(r.group(), r.group()), text))


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
    out.with_suffix(".meta.json").write_text(
        json.dumps(meta(runner, data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    asklog = AskLog()
    logger = logging.getLogger("formline.ask")
    logger.addHandler(asklog)
    logger.setLevel(logging.INFO)
    print(f"model: {runner.kind}; {len(questions)} questions -> {out}")
    with out.open("x", encoding="utf-8") as f:
        for q in questions:
            if "event" in q:  # pinned to one feed version, e.g. a goal before its correction
                event_id, v = q["event"].split("/")
                version = int(v)
            else:
                event_id, version = as_of(feed, float(q["at"]))
            m, _ = moment_as_of(event_id, version, feed, ctx, norm)
            calls, hits = runner.budget.calls, runner.cache_hits
            asklog.last = None
            t0 = time.perf_counter()
            try:
                res = await answer_free(event_id, version, q["text"], q["lang"], feed, ctx,
                                        runner, norm=norm, short_names=short)
                error = None
            except Exception as exc:  # noqa: BLE001 - recorded: the eval measures failures too
                res, error = {}, f"{type(exc).__name__}: {exc}"
            answer = res.get("answer")
            row = {**q, "event_id": event_id, "version": version, "outcome": res.get("outcome"),
                   "calls": runner.budget.calls - calls, "cache_hits": runner.cache_hits - hits,
                   "seconds": round(time.perf_counter() - t0, 2),
                   "research": res.get("research"), "retrieved": res.get("retrieved"),
                   "answer": asdict(answer) if hasattr(answer, "__dataclass_fields__") else answer,
                   "declined": res.get("declined"), "error": error,
                   "analyst": {k: (asklog.last or {}).get(k)
                               for k in ("source", "attempts", "rejections", "fallback_reason")},
                   "gold_facts": gold_facts(q.get("gold"), m, ctx, norm)}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{q['id']:>4} {row['outcome'] or error!s:<18} calls={row['calls']} "
                  f"hits={row['cache_hits']} {row['seconds']:>5}s")
    print(f"total model calls: {runner.budget.calls}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True, help="a new .jsonl file")
    ap.add_argument("--only", help="comma-separated question ids")
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit(f"{args.out} exists: give each run its own file")
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if args.only:
        keep = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in keep]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(run(questions, args.out))


if __name__ == "__main__":
    main()
