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
REFERENCE_60 = ROOT / "docs/eval/typed-questions-expansion-60-reference.json"
REFERENCE_75 = ROOT / "docs/eval/typed-questions-expansion-75-reference.json"
ORIGINAL_50 = ROOT / "docs/eval/typed-questions-original-50.json"
ORIGINAL_60 = ROOT / "docs/eval/typed-questions-original-60.json"
QUESTIONS = json.loads(DATASET.read_text())
NEW = QUESTIONS[38:]
GOLD = json.loads(REFERENCE.read_text())
GOLD_60 = json.loads(REFERENCE_60.read_text())
GOLD_75 = json.loads(REFERENCE_75.read_text())
REFERENCES = {case_id: ref for batch in (GOLD, GOLD_60, GOLD_75)
              for case_id, ref in batch["cases"].items()}
BY_ID = {q["id"]: q for q in QUESTIONS}
HELPERS = runpy.run_path(str(ROOT / "backend/scripts/eval_typed_questions.py"))


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    data = tmp_path_factory.mktemp("expanded-eval")
    write_season(generate_season(2026), data)
    feed = read_feed(data / "feeds" / f"{HELPERS['LIVE']}.jsonl")
    return feed, match_context(data, HELPERS["LIVE"]), bootstrap_history(data).season_norm


def test_seventy_five_unique_cases_preserve_previous_datasets():
    assert len(QUESTIONS) == len({q["id"] for q in QUESTIONS}) == 75
    assert QUESTIONS[:38] == json.loads(ORIGINAL.read_text())
    assert QUESTIONS[:50] == json.loads(ORIGINAL_50.read_text())
    assert QUESTIONS[:60] == json.loads(ORIGINAL_60.read_text())
    baseline = json.loads((ROOT / "docs/eval/typed-questions-baseline.meta.json").read_text())
    assert hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()[:12] == baseline["questions"]
    assert hashlib.sha256(ORIGINAL_50.read_bytes()).hexdigest() == GOLD["expanded_dataset_sha256"]
    assert hashlib.sha256(ORIGINAL_60.read_bytes()).hexdigest() == GOLD_60["expanded_dataset_sha256"]
    assert hashlib.sha256(DATASET.read_bytes()).hexdigest() == GOLD_75["expanded_dataset_sha256"]
    assert hashlib.sha256(ORIGINAL_60.read_bytes()).hexdigest() == GOLD_75["parent_dataset_sha256"]
    assert set(GOLD["cases"]) == {q["id"] for q in QUESTIONS[38:50]}
    assert set(GOLD_60["cases"]) == {q["id"] for q in QUESTIONS[50:60]}
    assert set(GOLD_75["cases"]) == {q["id"] for q in QUESTIONS[60:]}
    for q in NEW:
        assert q["expected_decisions"] and set(q["expected_decisions"]) <= {
            "answer", "decline", "clarify", "correct_false_premise"}
        assert q["constraints"] and q["scoring_criteria"]
        assert q["reference"].endswith(f"#cases.{q['id']}")


@pytest.mark.parametrize("q", NEW, ids=lambda q: q["id"])
def test_new_reference_facts_match_the_seeded_match(q, world):
    feed, ctx, norm = world
    eid, v = q["event"].split("/")
    assert any(msg.event_id == eid and msg.version == int(v) for msg in feed)
    moment, _ = moment_as_of(eid, int(v), feed, ctx, norm)
    ref = REFERENCES[q["id"]]
    assert (ref["event_id"], ref["version"]) == (eid, int(v))
    for lookup in ref["references"]:
        assert HELPERS["gold_facts"](lookup["lookup"], moment, ctx, norm) == lookup["facts"]
    if q["gold"] is not None:
        assert HELPERS["gold_facts"](q["gold"], moment, ctx, norm)
    else:
        assert "registry_check" in ref or "policy_reference" in ref


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
    eid, v = BY_ID["s02"]["event"].split("/")
    moment, _ = moment_as_of(eid, int(v), feed, ctx, norm)
    assert not any(s.player_id == "ply_0201" for s in moment.shots)
    assert ctx.players["ply_0115"].club_id == ctx.home
    assert ctx.players["ply_0115"].display_name == "Pablo Garrow"
    # Check that the club qualifier actually resolves the existing shared surname.
    from formline.analyst.router import player_clarification
    assert player_clarification("How did Garrow play last game?", "en", moment)
    assert not player_clarification(BY_ID["s01"]["text"], "en", moment)


