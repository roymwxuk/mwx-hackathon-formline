import pytest
from fastapi.testclient import TestClient

from formline import api
from formline.config import settings
from formline.generator.output import write_season
from formline.generator.season import generate_season

LIVE = "mtc_s26_md11_har_nor"


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


def test_league_returns_both_squads_home_first(client):
    body = client.get(f"/matches/{LIVE}/league").json()
    assert [c["short_name"] for c in body["clubs"]] == ["HAR", "NOR"]
    assert len(body["players"]) == 36
    assert {"color", "text_color"} <= body["clubs"][0].keys()
    reyner = next(p for p in body["players"] if p["player_id"] == "ply_0107")
    assert reyner["display_name"] == "Tomas Reyner" and reyner["display_name_ja"]


def test_season_norms_come_from_the_engine(client):
    players = client.get(f"/matches/{LIVE}/league").json()["players"]
    keepers = [p for p in players if p["position"] == "GK"]
    outfield = [p for p in players if p["position"] != "GK"]
    assert all(p["season_shot_speed_norm_kmh"] is None for p in keepers)
    assert all(55 < p["season_shot_speed_norm_kmh"] < 110 for p in outfield)
    reyner = next(p for p in players if p["player_id"] == "ply_0107")
    # A power shooter: his shrunk norm sits above the forward average.
    assert reyner["season_shot_speed_norm_kmh"] > 84


def test_unknown_match_is_404(client):
    assert client.get("/matches/nope/league").status_code == 404
