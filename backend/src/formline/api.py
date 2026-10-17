"""FastAPI entrypoint: replays a generated match feed to the viewer over SSE."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from formline.agents.precompute import (
    default_runner,
    make_orchestrator,
    overlays_path,
    read_overlays,
)
from formline.chaos import ChaosConfig, inject
from formline.config import settings
from formline.engine.bootstrap import bootstrap_history
from formline.engine.engine import BaselineEngine
from formline.generator.output import read_feed
from formline.replay import END_MESSAGE, merge_stream, replay, replay_items, to_stream_message
from formline.schema.overlay import overlay_message
from formline.viewer import UnknownMatch, match_league

app = FastAPI(title="Formline")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/matches")
def matches() -> list[dict]:
    path = settings.data_dir / "matches.json"
    if not path.exists():
        raise HTTPException(503, "No generated data. Run `uv run formline-gen generate`.")
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def history_engine(data_dir: Path) -> BaselineEngine:
    """Season-so-far baselines, built once per process from the generated history."""
    return bootstrap_history(data_dir)


@app.get("/matches/{match_id}/league")
def league(match_id: str) -> dict:
    """Clubs (home first) and both squads, in the viewer's Club/Player shapes."""
    if not (settings.data_dir / "matches.json").exists():
        raise HTTPException(503, "No generated data. Run `uv run formline-gen generate`.")
    try:
        return match_league(settings.data_dir, match_id, history_engine(settings.data_dir))
    except UnknownMatch:
        raise HTTPException(404, f"Unknown match {match_id}") from None


@app.get("/matches/{match_id}/stream")
async def stream(match_id: str, speed: float | None = Query(None, gt=0),
                 live: bool = False, chaos: bool = False,
                 chaos_seed: int = 0) -> EventSourceResponse:
    """Each SSE `data:` line is one StreamMessage as JSON (the viewer's live mode).

    Default: replays the feed together with the precomputed overlays
    (`formline-gen overlays`). `live=true` runs the engine and the agent workflow during
    the replay instead. `chaos=true` replays the feed through the chaos injector
    (duplicates, reordering, late messages, injected corrections) and implies live, so
    the cards follow the chaotic feed's own corrections. The stream ends with
    `{"kind": "end"}`.
    """
    path = settings.data_dir / "feeds" / f"{match_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, f"Unknown match {match_id}")
    feed = read_feed(path)
    pace = speed or settings.sim_speed

    def sse(payload: dict) -> dict:
        return {"data": json.dumps(payload, ensure_ascii=False)}

    async def gen():
        if live or chaos:
            orch = make_orchestrator(settings.data_dir, history_engine(settings.data_dir),
                                     default_runner(settings.data_dir))
            messages = inject(feed, ChaosConfig(seed=chaos_seed)).messages if chaos else feed
            async for msg in replay(messages, pace):
                if (payload := to_stream_message(msg)) is not None:
                    yield sse(payload)
                for overlay in await orch.process(msg):
                    yield sse(overlay_message(overlay))
            for overlay in await orch.flush():
                yield sse(overlay_message(overlay))
        else:
            cached = overlays_path(settings.data_dir, match_id)
            overlays = read_overlays(cached) if cached.exists() else []
            async for payload in replay_items(merge_stream(feed, overlays), pace):
                yield sse(payload)
        yield sse(END_MESSAGE)

    return EventSourceResponse(gen())