def test_tie_and_scope_constraints_are_supported_by_all_club_players(world):
    _, ctx, _ = world
    assists = {pid: ctx.player_seasons.get(pid, {}).get("assists", 0)
               for pid, p in ctx.players.items() if p.club_id == ctx.home}
    best = max(assists.values())
    expected = BY_ID["tie01"]["constraints"]
    assert best == expected["assists_each"]
    assert {pid for pid, n in assists.items() if n == best} == set(expected["leaders"])
    # A single counterexample disproves league leadership; it does not identify the winner.
    scope = BY_ID["scope01"]["constraints"]
    assert ctx.player_seasons[scope["club_top_scorer"]]["goals"] == scope["club_goals"]
    assert ctx.player_seasons[scope["counterexample_player"]]["goals"] == scope["counterexample_goals"]
    assert scope["counterexample_goals"] > scope["club_goals"]


def test_zero_shots_and_missing_history_are_different(world):
    feed, ctx, norm = world
    q = BY_ID["ze01"]
    eid, version = q["event"].split("/")
    moment, _ = moment_as_of(eid, int(version), feed, ctx, norm)
    pid = q["constraints"]["player_id"]
    assert not any(s.player_id == pid for s in moment.shots)
    missing = BY_ID["ze02"]["constraints"]["player_id"]
    assert not any(missing in game["players"] for game in ctx.history)
    # There are no recorded appearances to attach even zero-valued match totals to.
    facts = GOLD_60["cases"]["ze02"]["references"][0]["facts"]["player_recent"]
    assert "totals" not in facts


def test_future_event_questions_really_precede_those_events(world):
    feed, ctx, norm = world
    for case_id, target_type, player in [("future01", "shot", "ply_0111"),
                                         ("future02", "card", "ply_0105")]:
        q = BY_ID[case_id]
        eid, version = q["event"].split("/")
        index = next(i for i, msg in enumerate(feed)
                     if msg.event_id == eid and msg.version == int(version))
        def target(event, target_type=target_type, player=player):
            return (event.type == target_type and getattr(event, "player_id", None) == player
                    and (getattr(event, "outcome", None) == "goal" if target_type == "shot"
                         else getattr(event, "card", None) == "second_yellow"))
        moment, _ = moment_as_of(eid, int(version), feed, ctx, norm)
        assert not any(target(e) for e in moment.events)
        assert any(target(msg.event) for msg in feed[index + 1:])


def test_personal_baseline_constraints_use_stronger_foot_averages(world):
    from formline.engine.features import shot_features
    feed, ctx, norm = world
    for case_id in ("base01", "base02", "base03"):
        q = BY_ID[case_id]
        eid, v = q["event"].split("/")
        m, _ = moment_as_of(eid, int(v), feed, ctx, norm)
        expected = q["constraints"]
        pid = expected["player_id"]
        features = [shot_features(s, ctx.players[pid]) for s in m.shots if s.player_id == pid]
        speeds = [f.shot_speed_kmh for f in features if f.body_group == "strong_foot"]
        assert round(sum(speeds) / len(speeds)) == expected["average_kmh"]
        assert round(norm(pid)) == expected["season_norm_kmh"]
        assert expected["average_kmh"] > expected["season_norm_kmh"]


def test_unknown_entities_are_absent_and_identity_conflicts_are_real(world):
    _, ctx, _ = world
    for case_id in ("unknown01", "unknown02", "unknown03"):
        q = BY_ID[case_id]
        check = REFERENCES[case_id]["registry_check"]
        names = ([name for p in ctx.players.values() for name in
                  (p.display_name, p.display_name_ja)] if check["entity_type"] == "player"
                 else list(ctx.clubs.values()))
        assert not any(check["query"].casefold() in name.casefold() for name in names)
        assert q["gold"] is None and check["matches"] == []
    for case_id in ("identity01", "identity02", "identity03"):
        c = BY_ID[case_id]["constraints"]
        assert ctx.players[c["player_id"]].club_id == c["actual_club_id"]
        assert c["incorrect_club_id"] != c["actual_club_id"]


def test_request_limit_cases_are_invalid_for_existing_tool_policy(world):
    from formline.analyst.sections import MAX_RECENT
    from formline.analyst.tools import ResearchSession
    feed, ctx, norm = world
    for case_id in ("limit01", "limit02", "limit03"):
        q = BY_ID[case_id]
        eid, v = q["event"].split("/")
        m, _ = moment_as_of(eid, int(v), feed, ctx, norm)
        session = ResearchSession(m, ctx, norm)
        c = q["constraints"]
        assert c["maximum_n"] == MAX_RECENT
        assert session._check("get_player_recent", {"player_id": "ply_0210", "n": c["requested_n"]})
        assert not session._check("get_player_recent", {"player_id": "ply_0210", "n": MAX_RECENT})
