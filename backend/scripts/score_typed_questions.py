"""Validate saved review judgments and summarize one frozen run; never calls a model.

Usage: python scripts/score_typed_questions.py --review ../docs/eval/FILE.review.json
       --out ../docs/eval/FILE.scores.json --markdown ../docs/eval/FILE.scores.md
Judgments are manual. This script checks provenance/coverage and calculates metrics;
it does not decide whether natural-language answers are correct.
"""

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

DIMENSIONS = ("decision", "relevance", "factual_accuracy", "grounding", "coverage", "language")
SCORES = {"pass", "fail", "uncertain", "not_applicable"}
DECISIONS = {"answer", "clarify", "decline", "correct_false_premise"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(review_path: Path) -> tuple[dict, list[dict], dict]:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("schema_version") != 1:
        raise ValueError("unsupported review schema")
    for key in ("reviewer", "reviewed_at", "rubric_version"):
        if not review.get(key):
            raise ValueError(f"missing {key}")
    for artifact in review["artifacts"].values():
        if digest(review_path.parent / artifact["path"]) != artifact["sha256"]:
            raise ValueError(f"artifact hash mismatch: {artifact['path']}")
    raw = review_path.parent / review["artifacts"]["run"]["path"]
    rows = [json.loads(s) for s in raw.read_text(encoding="utf-8").splitlines() if s.strip()]
    cases = review["cases"]
    ids, scored_ids = [r["id"] for r in rows], [c["id"] for c in cases]
    if len(set(ids)) != len(ids) or len(set(scored_ids)) != len(scored_ids):
        raise ValueError("duplicate case IDs")
    if set(ids) != set(scored_ids):
        raise ValueError("review must cover exactly the run IDs")
    raw_by_id = {r["id"]: r for r in rows}
    for c in cases:
        allowed = c["expected_decisions"]
        if not allowed or not set(allowed) <= DECISIONS:
            raise ValueError(f"invalid expected decisions: {c['id']}")
        if c["observed_decision"] not in DECISIONS:
            raise ValueError(f"invalid observed decision: {c['id']}")
        if set(c["scores"]) != set(DIMENSIONS) or not set(c["scores"].values()) <= SCORES:
            raise ValueError(f"invalid scores: {c['id']}")
        expected_score = "pass" if c["observed_decision"] in allowed else "fail"
        if c["scores"]["decision"] != expected_score:
            raise ValueError(f"decision score disagrees with labels: {c['id']}")
        if not c.get("evidence") or not c.get("criteria") or not c.get("note"):
            raise ValueError(f"missing review evidence/criteria/note: {c['id']}")
        r = raw_by_id[c["id"]]
        if r.get("error"):
            raise ValueError("infrastructure-error rows require a separate review policy")
        if c["observed_decision"] in {"answer", "correct_false_premise"}:
            if not r.get("answer"):
                raise ValueError(f"answer decision without an answer: {c['id']}")
        elif r.get("answer") or not r.get("declined"):
            raise ValueError(f"clarify/decline decision disagrees with payload: {c['id']}")
        if c["observed_decision"] == "clarify" and r.get("outcome") != "clarify":
            raise ValueError(f"clarification disagrees with outcome: {c['id']}")
        values = set(c["scores"].values())
        c["overall"] = "fail" if "fail" in values else (
            "uncertain" if "uncertain" in values else "pass")
    critical = review["critical_suite"]
    if len({c["id"] for c in critical}) != len(critical) or any(c["id"] not in ids for c in critical):
        raise ValueError("invalid critical suite IDs")

    def metrics(group: list[dict]) -> dict:
        return {"total": len(group), "overall": dict(Counter(c["overall"] for c in group)),
                "dimensions": {d: dict(Counter(c["scores"][d] for c in group)) for d in DIMENSIONS}}

    groups = {}
    for field in ("kind", "lang"):
        bucket = defaultdict(list)
        for c in cases:
            bucket[raw_by_id[c["id"]][field]].append(c)
        groups[field] = {k: metrics(v) for k, v in sorted(bucket.items())}
    bucket = defaultdict(list)
    for c in cases:
        bucket["|".join(sorted(c["expected_decisions"]))].append(c)
    groups["expected_decisions"] = {k: metrics(v) for k, v in sorted(bucket.items())}
    latencies = sorted(r["seconds"] for r in rows if r["calls"])
    historical = [c for c in cases if raw_by_id[c["id"]]["kind"] not in
                  {"ambiguous", "out_of_scope", "hostile"}]
    summary = {"schema_version": 1, "reviewer": review["reviewer"],
               "rubric_version": review["rubric_version"], "review_sha256": digest(review_path),
               "artifacts": review["artifacts"], **metrics(cases), "groups": groups,
               "critical_suite": critical,
               "failure_ids": [c["id"] for c in cases if c["overall"] == "fail"],
               "uncertain_ids": [c["id"] for c in cases if c["overall"] == "uncertain"],
               "historical_answerable_relevance": {
                   "pass": sum(c["scores"]["relevance"] == "pass" for c in historical),
                   "total": len(historical)},
               "runtime": {"calls": sum(r["calls"] for r in rows),
                           "cache_hits": sum(r["cache_hits"] for r in rows),
                           "recorded_exceptions": sum(bool(r["error"]) for r in rows),
                           "model_calling_cases": len(latencies),
                           "latency_population": "cases with at least one model call",
                           "quantile_method": "nearest rank; ceil(p*n)-1",
                           "p50_seconds": latencies[math.ceil(.5 * len(latencies)) - 1] if latencies else None,
                           "p90_seconds": latencies[math.ceil(.9 * len(latencies)) - 1] if latencies else None,
                           "token_usage": None, "measured_cost": None}}
    return summary, cases, raw_by_id


def render(summary: dict, cases: list[dict], rows: dict) -> str:
    hist = summary["historical_answerable_relevance"]
    lines = ["# Structured review of the saved 38-question baseline", "",
             "Retrospective manual review by Codex (AI agent), using rubric v1. No new inference.",
             "Original outputs and the prior review report are unchanged. This is one historical",
             "run, not a claim about current HEAD. Reruns are excluded from all totals.", "",
             f"Historical answerable relevance: **{hist['pass']}/{hist['total']}**.",
             f"Strict overall judgments: **{json.dumps(summary['overall'], sort_keys=True)}**.",
             "Overall fails if any dimension fails; otherwise uncertainty stays uncertain.",
             "This stricter retrospective rubric includes grounding and language, so overall",
             "results must not be substituted for the original relevance-only metric.", "",
             "## Dimension totals", "", "| Dimension | Pass | Fail | Uncertain | N/A |",
             "|---|---:|---:|---:|---:|"]
    for d, counts in summary["dimensions"].items():
        lines.append(f"| {d} | " + " | ".join(str(counts.get(k, 0)) for k in
                     ("pass", "fail", "uncertain", "not_applicable")) + " |")
    for name, groups in summary["groups"].items():
        lines += ["", f"## By {name}", "", "| Group | Total | Strict pass | Fail | Uncertain |",
                  "|---|---:|---:|---:|---:|"]
        for label, group in groups.items():
            counts = group["overall"]
            lines.append(f"| {label.replace('|', ' or ')} | {group['total']} | " +
                         " | ".join(str(counts.get(k, 0)) for k in ("pass", "fail", "uncertain")) + " |")
    lines += ["", "## Per-case judgments", "",
              "Detailed expected decisions, evidence pointers and criteria are in the review JSON.",
              "", "| ID | Language | Decision | Overall | Review note |", "|---|---|---|---|---|"]
    for c in cases:
        lines.append(f"| {c['id']} | {rows[c['id']]['lang']} | {c['scores']['decision']} | "
                     f"{c['overall']} | {c['note'].replace('|', '/')} |")
    lines += ["", "## Proposed critical regression suite", "",
              "Existing IDs only; selected for future regression runs, not executed again here.",
              "Any future Foundry run needs separate authorization.", ""]
    lines += [f"- `{c['id']}`: {c['reason']}" for c in summary["critical_suite"]]
    r = summary["runtime"]
    lines += ["", "## Runtime and limits", "",
              f"{r['calls']} calls; {r['cache_hits']} cache hits; {r['recorded_exceptions']} recorded exceptions.",
              (f"Among {r['model_calling_cases']} model-calling cases: p50 {r['p50_seconds']} s, "
               f"p90 {r['p90_seconds']} s (nearest rank). Tokens and measured cost unavailable."),
              "", "No baseline attempt telemetry exists. Extra factual evidence was reconstructed",
              "at the review commit; historical-feed hashes were not recorded by the old run.",
              "No claim of independently verified original tool context or unbiased holdout accuracy."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--markdown", type=Path, required=True)
    args = ap.parse_args()
    if args.out.resolve() == args.markdown.resolve() or args.out.exists() or args.markdown.exists():
        ap.error("give both outputs distinct new filenames")
    summary, cases, rows = evaluate(args.review)
    for path, value in ((args.out, json.dumps(summary, indent=2, ensure_ascii=False) + "\n"),
                        (args.markdown, render(summary, cases, rows))):
        with path.open("x", encoding="utf-8") as f:
            f.write(value)


if __name__ == "__main__":
    main()
