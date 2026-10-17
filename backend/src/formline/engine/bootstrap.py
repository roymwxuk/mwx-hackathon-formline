"""Build a baseline engine from the generated history (the "season so far")."""

import json
from pathlib import Path

from formline.engine.engine import BaselineEngine
from formline.engine.ingest import Applied
from formline.engine.log import current_events
from formline.generator.output import read_feed
from formline.schema.reference import Player


def load_players(data_dir: Path) -> list[Player]:
    league = json.loads((data_dir / "league.json").read_text(encoding="utf-8"))
    return [Player.model_validate(p) for p in league["players"]]


def bootstrap_history(data_dir: Path) -> BaselineEngine:
    """Apply every historical match (final event versions), then fit and freeze priors."""
    engine = BaselineEngine(load_players(data_dir))
    matches = json.loads((data_dir / "matches.json").read_text(encoding="utf-8"))
    for m in matches:
        if m["is_live_demo"]:
            continue
        feed = read_feed(data_dir / "feeds" / f"{m['match_id']}.jsonl")
        engine.apply_all(Applied(e) for e in current_events(feed))
    engine.fit_priors()
    return engine
