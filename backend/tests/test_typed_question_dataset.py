"""The expanded evaluation must preserve its baseline and use valid frozen facts."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

from formline.analyst.ask import moment_as_of
from formline.analyst.store import match_context
from formline.engine.bootstrap import bootstrap_history
from formline.generator.output import read_feed, write_season
from formline.generator.season import generate_season

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "backend/scripts/typed_questions.json"
ORIGINAL = ROOT / "docs/eval/typed-questions-original-38.json"
REFERENCE = ROOT / "docs/eval/typed-questions-expansion-reference.json"
QUESTIONS = json.loads(DATASET.read_text())
NEW = QUESTIONS[38:]
GOLD = json.loads(REFERENCE.read_text())
HELPERS = runpy.run_path(str(ROOT / "backend/scripts/eval_typed_questions.py"))


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    data = tmp_path_factory.mktemp("expanded-eval")
    write_season(generate_season(2026), data)
    feed = read_feed(data / "feeds" / f"{HELPERS['LIVE']}.jsonl")
    return feed, match_context(data, HELPERS["LIVE"]), bootstrap_history(data).season_norm


def test_fifty_unique_cases_preserve_the_original_baseline():
    assert len(QUESTIONS) == len({q["id"] for q in QUESTIONS}) == 50
    assert QUESTIONS[:38] == json.loads(ORIGINAL.read_text())
    baseline = json.loads((ROOT / "docs/eval/typed-questions-baseline.meta.json").read_text())
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()[:12] == baseline["questions"]
    assert hashlib.sha256(DATASET.read_bytes()).hexdigest() == GOLD["expanded_dataset_sha256"]
    assert set(GOLD["cases"]) == {q["id"] for q in NEW}
    for q in NEW:
        assert q["expected_decisions"] in (["answer"], ["decline"])
        assert q["constraints"] and q["scoring_criteria"]
        assert q["reference"].endswith(f"#cases.{q['id']}")


@pytest.mark.parametrize("q", NEW, ids=lambda q: q["id"])
def test_new_reference_facts_match_the_seeded_match(q, world):
    feed, ctx, norm = world
    eid, v = q["event"].split("/")
    assert any(msg.event_id == eid and msg.version == int(v) for msg in feed)
    moment, _ = moment_as_of(eid, int(v), feed, ctx, norm)
    ref = GOLD["cases"][q["id"]]
    assert (ref["event_id"], ref["version"]) == (eid, int(v))
    for lookup in ref["references"]:
        assert HELPERS["gold_facts"](lookup["lookup"], moment, ctx, norm) == lookup["facts"]
    assert HELPERS["gold_facts"](q["gold"], moment, ctx, norm)


def test_var_constraints_follow_received_versions_not_final_match_state(world):
    feed, ctx, norm = world
    positions = []
    for q in NEW[:3]:
        eid, v = q["event"].split("/")
        positions.append(next(i for i, msg in enumerate(feed)
                              if msg.event_id == eid and msg.version == int(v)))
        moment, _ = moment_as_of(eid, int(v), feed, ctx, norm)
        shots = [s for s in moment.shots if s.player_id == "ply_0107"]
        expected = q["constraints"]
        assert len(shots) == expected["shots"]
        assert sum(s.outcome in {"saved", "goal"} for s in shots) == expected["on_target"]
        assert sum(s.outcome == "goal" for s in shots) == expected["goals"]
    assert positions == sorted(positions)


def test_club_disambiguation_and_nonshooter_cases_really_apply(world):
    feed, ctx, norm = world
    eid, v = NEW[-1]["event"].split("/")
    moment, _ = moment_as_of(eid, int(v), feed, ctx, norm)
    assert not any(s.player_id == "ply_0201" for s in moment.shots)
    assert ctx.players["ply_0115"].club_id == ctx.home
    assert ctx.players["ply_0115"].display_name == "Pablo Garrow"
    # Check that the club qualifier actually resolves the existing shared surname.
    from formline.analyst.router import player_clarification
    assert player_clarification("How did Garrow play last game?", "en", moment)
    assert not player_clarification(NEW[-2]["text"], "en", moment)
