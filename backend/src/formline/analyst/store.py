"""Comments on disk: computed once per match (like the overlays) and replayed with the feed.

Follow-up answers precomputed with them live next to the comments
(`<match>.answers.jsonl`); `/ask` serves those first and answers anything else live.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
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
    # the fixture (season, matchday, kick-off, venue) and each club's record before tonight
    info: dict = field(default_factory=dict)
    records: dict = field(default_factory=dict)
    player_seasons: dict = field(default_factory=dict)  # player id -> season before tonight
    history: list = field(default_factory=list)  # past matches, oldest first (history_rows)


def match_context(data_dir: Path, match_id: str) -> MatchContext:
    players, clubs = load_league(data_dir)
    matches = json.loads((data_dir / "matches.json").read_text(encoding="utf-8"))
    match = next(m for m in matches if m["match_id"] == match_id)
    return MatchContext(league_names(players, clubs), {p.player_id: p for p in players},
                        {c.club_id: c.name for c in clubs}, match["home_club_id"],
                        match["away_club_id"], info=match, records=_records(data_dir),
                        player_seasons=_player_seasons(data_dir), history=_history(data_dir))


def season_records(results: Iterable[tuple[str, str, int, int]]) -> dict[str, dict]:
    """club id -> {played, won, drawn, lost, goals_for, goals_against} from (home, away,
    home goals, away goals) results."""
    rec: dict[str, dict] = {}
    for home, away, hg, ag in results:
        for club, gf, ga in ((home, hg, ag), (away, ag, hg)):
            r = rec.setdefault(club, {"played": 0, "won": 0, "drawn": 0, "lost": 0,
                                      "goals_for": 0, "goals_against": 0})
            r["played"] += 1
            r["won" if gf > ga else "drawn" if gf == ga else "lost"] += 1
            r["goals_for"] += gf
            r["goals_against"] += ga
    return rec


def player_season_stats(matches: Iterable[list]) -> dict[str, dict]:
    """player id -> {appearances, goals, assists, shots, on_target} over matches (each a
    list of its events, latest versions). Appearances count matches with any event of his."""
    stats: dict[str, dict] = {}

    def row(pid: str) -> dict:
        return stats.setdefault(pid, {"appearances": 0, "goals": 0, "assists": 0, "shots": 0,
                                      "on_target": 0})
    for events in matches:
        by_id = {e.event_id: e for e in events}
        seen: set[str] = set()
        for e in events:
            seen |= {p for p in (getattr(e, "player_id", None), getattr(e, "player_on_id", None)) if p}
            if e.type != "shot":
                continue
            r = row(e.player_id)
            r["shots"] += 1
            r["on_target"] += e.outcome in ("goal", "saved")
            if e.outcome == "goal":
                r["goals"] += 1
                kp = by_id.get(e.key_pass_event_id or "")
                if kp is not None and kp.player_id:
                    row(kp.player_id)["assists"] += 1
        for pid in seen:
            row(pid)["appearances"] += 1
    return stats


def history_rows(matches: Iterable[tuple[dict, list]]) -> list[dict]:
    """One row per past match, oldest first: who played whom, the score, the scorers and each
    player's numbers (goals, assists, shots, on target, passes). From (match, events) pairs,
    the same events the season stats count."""
    rows = []
    for match, events in matches:
        by_id = {e.event_id: e for e in events}
        players: dict[str, dict] = {}

        def row(pid: str, players: dict = players) -> dict:
            return players.setdefault(pid, {"goals": 0, "assists": 0, "shots": 0, "on_target": 0,
                                            "passes": 0, "passes_completed": 0})
        scorers = []
        for e in events:
            for pid in (getattr(e, "player_id", None), getattr(e, "player_on_id", None)):
                if pid:
                    row(pid)
            if e.type == "pass" and e.player_id:
                row(e.player_id)["passes"] += 1
                row(e.player_id)["passes_completed"] += e.outcome == "complete"
            if e.type != "shot":
                continue
            r = row(e.player_id)
            r["shots"] += 1
            r["on_target"] += e.outcome in ("goal", "saved")
            if e.outcome == "goal":
                r["goals"] += 1
                scorers.append((e.player_id, e.team_id, e.match_clock_ms // 60_000 + 1))
                kp = by_id.get(e.key_pass_event_id or "")
                if kp is not None and kp.player_id:
                    row(kp.player_id)["assists"] += 1
        home, away = match["home_club_id"], match["away_club_id"]
        rows.append({"match_id": match["match_id"], "kickoff_at": str(match["kickoff_at"]),
                     "home": home, "away": away,
                     "home_goals": sum(t == home for _, t, _ in scorers),
                     "away_goals": sum(t == away for _, t, _ in scorers),
                     "scorers": scorers, "players": players})
    return sorted(rows, key=lambda r: r["kickoff_at"])


@cache
def _history(data_dir: Path) -> list[dict]:
    return history_rows(_history_events(data_dir))


@cache
def _history_events(data_dir: Path) -> list[tuple[dict, list]]:
    from formline.engine.log import current_events
    from formline.generator.output import read_feed

    matches = json.loads((data_dir / "matches.json").read_text(encoding="utf-8"))
    return [(m, current_events(read_feed(data_dir / "feeds" / f"{m['match_id']}.jsonl")))
            for m in matches if not m["is_live_demo"]]


@cache
def _player_seasons(data_dir: Path) -> dict[str, dict]:
    return player_season_stats(events for _, events in _history_events(data_dir))


@cache
def _records(data_dir: Path) -> dict[str, dict]:
    """Season records from the generated history (every match but the live one)."""
    results = []
    for m, events in _history_events(data_dir):
        goals = [e.team_id for e in events if e.type == "shot" and e.outcome == "goal"]
        results.append((m["home_club_id"], m["away_club_id"], goals.count(m["home_club_id"]),
                        goals.count(m["away_club_id"])))
    return season_records(results)


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
