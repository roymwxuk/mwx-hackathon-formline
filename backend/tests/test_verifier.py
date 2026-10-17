import pytest

from formline.agents.catalog import TEMPLATE_FOR_INSIGHT
from formline.agents.template_narrator import names_for, narrate, narrate_correction
from formline.agents.verifier import VerifyContext, league_names, normalize, verify
from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.insights import InsightCorrected, InsightCreated, InsightRetracted
from formline.engine.log import current_events
from formline.engine.pipeline import LivePipeline
from formline.generator.season import generate_season

VARIANTS = [(lang, mode) for lang in ("en", "ja") for mode in ("casual", "analyst")]


@pytest.fixture(scope="module")
def world():
    season = generate_season(2026)
    eng = BaselineEngine(season.league.players)
    eng.apply_all(Applied(e) for gm in season.matches if not gm.match.is_live_demo
                  for e in current_events(gm.feed))
    eng.fit_priors()
    live = next(gm.feed for gm in season.matches if gm.match.is_live_demo)
    changes = LivePipeline(eng).run(live)
    players = {p.player_id: p for p in season.league.players}
    return changes, players, league_names(season.league.players, season.league.clubs)


@pytest.fixture(scope="module")
def slow(world):
    """Reyner's 84.1 km/h shot at 40:12: facts, names and context for EN casual."""
    changes, _, league = world
    ins = next(c.insight for c in changes if isinstance(c, InsightCreated)
               and c.insight.player_id == "ply_0107" and c.insight.facts["value"] == 84.1
               and c.insight.type == "shot_speed_vs_norm")
    return ins, league


def ctx(ins, lang="en", mode="casual"):
    return VerifyContext(TEMPLATE_FOR_INSIGHT[ins.type], lang, mode, ins.facts, ins.player_id)


def good(**changes):
    base = {"tag": "SHOT SPEED · VS HIS OWN NORM", "headline": "Reyner — not his usual strike",
            "sub": "84 km/h, about 8 km/h below his typical shot from outside the box (estimate)."}
    return base | changes


def checks(verdict):
    return {f.check for f in verdict.failures}


# ---------- template output always passes ----------

def test_every_template_narration_passes(world):
    changes, players, league = world
    for c in changes:
        if not isinstance(c, InsightCreated):
            continue
        p = players[c.insight.player_id]
        names = names_for(p.display_name, p.display_name_ja)
        for lang, mode in VARIANTS:
            slots = vars(narrate(c.insight, lang, mode, names))
            verdict = verify(slots, ctx(c.insight, lang, mode), league)
            assert verdict.ok, (lang, mode, slots, verdict.feedback())


def test_correction_banners_pass(world):
    changes, _, league = world
    group = [c for c in changes if isinstance(c, (InsightCorrected, InsightRetracted))]
    for lang, mode in VARIANTS:
        slots = vars(narrate_correction(group, lang, mode))
        banner_ctx = VerifyContext("correction_banner", lang, mode,
                                   extra_numbers=frozenset({"1"}))
        assert verify(slots, banner_ctx, league).ok, slots


# ---------- each check catches its error ----------

def test_baseline_good_text_passes(slow):
    ins, league = slow
    assert verify(good(), ctx(ins), league).ok


@pytest.mark.parametrize("sub", [
    "85 km/h, about 8 km/h below his typical shot (estimate).",  # off by one
    "84 km/h, about 18 km/h below his typical shot (estimate).",  # wrong delta
    "84 km/h, his 3rd slowest this season (estimate).",  # invented number
])
def test_wrong_numbers_are_caught(slow, sub):
    ins, league = slow
    v = verify(good(sub=sub), ctx(ins), league)
    assert "numbers" in checks(v)
    assert "FACTS" in v.feedback()


def test_full_width_digits_are_checked():
    assert normalize("８５ km/h") == "85 km/h"


def test_another_player_is_caught(slow):
    ins, league = slow
    v = verify(good(headline="Ito — not his usual strike"), ctx(ins), league)
    assert "entities" in checks(v)


def test_another_club_is_caught(slow):
    ins, league = slow
    v = verify(good(sub="84 km/h against Northgate Rovers, about 8 km/h below his typical "
                        "shot (estimate)."), ctx(ins), league)
    assert "entities" in checks(v)


def test_shared_surname_is_not_a_false_alarm(world):
    _, players, league = world
    inglebys = [p for p in players.values() if p.display_name.endswith("Ingleby")]
    assert len(inglebys) >= 2
    me = inglebys[0]
    c = VerifyContext("shot_speed_card", "en", "casual", {"metric": "shot_speed_kmh", "value": 80.0, "norm": 75.0},
                      me.player_id)
    assert verify({"tag": "T", "headline": "Ingleby hits it harder", "sub": "80 km/h."},
                  c, league).ok


def test_missing_estimate_marker_is_caught(slow):
    ins, league = slow
    v = verify(good(sub="84 km/h, in the bottom 21% of his shots from outside the box."),
               ctx(ins), league)
    assert "estimates" in checks(v)


