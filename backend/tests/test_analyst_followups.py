"""Match Analyst phase 2: suggested follow-up questions and their answers (/ask)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from formline import api
from formline.agents.fakes import FakeAgents
from formline.agents.llm import LLMConfig, make_runner
from formline.agents.verifier import league_names
from formline.analyst.ask import AskError, AskRequest, answer_question, known_events
from formline.analyst.followups import (
    FOLLOWUPS,
    Moment,
    answer_key,
    applicable,
    followup_pack,
    label,
    moment_kind,
)
from formline.analyst.store import MatchContext
from formline.analyst.suggester import check_picks, suggest
from formline.analyst.verify import AnswerContext, verify_answer
from formline.analyst.writer import AnalystWriter, write_comments
from formline.config import settings
from formline.generator.output import write_season
from formline.generator.season import generate_season

LIVE = "mtc_s26_md11_har_nor"
NORM = 85.0


def norm(_pid: str) -> float:
    return NORM


@pytest.fixture(scope="module")
def match():
    season = generate_season(2026)
    gm = next(g for g in season.matches if g.match.is_live_demo)
    players = {p.player_id: p for p in season.league.players}
    clubs = {c.club_id: c.name for c in season.league.clubs}
    league = league_names(season.league.players, season.league.clubs)
    ctx = MatchContext(league, players, clubs, gm.match.home_club_id, gm.match.away_club_id)
    return gm, ctx


@pytest.fixture(scope="module")
def written(match):
    gm, ctx = match
    runner = make_runner(LLMConfig(), fake_responder=FakeAgents())
    w = AnalystWriter(runner, ctx.league, ctx.players, ctx.clubs, ctx.home, ctx.away,
                      norm=norm, answer_followups=True)
    rows = asyncio.run(write_comments(gm.feed, w))
    return w, [c for _, c in rows if c["op"] == "show"]


def moment_at(gm, ctx, comment) -> Moment:
    kind, event_id = moment_kind(comment["ask"]["moment"])
    known = known_events(gm.feed, comment["ask"]["seq"])
    events = sorted(known.values(), key=lambda e: (e.period, e.match_clock_ms))
    return Moment(kind, known[event_id], events, known[event_id].player_id, ctx.home, ctx.away,
                  ctx.clubs, ctx.players, norm)


def ito_goal(comments, lang="en"):
    return next(c for c in comments if c["goal"] and c["lang"] == lang
                and c["match_clock_ms"] // 1000 == 22 * 60 + 30)


# ---------- catalog and suggestions ----------

def test_every_comment_offers_two_or_three_questions_that_apply(match, written):
    gm, ctx = match
    w, comments = written
    for c in comments:
        picks = [s["question"] for s in c["suggestions"]]
        assert 2 <= len(picks) <= 3 and len(set(picks)) == len(picks), c["comment_id"]
        m = moment_at(gm, ctx, c)
        assert all(q in FOLLOWUPS and applicable(q, m) for q in picks)
        assert all(s["label"] for s in c["suggestions"])
    assert w.summary["suggested_rule"] == 0
    # one Suggester call per moment, shared by both languages
    assert w.summary["suggested_llm"] == len(comments) // 2


def test_player_tonight_only_for_a_player_who_has_shot(match, written):
    gm, ctx = match
    _, comments = written
    for c in comments:
        m = moment_at(gm, ctx, c)
        has_shot = any(s.player_id == m.player_id for s in m.shots)
        assert applicable("player_tonight", m) == has_shot


def test_question_wording_is_fixed_by_the_catalog(match, written):
    gm, ctx = match
    _, comments = written
    goal_en, goal_ja = ito_goal(comments), ito_goal(comments, "ja")
    assert [s["label"] for s in goal_en["suggestions"]] == [
        "Why is it 1–0?", "How is Ito doing tonight?", "What's happening?"]
    assert goal_ja["suggestions"][0]["label"] == "なぜ1–0なのか？"
    first = next(c for c in comments if c["lang"] == "en")
    assert label("score", "en", moment_at(gm, ctx, first), None) == "Why is it still 0–0?"


def test_suggester_picks_are_checked_in_code():
    opts = ["score", "player_tonight", "situation", "team_stats"]
    assert check_picks({"pick": ["score", "situation"]}, opts) is None
    assert "unknown" in check_picks({"pick": ["weather", "score"]}, opts)
    assert "at most once" in check_picks({"pick": ["score", "score"]}, opts)
    assert "between" in check_picks({"pick": ["score"]}, opts)
    assert "between" in check_picks({"pick": opts}, opts)
    assert check_picks(["score"], opts) is not None


def test_a_misbehaving_suggester_falls_back_to_the_default_order(match, written):
    gm, ctx = match
    _, comments = written
    m = moment_at(gm, ctx, ito_goal(comments))
    opts = ["score", "player_tonight", "situation", "team_stats"]
    bad = make_runner(LLMConfig(), fake_responder=lambda texts: '{"pick": ["weather"]}')
    s = asyncio.run(suggest(followup_pack("situation", m), opts, bad))
    assert s.source == "rule" and s.picks == opts[:3] and s.attempts == 2


# ---------- facts packs and verification ----------

def test_follow_up_facts_at_itos_goal(match, written):
    gm, ctx = match
    _, comments = written
    m = moment_at(gm, ctx, ito_goal(comments))
    score = followup_pack("score", m)
    assert score.facts["score_now"] == "Harbourside Athletic 1–0 Northgate Rovers"
    assert score.roles["SCORER_A"] == m.player_id and "minute 23" in score.facts["goals"]
    assert "model estimate" in score.facts["chance_quality_total"]
    stats = followup_pack("team_stats", m)
    home_shots = sum(s.team_id == ctx.home for s in m.shots)
    assert stats.facts["shots"].startswith(f"shots: Harbourside Athletic {home_shots},")
    me = followup_pack("player_tonight", m)
    assert me.roles == {"PLAYER": m.player_id}
    assert me.facts["speed_vs_norm"].endswith(f"his season norm {round(NORM)} km/h")
    assert set(me.source_event_ids) == {s.event_id for s in m.shots if s.player_id == m.player_id}


def test_the_verifier_rejects_a_wrong_score_or_another_club(match, written):
    gm, ctx = match
    _, comments = written
    m = moment_at(gm, ctx, ito_goal(comments))
    pack = followup_pack("score", m)
    actx = AnswerContext(pack, "en", (ctx.home, ctx.away))
    good = {"headline": "Harbourside lead 1–0", "body": "Ito scored the only goal so far."}
    assert verify_answer(good, actx, ctx.league).ok
    wrong = {**good, "headline": "Harbourside lead 2–0"}
    assert "numbers" in {f.check for f in verify_answer(wrong, actx, ctx.league).failures}
    other = next(name for cid, (name, _) in ctx.league.clubs.items() if cid not in (ctx.home, ctx.away))
    stray = {**good, "body": f"Ito scored; {other} were watching."}
    assert "entities" in {f.check for f in verify_answer(stray, actx, ctx.league).failures}


def test_every_suggested_question_is_answered_and_verified_in_both_languages(written):
    w, comments = written
    keys = {a["key"] for a in w.answers}
    for c in comments:
        for s in c["suggestions"]:
            assert answer_key(c["ask"]["moment"], s["question"], s["player_id"], c["lang"]) in keys
    assert w.summary["answers_template"] == 0
    assert all(a["answer"]["verified"] and a["answer"]["headline"] for a in w.answers)


# ---------- /ask ----------

def ask(c, s, lang=None):
    return AskRequest(c["ask"]["moment"], c["ask"]["seq"], s["question"], s["player_id"],
                      lang or c["lang"])


def test_ask_serves_the_precomputed_answer(match, written):
    gm, ctx = match
    w, comments = written
    c = ito_goal(comments)
    pre = {a["key"]: a["answer"] for a in w.answers}
    runner = make_runner(LLMConfig(), fake_responder=lambda texts: 1 / 0)  # must not be called
    out = asyncio.run(answer_question(ask(c, c["suggestions"][0]), gm.feed, ctx, runner, pre, norm))
    assert out["cached"] is True and out["headline"]


def test_a_live_answer_matches_the_precomputed_one(match, written):
    gm, ctx = match
    w, comments = written
    pre = {a["key"]: a["answer"] for a in w.answers}
    runner = make_runner(LLMConfig(), fake_responder=FakeAgents())
    for c in (ito_goal(comments), ito_goal(comments, "ja")):
        for s in c["suggestions"]:
            live = asyncio.run(answer_question(ask(c, s), gm.feed, ctx, runner, {}, norm))
            cached = pre[answer_key(c["ask"]["moment"], s["question"], s["player_id"], c["lang"])]
            assert live["cached"] is False
            assert {k: live[k] for k in cached} == cached


def test_ask_rejects_requests_that_do_not_name_an_answerable_moment(match, written):
    gm, ctx = match
    _, comments = written
    c = ito_goal(comments)
    runner = make_runner(LLMConfig(), fake_responder=FakeAgents())
    bad = [
        AskRequest("penalty_evt_1", c["ask"]["seq"], "score", None, "en"),  # not a moment id
        AskRequest(c["ask"]["moment"], 1, "score", None, "en"),  # before the event happened
        AskRequest(c["ask"]["moment"], c["ask"]["seq"], "player_tonight", "ply_0107", "en"),  # not Ito
    ]
    no_shot = next(x for x in comments if not any(
        s.player_id == x["player_id"] for s in moment_at(gm, ctx, x).shots))
    bad.append(AskRequest(no_shot["ask"]["moment"], no_shot["ask"]["seq"], "player_tonight",
                          no_shot["player_id"], "en"))
    for req in bad:
        with pytest.raises(AskError):
            asyncio.run(answer_question(req, gm.feed, ctx, runner, {}, norm))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    write_season(generate_season(2026), data)
    original = settings.data_dir
    settings.data_dir = data
    api.history_engine.cache_clear()
    yield TestClient(api.app)
    settings.data_dir = original
    api.history_engine.cache_clear()


def test_the_ask_endpoint_answers_live_and_rejects_bad_requests(client, written):
    _, comments = written
    c = ito_goal(comments)
    body = {**c["ask"], "question": "score", "player_id": None, "lang": "en"}
    r = client.post(f"/matches/{LIVE}/ask", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["cached"] is False and out["verified"] and out["evidence"]
    assert "1–0" in out["headline"] + out["body"]
    assert client.post(f"/matches/{LIVE}/ask", json={**body, "question": "weather"}).status_code == 422
    assert client.post(f"/matches/{LIVE}/ask", json={**body, "seq": 1}).status_code == 422
    assert client.post("/matches/nope/ask", json=body).status_code == 404
