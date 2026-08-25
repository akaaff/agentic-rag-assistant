# CLAUDE.md

Guidance for working in this repository, in the sibling repo's own convention: commands first, then an engineering log of real gotchas hit while building it - the "why" behind non-obvious decisions, not a restatement of what the code already says.

## Commands

Python 3.13, managed via [uv](https://docs.astral.sh/uv/). This is a non-packaged app (`tool.uv.package = false` in `pyproject.toml`) - it ships as a FastAPI service + scripts, not a distributable library.

- Install deps: `uv sync`
- Lint: `uv run ruff check .` / format: `uv run ruff format .` / type-check: `uv run mypy .`
- Unit tests (fully offline): `uv run pytest`
- Tests needing a live Ollama: `uv run pytest -m llm`
- Tests needing order-fulfillment-platform's gateway: `uv run pytest -m integration`
- Start local infra (Postgres+pgvector, Redis): `docker compose -f infra/docker-compose.yml --env-file .env up -d`
- Migrations: `uv run alembic upgrade head` (new revision: `uv run alembic revision -m "..."`)
- Ingest the docs corpus: `uv run python -m scripts.ingest`
- Run the app locally: `uv run python -m app.main` (`http://localhost:8000`) - **not** `uvicorn app.main:app` directly on Windows, see the ProactorEventLoop entry below
- Run the eval harness: `uv run python -m scripts.run_eval`
- Full containerized stack (app included): `docker compose -f infra/docker-compose.yml --env-file .env up -d --build`
- Self-hosted Langfuse (optional, separate compose file): `docker compose -f infra/docker-compose.langfuse.yml up -d`

Ollama must be running on the host with `qwen2.5:7b-instruct` and `nomic-embed-text` pulled (`OLLAMA_CHAT_MODEL`/`OLLAMA_EMBED_MODEL` env vars to override). order-fulfillment-platform's gateway (`http://localhost:8080` by default, `ORDER_PLATFORM_GATEWAY_URL` to override) is needed for login and any tool-calling question to have real data to answer from - this repo runs without it, but those questions won't resolve.

Local ports: this app `8000`, Postgres (this repo's own) `5434`, Redis `6379`, Langfuse web `3000` (Langfuse's own internal Postgres/Redis/ClickHouse/MinIO are not host-exposed at all - see `infra/docker-compose.langfuse.yml`).

## Architecture

See `README.md` for the diagram and `DECISIONS.md` for the trade-off reasoning behind each major choice. Short version: `app/agent/graph.py` wires five real nodes (`scope_check`, `router`, `retrieve`, `tools`, `critique`, `answer` - six, counting the tiny `mark_retry` bookkeeping node) into a LangGraph state machine; `app/retrieval/` does hybrid search (pgvector + Postgres `tsvector`, RRF-fused) then cross-encoder reranking; `app/gateway_client/` is a strictly read-only client for the sibling repo's API; `app/guardrails/` is the deterministic (non-LLM) safety layer; `app/cache/` is the customer-namespaced Redis semantic cache; `app/observability/` wires optional Langfuse tracing.

## Conventions to keep consistent

- **Live-verify before trusting, especially for anything touching a live service (DB, Ollama, an external API) or a library whose API might have moved.** This build's whole working pattern was checking real behavior directly rather than reasoning from documentation or memory - RAGAS's actual `ragas.metrics.collections` API, the real shape of Ollama's `/api/embed` response, uvicorn's actual Windows event-loop behavior, LangChain's actual handling of an unexpected tool argument - all confirmed live before code was written against them, and several turned out to differ from what documentation or general knowledge would have suggested.
- **Pure logic gets a unit test with a fake; DB/model-touching code gets verified live instead of mocked.** `rerank.py`'s injectable `score_fn`, the `_RedisLike` Protocol in `semantic_cache.py`, and the `FakeChatModel`/`FakeGatewayClient` test doubles all exist specifically to keep node-logic tests fast and hermetic - but `store.py`'s actual SQL and `embeddings.py`'s actual HTTP calls are verified against the real Postgres/Ollama instances instead of mocked, since a mock would only prove the mock was self-consistent, not that the real integration works.
- **Commit in small, clearly-described batches.** Most days of this build landed as 2-3 commits (e.g. "chunking+embeddings" then "hybrid retrieval+ingest+tests"), not one commit per day.
- Constructor-injected dependencies throughout (e.g. `GatewayClient()` constructed fresh per graph invocation, closed over `customer_jwt` - never passed as a call argument).

## Engineering log (gotchas, in the order they were found)

**Windows' `ProactorEventLoop` is incompatible with psycopg3's async mode**, and this was hit three separate times (`scripts/ingest.py`, `app/main.py`, `scripts/run_eval.py`) before being centralized in `app/asyncio_compat.py`. The fix has to run *before* `asyncio.run()` creates the loop - inside the coroutine `asyncio.run()` executes is too late, since the loop already exists by then. For `app/main.py`'s dev entrypoint specifically, that alone wasn't enough: uvicorn hardcodes `ProactorEventLoop` on Windows for a single-process run regardless of the ambient event-loop policy (`uvicorn/loops/asyncio.py`), so the fix there bypasses `uvicorn.run()` entirely and drives `Server.serve()` on a manually-created `SelectorEventLoop`. None of this exists on Linux (the actual Docker/deployment target) - `ProactorEventLoop` doesn't exist there.

**Postgres/psycopg can't infer a bind parameter's type from an `IS NULL OR col = $1` pattern alone** - `vector_search`/`keyword_search`'s optional `doc_type`/`category` filters hit `AmbiguousParameter` until wrapped in `CAST(:doc_type AS text)`. The more obvious-looking fix, `:doc_type::text`, silently fails to parse as a bind parameter at all - SQLAlchemy's `text()` bind-parameter regex trips on the adjacent `::`.

**`ruff` version drift between pre-commit and the project's own dependency** caused a real CI failure that passed locally: `astral-sh/ruff-pre-commit` was pinned to `v0.8.4` (left over from before mypy's hook was made local on Day 2 for this exact reason), while `pyproject.toml`'s `ruff>=0.8` had resolved to `0.16.3` - the two versions disagreed on whether to join two adjacent string literals onto one line in a migration file. Fixed by running both `ruff` hooks locally via `uv run` too, so there's one version of the tool in play, not two that can drift apart.

