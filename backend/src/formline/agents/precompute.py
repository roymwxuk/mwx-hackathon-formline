"""Overlays for a match, computed once and replayed (decision D3).

`uv run formline-gen overlays` runs the full live path (engine + agent workflow) over a
match feed and writes the resulting overlays with their emission times to
`data/overlays/<match_id>.jsonl`. The stream then replays events and overlays together,
so the demo is reproducible and costs nothing per view. Model answers are cached in
`data/llm_cache.jsonl`, so a rerun with the same prompts makes no model calls.
"""

import copy
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from formline.agents.fakes import FakeAgents
from formline.agents.live import LiveOrchestrator, LiveSummary
from formline.agents.llm import LLMConfig, LLMRunner, make_runner
from formline.agents.template_narrator import names_for
from formline.agents.verifier import league_names
from formline.agents.workflow import Deps
from formline.engine.engine import BaselineEngine
from formline.generator.output import read_feed
from formline.schema.overlay import Overlay, overlay_json
from formline.schema.reference import Club, Player


def load_league(data_dir: Path) -> tuple[list[Player], list[Club]]:
    league = json.loads((data_dir / "league.json").read_text(encoding="utf-8"))
    return ([Player.model_validate(p) for p in league["players"]],
            [Club.model_validate(c) for c in league["clubs"]])


def make_orchestrator(data_dir: Path, history: BaselineEngine,
                      runner: LLMRunner) -> LiveOrchestrator:
    """A fresh orchestrator on a private copy of the season-so-far engine."""
    players, clubs = load_league(data_dir)
    names = {p.player_id: names_for(p.display_name, p.display_name_ja) for p in players}
    deps = Deps(runner, league_names(players, clubs), names)
    return LiveOrchestrator(copy.deepcopy(history), deps)


def default_runner(data_dir: Path) -> LLMRunner:
    return make_runner(LLMConfig.from_settings(), fake_responder=FakeAgents(),
                       cache_path=data_dir / "llm_cache.jsonl")


def overlays_path(data_dir: Path, match_id: str) -> Path:
    return data_dir / "overlays" / f"{match_id}.jsonl"


async def precompute(data_dir: Path, match_id: str, history: BaselineEngine,
                     runner: LLMRunner) -> tuple[Path, LiveSummary, LLMRunner]:
    feed = read_feed(data_dir / "feeds" / f"{match_id}.jsonl")
    orch = make_orchestrator(data_dir, history, runner)
    rows: list[dict] = []
    for msg in feed:
        for o in await orch.process(msg):
            rows.append({"emitted_at": msg.emitted_at.isoformat(), "overlay": overlay_json(o)})
    last = feed[-1].emitted_at.isoformat() if feed else None
    for o in await orch.flush():
        rows.append({"emitted_at": last, "overlay": overlay_json(o)})
    path = overlays_path(data_dir, match_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path, orch.summary, runner


def read_overlays(path: Path) -> list[tuple[datetime, Overlay]]:
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                out.append((datetime.fromisoformat(row["emitted_at"]),
                            Overlay.model_validate(row["overlay"])))
    return out


def summary_dict(summary: LiveSummary, runner: LLMRunner) -> dict:
    return asdict(summary) | {"model": runner.kind, "model_calls": runner.budget.calls,
                              "cache_hits": runner.cache_hits}
