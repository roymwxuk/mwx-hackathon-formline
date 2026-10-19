"""Typed answers: numbers must belong to the player named in the same clause.

Codex's review reproduced the gap: with facts "Reyner 2 goals, Ito 1 goal", an answer
swapping the counts passed, because the verifier only checked that each number appeared
somewhere in the facts.
"""

import pytest

from formline.agents.verifier import league_names
from formline.analyst.facts import FactsPack
from formline.analyst.verify import AnswerContext, bound_numbers, verify_answer
from formline.generator.season import generate_season

REYNER, ITO = "ply_0107", "ply_0111"


@pytest.fixture(scope="module")
def setting():
    season = generate_season(2026)
    gm = next(g for g in season.matches if g.match.is_live_demo)
    league = league_names(season.league.players, season.league.clubs)
    return league, (gm.match.home_club_id, gm.match.away_club_id)


def pack(facts: dict, roles: dict) -> FactsPack:
    return FactsPack("free", None, facts, roles, [])


def check(setting, facts, roles, body, lang="en"):
    league, clubs = setting
    answer = {"headline": "Harbourside so far", "body": body, "coverage": "full"}
    return verify_answer(answer, AnswerContext(pack(facts, roles), lang, clubs, free=True), league)


def test_the_reproduced_swap_is_rejected_and_the_truth_accepted(setting):
    league, _ = setting
    assert league.players[ITO][0].endswith("Ito")
    facts = {"season_leaders": {"home_goals": "most goals: PLAYER_A 2, PLAYER_B 1"}}
    roles = {"PLAYER_A": REYNER, "PLAYER_B": ITO}
    assert check(setting, facts, roles, "Reyner has 2 goals; Ito has 1 goal.").ok
    swapped = check(setting, facts, roles, "Reyner has 1 goal; Ito has 2 goals.")
    assert not swapped.ok and "binding" in {f.check for f in swapped.failures}


def test_a_players_own_section_binds_all_its_numbers_to_him(setting):
    facts = {"player_recent": {"player": "PLAYER_A", "totals": "over these 3 game(s): 1 goal(s), 11 shot(s)"},
             "season_leaders": {"away_goals": "most goals: PLAYER_B 10"}}
    roles = {"PLAYER_A": REYNER, "PLAYER_B": ITO}
    assert check(setting, facts, roles, "Over his last 3 games Reyner scored 1 goal from 11 shots.").ok
    wrong = check(setting, facts, roles, "Over his last 3 games Reyner scored 10 goals.")
    assert "binding" in {f.check for f in wrong.failures}  # Ito's 10, given to Reyner


def test_scores_and_clauses_without_a_player_are_not_bound(setting):
    facts = {"score": {"score_now": "Harbourside Athletic 1–0 Northgate Rovers",
                       "goals": "SCORER_A (Harbourside Athletic) in minute 23"},
             "team_stats": {"shots": "shots: Harbourside Athletic 7, Northgate Rovers 3"}}
    roles = {"SCORER_A": ITO}
    ok = "Ito scored in minute 23 to make it 1–0. Harbourside have 7 shots to 3."
    assert check(setting, facts, roles, ok).ok
    assert "binding" in {f.check for f in check(setting, facts, roles, "Ito has 7 shots.").failures}


def test_japanese_clauses_are_bound_too(setting):
    league, _ = setting
    ito_ja = league.players[ITO][1].split("・")[-1]
    reyner_ja = league.players[REYNER][1].split("・")[-1]
    facts = {"season_leaders": {"home_goals": "most goals: PLAYER_A 2, PLAYER_B 1"}}
    roles = {"PLAYER_A": REYNER, "PLAYER_B": ITO}
    assert check(setting, facts, roles, f"{reyner_ja}は2得点、{ito_ja}は1得点。", "ja").ok
    swapped = check(setting, facts, roles, f"{reyner_ja}は1得点、{ito_ja}は2得点。", "ja")
    assert "binding" in {f.check for f in swapped.failures}


def test_bound_numbers_reads_clauses_and_owned_sections():
    p = pack({"a": {"x": "most goals: PLAYER_A 5, PLAYER_B 3; corners: 4"},
              "b": {"player": "PLAYER_C", "season": "10 appearance(s), 2.0 xG"}},
             {"PLAYER_A": "p1", "PLAYER_B": "p2", "PLAYER_C": "p3"})
    b = bound_numbers(p)
    assert b["PLAYER_A"] == {"5"} and b["PLAYER_B"] == {"3"}
    assert {"10", "2.0", "2"} <= b["PLAYER_C"]
