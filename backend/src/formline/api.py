"""FastAPI entrypoint: replays a generated match feed to the viewer over SSE."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from formline.config import settings
from formline.engine.bootstrap import bootstrap_history
from formline.engine.engine import BaselineEngine
from formline.generator.output import read_feed
from formline.replay import replay, to_stream_message
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
async def stream(match_id: str, speed: float | None = Query(None, gt=0)) -> EventSourceResponse:
    """Each SSE `data:` line is one StreamMessage as JSON (the viewer's live mode)."""
    path = settings.data_dir / "feeds" / f"{match_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, f"Unknown match {match_id}")
    feed = read_feed(path)

    async def gen():
        async for msg in replay(feed, speed or settings.sim_speed):
            payload = to_stream_message(msg)
            if payload:
                yield {"data": json.dumps(payload, ensure_ascii=False)}

    return EventSourceResponse(gen())
