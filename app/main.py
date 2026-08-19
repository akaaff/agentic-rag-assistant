from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel
from redis.asyncio import Redis

from app.agent.checkpointer import get_checkpointer
from app.agent.graph import compile_graph
from app.cache.semantic_cache import get_cached_answer, store_answer
from app.config import settings
from app.jwt_utils import extract_customer_id
from app.retrieval.embeddings import OllamaEmbeddingsClient


class ChatRequest(BaseModel):
    question: str
    thread_id: str


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _serialize(value: object) -> object:
    """Best-effort JSON-safe rendering of a LangGraph node's partial-state
    update (messages, SearchResult dataclasses, plain bools/ints/lists) for
    the node_update SSE event - this is what Day 8's demo UI reasoning-trace
    panel will consume.

    Node outputs from stream_mode="updates" are always dicts - a dict
    branch is required, not optional; without it every node_update payload
    silently fell through to the str(value) fallback (Python's repr of the
    whole dict, single-quoted and not valid JSON), verified live before
    this was added. asdict(SearchResult) also isn't fully JSON-safe on its
    own since chunk_id is a UUID - recursing into its result (rather than
    returning it directly) is what actually converts that.
    """
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, BaseMessage):
        return {"type": type(value).__name__, "content": value.content}
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize(asdict(value))
    if isinstance(value, uuid.UUID):
        return str(value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Checkpointer, graph, Redis client, and embeddings client are all
    # opened once at startup and reused for every request - not per-request,
    # which would mean a fresh Postgres/Redis connection on every chat call.
    async with get_checkpointer() as checkpointer:
        app.state.graph = compile_graph(checkpointer)
        app.state.redis = Redis.from_url(settings.redis_url)
        app.state.embeddings_client = OllamaEmbeddingsClient()
        try:
            yield
        finally:
            await app.state.redis.aclose()


app = FastAPI(lifespan=lifespan)


def _extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    return authorization.removeprefix("Bearer ").strip()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    token = _extract_token(authorization)
    try:
        customer_id = extract_customer_id(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    graph = request.app.state.graph
    redis: Redis = request.app.state.redis
    embeddings_client: OllamaEmbeddingsClient = request.app.state.embeddings_client

    async def event_stream() -> AsyncIterator[str]:
        [query_embedding] = await embeddings_client.embed([body.question])

        cached = await get_cached_answer(redis, customer_id, query_embedding)
        if cached is not None:
            yield _sse("cache_hit", {"answer": cached})
            yield _sse("done", {})
            return

        config = {"configurable": {"thread_id": body.thread_id}}
        initial_state = {
            "messages": [HumanMessage(body.question)],
            "is_out_of_scope_action": False,
            "customer_jwt": token,
            "needs_retrieval": False,
            "needs_tools": False,
            "retrieved_docs": [],
            "tool_call_count": 0,
            "needs_more_tools": False,
            "critique_verdict": None,
            "retried": False,
        }

        async for update in graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_output in update.items():
                yield _sse("node_update", {"node": node_name, "output": _serialize(node_output)})

        final_state = await graph.aget_state(config)
        final_answer = str(final_state.values["messages"][-1].content)
        touched_live_data = final_state.values["tool_call_count"] > 0

        await store_answer(
            redis, customer_id, touched_live_data, body.question, query_embedding, final_answer
        )

        yield _sse("answer", {"answer": final_answer})
        yield _sse("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_REPO_ROOT = Path(__file__).resolve().parent.parent

# Mounted AFTER every API route above - Starlette matches routes in
# registration order, so a "/" static mount registered first would shadow
# /health and /chat entirely. /docs_corpus is served read-only, straight
# from the same markdown files web-client's help-center panel renders
# client-side; "/" serves the demo UI itself (index.html/app.js/style.css).
# Unlike the sibling repo's web-client (its own `python -m http.server`
# process, since its backend is Java/Spring with no equivalent built-in),
# this app can just mount its own static directories directly - one
# process for the whole demo instead of two.
app.mount("/docs_corpus", StaticFiles(directory=_REPO_ROOT / "docs_corpus"), name="docs_corpus")
app.mount("/", StaticFiles(directory=_REPO_ROOT / "web-client", html=True), name="web-client")


if __name__ == "__main__":
    # Windows-local-dev-only path. Two layers deep of the same
    # ProactorEventLoop problem ingest.py hit on Day 2:
    #
    # 1. `uvicorn app.main:app` (the CLI) imports this module *inside* its
    #    own asyncio.run() call, so an asyncio_compat.apply() at this
    #    file's top level would run too late - the loop already exists.
    #    `python -m app.main` avoids that by applying the fix before
    #    uvicorn does anything, in the same process, sequentially.
    #
    # 2. That alone still isn't enough: verified live that uvicorn.run()
    #    forces asyncio.ProactorEventLoop on Windows unconditionally
    #    (uvicorn/loops/asyncio.py's asyncio_loop_factory - it ignores the
    #    ambient event-loop policy entirely and passes the Proactor class
    #    straight to asyncio.run(loop_factory=...)). No public Config
    #    option turns this off for a single-process run. So this bypasses
    #    uvicorn.run() and drives Server.serve() on a loop we create
    #    ourselves instead.
    #
    # Neither issue exists on Linux/Docker (Day 10's actual deployment
    # target) - ProactorEventLoop doesn't exist there, and the Dockerfile's
    # entrypoint can just run the normal `uvicorn app.main:app` CLI.
    import asyncio
    import selectors

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=8000)
    server = uvicorn.Server(config)

    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())
