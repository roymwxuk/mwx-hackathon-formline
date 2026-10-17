"""Write a generated season to disk and read feeds back."""

import json
from pathlib import Path

from formline.generator.season import Season
from formline.schema.feed import FeedMessage

SAMPLE_HEAD = 150  # first N messages of the live feed in the committed sample


def _dump(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_feed(path: Path, feed: list[FeedMessage]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for msg in feed:
            f.write(msg.model_dump_json(exclude_none=False) + "\n")


def write_season(season: Season, out: Path) -> None:
    """Layout:
    league.json, matches.json, feeds/<match_id>.jsonl   what a provider would deliver
    gen_only/latent_profiles.json                        hidden truth, never read by the engine
    sample/                                              small committed excerpt
    """
    league = {
        "clubs": [c.model_dump() for c in season.league.clubs],
        "players": [p.model_dump() for p in season.league.players],
    }
    matches = [m.match.model_dump(mode="json") for m in season.matches]
    _dump(out / "league.json", league)
    _dump(out / "matches.json", matches)
    for gm in season.matches:
        _write_feed(out / "feeds" / f"{gm.match.match_id}.jsonl", gm.feed)
    _dump(out / "gen_only" / "latent_profiles.json", season.league.profiles_json())

    live = next(gm for gm in season.matches if gm.match.is_live_demo)
    var_ids = {m.event.event_id for m in live.feed
               if m.event and m.event.type.startswith("var_review")}
    var_targets = {rid for m in live.feed if m.event and m.event.event_id in var_ids
                   for rid in m.event.related_event_ids}
    excerpt = live.feed[:SAMPLE_HEAD] + [
        m for m in live.feed[SAMPLE_HEAD:] if m.event_id in var_ids | var_targets
    ]
    _dump(out / "sample" / "league.json", league)
    _dump(out / "sample" / "matches.json", matches)
    _write_feed(out / "sample" / f"{live.match.match_id}.excerpt.jsonl", excerpt)


def read_feed(path: Path) -> list[FeedMessage]:
    with path.open(encoding="utf-8") as f:
        return [FeedMessage.model_validate_json(line) for line in f if line.strip()]
