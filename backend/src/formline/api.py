"""FastAPI entrypoint: replays a generated match feed to the viewer over SSE."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from formline.agents.precompute import (
    default_runner,
    make_orchestrator,
    overlays_path,
    read_overlays,
)
from formline.analyst.store import comment_message, comments_path, make_writer, read_comments
from formline.chaos import ChaosConfig, inject
from formline.config import settings
from formline.engine.bootstrap import bootstrap_history
from formline.engine.engine import BaselineEngine
from formline.generator.output import read_feed
from formline.replay import (
    END_MESSAGE,
    match_time,
    merge_stream,
    paced,
    parse_clock,
    to_stream_message,
)
from formline.schema.feed import FeedMessage
from formline.schema.overlay import overlay_message
from formline.schema.tracking import tracking_path
from formline.tracking.frames import frames_for
from formline.viewer import UnknownMatch, match_league

CLOCK = r"^\d{1,3}:\d{2}$"  # mm:ss

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
async def stream(request: Request, match_id: str, speed: float | None = Query(None, gt=0),
                 live: bool = False, chaos: bool = False, chaos_seed: int = 0,
                 start: str | None = Query(None, pattern=CLOCK),
                 until: str | None = Query(None, pattern=CLOCK),
                 slow: bool = True, tracking: bool = True) -> EventSourceResponse:
    """Each SSE `data:` line is one StreamMessage as JSON (the viewer's live mode).

    Default: replays the feed together with the precomputed overlays
    (`formline-gen overlays`). `live=true` runs the engine and the agent workflow during
    the replay instead. `chaos=true` replays the feed through the chaos injector
    (duplicates, reordering, late messages, injected corrections) and implies live, so
    the cards follow the chaotic feed's own corrections. The stream ends with
    `{"kind": "end"}`.

    Playback controls: `speed` (feed seconds per real second); `start=mm:ss` delivers
    everything before that match time at once, then plays on; `until=mm:ss` stops there;
    `slow=true` (default) plays about 6x slower around shots and cards, but not below 3x
    (or the chosen speed, if slower). During gaps between
    events, `{"kind": "clock"}` messages (no SSE id) carry the running match time every 0.25 s
    of real time; when the match has tracking data (and `tracking=true`, the default) they
    are `{"kind": "frame"}` messages instead, which add the ball and all players. Minutes above 45 mean the
    second half. Every message has an SSE id, and a reconnecting client resumes after its
    `Last-Event-ID` instead of restarting the match (proxies may cut long streams).
    """
    path = settings.data_dir / "feeds" / f"{match_id}.jsonl"
    if not path.exists():
        raise HTTPException(404, f"Unknown match {match_id}")
    feed = read_feed(path)
    pace = speed or settings.sim_speed
    stop = parse_clock(until)
    last_id = request.headers.get("last-event-id", "")
    resume_after = int(last_id) if last_id.isdigit() else 0
    key_times = [m.emitted_at for m in feed if m.event is not None and m.event.type == "shot"]

    frames = frames_for(tracking_path(settings.data_dir, match_id)) if tracking else None

    def sse(idx: int | None, payload: dict) -> dict:
        if idx is None and frames is not None and payload.get("kind") == "clock":
            frame = frames.message(payload["period"], payload["match_clock_ms"])
            if frame is not None:
                return {"data": frame}
        data = json.dumps(payload, ensure_ascii=False)
        # Clock and frame messages carry no id, so Last-Event-ID always names a real message.
        return {"data": data} if idx is None else {"id": str(idx), "data": data}

    async def live_items(messages):
        runner = default_runner(settings.data_dir)
        orch = make_orchestrator(settings.data_dir, history_engine(settings.data_dir), runner)
        analyst = make_writer(settings.data_dir, match_id, runner)
        # Messages as they arrive, overlays as the orchestrator produces them (including those
        # its idle timeout releases between messages).
        async for at, item in orch.replay(messages):
            if isinstance(item, FeedMessage):
                if (payload := to_stream_message(item)) is not None:
                    yield at, payload
                for comment in await analyst.on_message(item):
                    yield at, comment_message(comment)
            else:
                yield at, overlay_message(item)
        last = messages[-1].emitted_at if messages else None
        for comment in await analyst.flush():
            yield last, comment_message(comment)

    async def gen():
        if live or chaos:
            messages = inject(feed, ChaosConfig(seed=chaos_seed)).messages if chaos else feed
            items = live_items(messages)
        else:
            cached = overlays_path(settings.data_dir, match_id)
            overlays = read_overlays(cached) if cached.exists() else []
            said = comments_path(settings.data_dir, match_id)
            items = merge_stream(feed, overlays, read_comments(said) if said.exists() else [])
            key_times.extend(at for at, _ in overlays)
        sent = resume_after
        async for idx, payload in paced(items, pace, start=parse_clock(start),
                                        resume_after=resume_after, key_times=key_times,
                                        slow=slow):
            if stop is not None and (mt := match_time(payload)) is not None and mt > stop:
                break
            yield sse(idx, payload)
            sent = idx if idx is not None else sent
        yield sse(sent + 1, END_MESSAGE)

    return EventSourceResponse(gen())