**`ragas` 0.4.3 is broken out of the box against a fresh dependency resolution**: `ragas/llms/base.py` unconditionally imports `ChatVertexAI` from `langchain_community.chat_models.vertexai`, a submodule that doesn't exist in the `langchain-community` version (`0.4.2`) that `uv` otherwise resolves - apparently removed there. Fixed by pinning `langchain-community<0.4` (resolves to `0.3.31`, which still has it).

**Omitting a Langfuse env var is not the same as it defaulting to what you'd expect**: leaving `CLICKHOUSE_CLUSTER_ENABLED` unset entirely (assuming a sane single-node default) made Langfuse's migration tooling try to create `ReplicatedMergeTree` tables `ON CLUSTER default`, which fails outright with no Zookeeper configured. The upstream compose file sets it to `false` explicitly - matched that rather than omitting it.

**A prompt-injection defense that looks complete can still do nothing**: `<untrusted_content>` delimiting plus an explicit system-prompt instruction not to follow directives inside those tags still resulted in 100% compliance with an embedded "ignore previous instructions" attack, in a live adversarial test. The actual fix was unrelated to either of those two things - moving the untrusted context to appear *before* the conversation in the message list, rather than after it, so the real user question is the last thing the model reads. See `DECISIONS.md` #9 for the full reasoning; the short version is that this was found and fixed by testing a concrete alternative, not by reasoning about prompt wording.

**`nomic-embed-text` cosine similarity does not cleanly separate "same question, reworded" from "different question, same topic"** - measured directly (not assumed) before picking the semantic cache's similarity threshold. See `DECISIONS.md` #10.

**RAGAS's real 0.4.x API differs substantially from older documentation/tutorials**: metrics live under `ragas.metrics.collections` (not the top-level `ragas.metrics` names most docs show), are scored per-sample via `.ascore(...)` rather than through the batch `evaluate()` dataset function, and the judge LLM is wired through the `instructor` library's client pattern (`ragas.llms.llm_factory(model, provider="openai", client=AsyncOpenAI(...))`) rather than a plain LangChain model object - Ollama works here via its own OpenAI-compatible `/v1` endpoint. All confirmed against the installed version directly.
