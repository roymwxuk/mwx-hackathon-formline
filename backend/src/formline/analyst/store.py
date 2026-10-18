"""Comments on disk: computed once per match (like the overlays) and replayed with the feed.

Follow-up answers precomputed with them live next to the comments
(`<match>.answers.jsonl`); `/ask` serves those first and answers anything else live.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from formline.agents.llm import LLMRunner
from formline.agents.precompute import load_league
from formline.agents.verifier import LeagueNames, league_names
from formline.analyst.writer import AnalystWriter


def comments_path(data_dir: Path, match_id: str) -> Path:
    return data_dir / "analyst" / f"{match_id}.jsonl"


def comment_message(comment: dict) -> dict:
    """The viewer's StreamMessage for a comment (SSE `data:` payload)."""
    return {"kind": "comment", "comment": comment}


def answers_path(data_dir: Path, match_id: str) -> Path:
    return data_dir / "analyst" / f"{match_id}.answers.jsonl"


@dataclass(frozen=True)
class MatchContext:
    """What the Analyst needs to know about a match: names, squads, the two clubs."""

    league: LeagueNames
    players: dict  # player id -> Player
    clubs: dict[str, str]  # club id -> name
    home: str
    away: str


def match_context(data_dir: Path, match_id: str) -> MatchContext:
    players, clubs = load_league(data_dir)
    matches = json.loads((data_dir / "matches.json").read_text(encoding="utf-8"))
    match = next(m for m in matches if m["match_id"] == match_id)
    return MatchContext(league_names(players, clubs), {p.player_id: p for p in players},
                        {c.club_id: c.name for c in clubs}, match["home_club_id"],
                        match["away_club_id"])


def make_writer(data_dir: Path, match_id: str, runner: LLMRunner,
                norm: Callable[[str], float | None] | None = None,
                answer_followups: bool = False) -> AnalystWriter:
    ctx = match_context(data_dir, match_id)
    return AnalystWriter(runner, ctx.league, ctx.players, ctx.clubs, ctx.home, ctx.away,
                         norm=norm, answer_followups=answer_followups)


def write_answers_file(path: Path, answers: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in answers:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_answers(path: Path) -> dict[str, dict]:
    """answer key -> answer; empty when nothing was precomputed."""
    if not path.exists():
        return {}
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return {r["key"]: r["answer"] for r in rows}


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
