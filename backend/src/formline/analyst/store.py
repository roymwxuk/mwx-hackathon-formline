"""Comments on disk: computed once per match (like the overlays) and replayed with the feed."""

import json
from datetime import datetime
from pathlib import Path

from formline.agents.llm import LLMRunner
from formline.agents.precompute import load_league
from formline.agents.verifier import league_names
from formline.analyst.writer import AnalystWriter


def comments_path(data_dir: Path, match_id: str) -> Path:
    return data_dir / "analyst" / f"{match_id}.jsonl"


def comment_message(comment: dict) -> dict:
    """The viewer's StreamMessage for a comment (SSE `data:` payload)."""
    return {"kind": "comment", "comment": comment}


def make_writer(data_dir: Path, match_id: str, runner: LLMRunner) -> AnalystWriter:
    players, clubs = load_league(data_dir)
    matches = json.loads((data_dir / "matches.json").read_text(encoding="utf-8"))
    match = next(m for m in matches if m["match_id"] == match_id)
    return AnalystWriter(runner, league_names(players, clubs), {p.player_id: p for p in players},
                         {c.club_id: c.name for c in clubs}, match["home_club_id"],
                         match["away_club_id"])


def write_comments_file(path: Path, rows: list[tuple[datetime, dict]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for at, comment in rows:
            f.write(json.dumps({"emitted_at": at.isoformat(), "comment": comment},
                               ensure_ascii=False) + "\n")


def read_comments(path: Path) -> list[tuple[datetime, dict]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows.append((datetime.fromisoformat(r["emitted_at"]), r["comment"]))
    return rows
