"""View models for the live viewer (frontend/src/lib/types.ts: Club, Player)."""

import json
from pathlib import Path

from formline.engine.engine import BaselineEngine


class UnknownMatch(LookupError):
    pass


def match_league(data_dir: Path, match_id: str, engine: BaselineEngine) -> dict:
    """Both clubs (home first) and their full squads, with each player's season norm."""
    matches = json.loads((data_dir / "matches.json").read_text(encoding="utf-8"))
    match = next((m for m in matches if m["match_id"] == match_id), None)
    if match is None:
        raise UnknownMatch(match_id)
    league = json.loads((data_dir / "league.json").read_text(encoding="utf-8"))
    by_id = {c["club_id"]: c for c in league["clubs"]}
    club_ids = [match["home_club_id"], match["away_club_id"]]

    clubs = [{
        "club_id": cid,
        "name": by_id[cid]["name"],
        "short_name": by_id[cid]["short_name"],
        "color": by_id[cid]["colors"]["primary"],
        "text_color": by_id[cid]["colors"]["secondary"],
    } for cid in club_ids]

    players = []
    for p in league["players"]:
        if p["club_id"] not in club_ids:
            continue
        norm = engine.season_norm(p["player_id"])
        players.append({
            "player_id": p["player_id"],
            "display_name": p["display_name"],
            "display_name_ja": p["display_name_ja"],
            "club_id": p["club_id"],
            "shirt_number": p["shirt_number"],
            "position": p["position"],
            "season_shot_speed_norm_kmh": None if norm is None else round(norm, 1),
        })
    players.sort(key=lambda p: (club_ids.index(p["club_id"]), p["shirt_number"]))
    return {"match": match, "clubs": clubs, "players": players}
