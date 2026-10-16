"""FastAPI entrypoint: streams synthetic events and match state over SSE."""

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from formline.config import settings
from formline.pipeline.ingest import generate_match
from formline.pipeline.interpret import Interpreter

app = FastAPI(title="Formline")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/matches/{match_id}/stream")
async def stream(match_id: str) -> EventSourceResponse:
    async def gen():
        interp = Interpreter()
        prev = 0
        for ev in generate_match(match_id):
            t = ev.minute * 60 + ev.second
            await asyncio.sleep(max(0, t - prev) / settings.sim_speed)
            prev = t
            state = interp.update(ev)
            yield {"event": "match_event", "data": ev.model_dump_json()}
            yield {"event": "state", "data": state.model_dump_json()}

    return EventSourceResponse(gen())
