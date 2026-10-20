"""Offline review aggregation must preserve provenance and score denominators."""

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCORER = runpy.run_path(str(ROOT / "backend/scripts/score_typed_questions.py"))
REVIEW = ROOT / "docs/eval/typed-questions-baseline.review.json"


def copy_review(tmp_path):
    review = json.loads(REVIEW.read_text())
    for artifact in review["artifacts"].values():
        artifact["path"] = str((REVIEW.parent / artifact["path"]).resolve())
    target = tmp_path / "review.json"
    target.write_text(json.dumps(review))
    return target, review


def test_baseline_metrics_keep_relevance_separate_from_strict_quality():
    summary, cases, _ = SCORER["evaluate"](REVIEW)
    assert summary["total"] == 38
    assert summary["historical_answerable_relevance"] == {"pass": 26, "total": 27}
    assert summary["dimensions"]["decision"] == {"pass": 37, "fail": 1}
    assert set(summary["failure_ids"]) == {"d06", "r01", "o03", "j04"}
    assert "d07" in summary["uncertain_ids"]
    assert summary["runtime"]["calls"] == 127
    assert summary["groups"]["lang"]["ja"]["total"] == 6
    assert summary["groups"]["expected_decisions"]["correct_false_premise"]["total"] == 4
    assert len(cases) == 38


@pytest.mark.parametrize("problem", ["duplicate", "missing", "decision", "score", "payload"])
def test_invalid_reviews_are_rejected(tmp_path, problem):
    path, review = copy_review(tmp_path)
    if problem == "duplicate":
        review["cases"][1]["id"] = review["cases"][0]["id"]
    elif problem == "missing":
        review["cases"].pop()
    elif problem == "decision":
        review["cases"][0]["scores"]["decision"] = "fail"
    elif problem == "score":
        review["cases"][0]["scores"]["grounding"] = "maybe"
    else:
        review["cases"][0]["expected_decisions"] = ["decline"]
        review["cases"][0]["observed_decision"] = "decline"
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError):
        SCORER["evaluate"](path)


def test_changed_evidence_is_rejected(tmp_path):
    path, review = copy_review(tmp_path)
    evidence = tmp_path / "changed.json"
    evidence.write_text("{}")
    review["artifacts"]["evidence"]["path"] = str(evidence)
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="hash mismatch"):
        SCORER["evaluate"](path)


def test_cli_preserves_existing_output(tmp_path, monkeypatch):
    output, markdown = tmp_path / "out.json", tmp_path / "out.md"
    output.write_text("historical output")
    monkeypatch.setattr("sys.argv", ["score", "--review", str(REVIEW), "--out", str(output),
                                   "--markdown", str(markdown)])
    with pytest.raises(SystemExit):
        SCORER["main"]()
    assert output.read_text() == "historical output"
    assert not markdown.exists()