def test_certainty_claim_is_caught(slow):
    ins, league = slow
    v = verify(good(sub="84 km/h; he will score next time (estimate)."), ctx(ins), league)
    assert "certainty" in checks(v)


def test_wrong_language_is_caught(slow):
    ins, league = slow
    v = verify(good(), ctx(ins, lang="ja"), league)
    assert "language" in checks(v)
    v = verify(good(headline="レイナー — not his usual strike"), ctx(ins), league)
    assert "language" in checks(v)


def test_japanese_checks(slow):
    ins, league = slow
    ok = {"tag": "シュートスピード・本人比", "headline": "レイナー、いつもの威力がない",
          "sub": "84 km/h。エリア外からのシュートの平均より約8 km/h遅い（推定）"}
    assert verify(ok, ctx(ins, "ja"), league).ok
    assert "numbers" in checks(verify(ok | {"sub": "８６ km/h。平均より約8 km/h遅い（推定）"},
                                      ctx(ins, "ja"), league))
    assert "entities" in checks(verify(ok | {"headline": "ブラント、いつもの威力がない"},
                                       ctx(ins, "ja"), league))
    assert "estimates" in checks(verify(ok | {"sub": "下位21%のコース"}, ctx(ins, "ja"), league))
    assert "certainty" in checks(verify(ok | {"sub": "84 km/h。次は必ず決める（推定）"},
                                        ctx(ins, "ja"), league))


@pytest.mark.parametrize("slots,expected", [
    ({"tag": "T", "headline": "", "sub": "84 km/h (estimate)."}, "missing or empty"),
    ({"tag": "T", "headline": "Reyner " + "x" * 80, "sub": "84 km/h."}, "the limit is 60"),
    ({"tag": "T", "headline": "Reyner", "sub": "84 km/h.", "bars": []}, "unexpected slot"),
])
def test_structure_is_enforced(slow, slots, expected):
    ins, league = slow
    v = verify(slots, ctx(ins), league)
    assert "structure" in checks(v) and expected in v.feedback()


def test_feedback_lists_every_failure(slow):
    ins, league = slow
    v = verify(good(headline="Ito will score", sub="99% chance."), ctx(ins), league)
    assert {"numbers", "entities", "estimates", "certainty"} <= checks(v)
    assert v.feedback().count("\n") == len(v.failures) - 1


def test_numbers_are_checked_by_unit(slow):
    """18 is a real fact (the 17.7 m shot distance), but not a speed: '18 km/h' must fail."""
    ins, league = slow
    assert round(ins.facts["distance_m"]) == 18
    v = verify(good(sub="84 km/h, about 18 km/h below his typical shot (estimate)."),
               ctx(ins), league)
    assert "km/h does not match FACTS" in v.feedback()
    assert not verify(good(sub="84 km/h vs his norm of 92 km/h (estimate)."), ctx(ins),
                      league).failures


def test_percentiles_and_samples_are_bound_to_their_role(slow):
    ins, league = slow  # est. 21st percentile, n=5, season sample 20
    analyst = {"tag": "T", "headline": "Reyner 84.1 km/h · Δ −8.2 vs baseline",
               "sub": "Est. 21st percentile (n=5). Model estimates."}
    assert verify(analyst, ctx(ins, mode="analyst"), league).ok
    assert "numbers" in checks(verify(analyst | {"sub": "Est. 20th percentile (n=5). Model "
                                                        "estimates."}, ctx(ins, mode="analyst"),
                                      league))
    assert "numbers" in checks(verify(analyst | {"sub": "Est. 21st percentile (n=20). Model "
                                                        "estimates."}, ctx(ins, mode="analyst"),
                                      league))
    assert "numbers" in checks(verify(analyst | {"sub": "Est. 100th percentile (n=5). Model "
                                                        "estimates."}, ctx(ins, mode="analyst"),
                                      league))



def test_internal_labels_are_rejected(slow):
    ins, league = slow
    v = verify(good(sub="84 km/h from outside_central, body group strong foot (estimate)."),
               ctx(ins), league)
    assert "jargon" in checks(v)
    ja = {"tag": "本人比", "headline": "レイナー、強足のシュート",
          "sub": "84 km/h。平均より約8 km/h遅い（推定）"}
    assert "jargon" in checks(verify(ja, ctx(ins, "ja"), league))


def test_raw_placement_fraction_is_rejected(world):
    changes, _, league = world
    placement = next(c.insight for c in changes if isinstance(c, InsightCreated)
                     and c.insight.type == "placement_vs_norm")
    f = placement.facts
    bad = {"tag": "T", "headline": f"{league.players[placement.player_id][0].split()[-1]} "
                                   "placement", "sub": f"Placement {f['value']} (estimate)."}
    v = verify(bad, ctx(placement), league)
    assert "jargon" in checks(v) and "out of 100" in v.feedback()


def test_headline_must_name_the_player(slow):
    ins, league = slow
    v = verify(good(headline="Not his usual strike"), ctx(ins), league)
    assert "the headline must name the player (Reyner)" in v.feedback()
